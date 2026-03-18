import streamlit as st
import numpy as np
import datetime as dt
import pandas as pd
import pytz
import requests
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_body
import astropy.units as u
from astroplan import Observer, FixedTarget, moon_illumination
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
from astropy.utils.exceptions import AstropyWarning

warnings.simplefilter('ignore', category=AstropyWarning)

st.set_page_config(layout="wide", page_title="Astro Planner Pro", page_icon="🔭")
st.title("🔭 Astro Imaging Planner Pro V2.6: Progress Tracker")

# --- 1. DATA & SESSION STATE ---
if 'target_queue' not in st.session_state:
    st.session_state.target_queue = []

NAME_FIXER = {
    "pleiades": "M45", "bode": "M81", "cigar": "M82", "whirlpool": "M51",
    "andromeda": "M31", "orion": "M42", "seagull": "IC 2177", "rho oph": "IC 4604",
    "rosette": "NGC 2237", "pinwheel": "M101", "sombrero": "M104", "eagle": "M16"
}

# --- 2. FAIL-SAFE LOOKUP ---
def lookup_target(name):
    if not name or name.strip() == "": return None
    search_name = NAME_FIXER.get(name.lower().strip().replace(" ", ""), name)
    try:
        with st.spinner(f"Targeting {search_name}..."):
            co = SkyCoord.from_name(search_name)
            ra, dec = co.ra.deg, co.dec.deg
            img_url = f"https://archive.stsci.edu/cgi-bin/dss_search?v=poss2ukstu_red&r={ra}&d={dec}&e=J2000&h=15.0&w=15.0&f=gif"
            return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name), "thumb": img_url}
    except: return None

# --- 3. LIVE WEATHER ENGINE ---
def get_weather(lat, lon, api_key):
    if not api_key: return "N/A (Add Key in Sidebar)"
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
        data = requests.get(url).json()
        clouds, temp = data['clouds']['all'], data['main']['temp']
        desc = data['weather'][0]['description']
        return f"{desc.title()} | {clouds}% Clouds | {temp}°F"
    except: return "Weather Offline"

# --- 4. SIDEBAR PARAMETERS ---
st.sidebar.header("🌍 Location & Setup")
owm_key = st.sidebar.text_input("OpenWeatherMap API Key", type="password")
tz_string = st.sidebar.selectbox("Local Timezone", ["America/Phoenix", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"], index=0)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

st.sidebar.header("⚙️ Precision Overheads")
min_alt = st.sidebar.slider("Min Altitude Threshold (deg)", 5, 45, 20)
min_sep = st.sidebar.slider("Dynamic Moon Buffer (deg)", 10, 90, 35)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)
af_time = st.sidebar.number_input("AF Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Interval (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

# --- 5. THE MISSION BUILDER ---
st.markdown("### 🎯 Mission Briefing: Build Your Projects")
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
new_t_name = c1.text_input("Target Name/ID (e.g. M51, M104, Seagull)")
new_t_exp = c2.number_input("Exposure (s)", value=300)
new_t_goal = c3.number_input("Total Project Goal (Hrs)", value=10.0)

if c4.button("➕ Add to Missions"):
    t_data = lookup_target(new_t_name)
    if t_data:
        st.session_state.target_queue.append({**t_data, "exp": new_t_exp, "goal": new_t_goal, "captured": 0.0})
        st.toast(f"Locked on: {t_data['name']}")
    else: st.error("Target not found.")

if st.session_state.target_queue:
    st.markdown("#### 📂 Active Projects & Progress Logs")
    for i, t in enumerate(st.session_state.target_queue):
        with st.expander(f"📦 PROJECT: {t['name']} | Status: {t['captured']}/{t['goal']} hrs"):
            colA, colB, colC = st.columns([1, 2, 1])
            colA.image(t['thumb'], width=150)
            # THE LOGGING FEATURE
            t['captured'] = colB.number_input(f"Hours captured for {t['name']}", value=float(t['captured']), step=0.5, key=f"cap_{i}")
            colB.progress(min(1.0, t['captured']/t['goal']))
            colC.metric("Remaining Needed", f"{max(0.0, t['goal'] - t['captured']):.1f} hrs")
            if colC.button(f"Delete Project", key=f"del_{i}"):
                st.session_state.target_queue.pop(i)
                st.rerun()

st.divider()

tab1, tab2 = st.tabs(["⏱️ Nightly Sequence", "📅 Completion Roadmap"])

# --- TAB 1: SEQUENCER ---
with tab1:
    c_w1, c_w2 = st.columns([1, 2])
    c_w1.subheader("Nightly Plan")
    c_w2.info(f"☁️ **Live Weather:** {get_weather(lat, lon, owm_key)}")

    s_date = st.date_input("Select Night", dt.date.today())
    if st.button("🚀 Sequence Missions"):
        if not st.session_state.target_queue: st.warning("Add a mission above.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
            res, fig, ax = [], plt.subplots(figsize=(10, 3.5))[0], plt.subplots(figsize=(10, 3.5))[1]
            for t in st.session_state.target_queue:
                ri, se = observer.target_rise_time(dk, t["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, t["target"], 'next', min_alt*u.deg)
                if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                sl, el = max(dk, ri), min(dw, se)
                if sl < el:
                    raw_s = (el - sl).to(u.second).value
                    net_s = raw_s - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                    subs = int(net_s // (t["exp"] + dither_time))
                    h = round((subs*t['exp'])/3600, 1)
                    res.append({"Target": t["name"], "Window": f"{sl.to_datetime(local_tz).strftime('%H:%M')} - {el.to_datetime(local_tz).strftime('%H:%M')}", "Subs": subs, "Gain (Hrs)": h})
                    alt = t["coord"].transform_to(AltAz(obstime=dk + np.linspace(0, 12, 100)*u.hour, location=location)).alt.degree
                    ax.plot((dk + np.linspace(0, 12, 100)*u.hour).plot_date, alt, label=t["name"])
            st.table(pd.DataFrame(res))
            ax.axhline(min_alt, ls="--", color="red", alpha=0.5); ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
            fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white'); st.pyplot(fig)

# --- TAB 2: ROADMAP (THE GOAL TRACKER) ---
with tab2:
    st.subheader("Projected Completion Forecast")
    if st.button("🏁 Run Roadmap"):
        if not st.session_state.target_queue: st.error("Queue empty.")
        else:
            dates = [dt.date.today() + dt.timedelta(days=x) for x in range(30)]
            for t in st.session_state.target_queue:
                needed = t['goal'] - t['captured']
                st.markdown(f"#### 🔭 **{t['name']}** (Still need {max(0.0, needed):.1f} hrs)")
                if needed <= 0: st.success("✅ MISSION COMPLETE!"); continue
                acc_h, log = 0, []
                for d in dates:
                    if acc_h >= needed: break
                    anc_c = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                    dk_c = observer.twilight_evening_astronomical(anc_c, 'next')
                    if t["coord"].separation(get_body("moon", dk_c, location)).degree > min_sep:
                        try:
                            ri, se = observer.target_rise_time(dk_c, t["target"], 'next', min_alt*u.deg), observer.target_set_time(dk_c, t["target"], 'next', min_alt*u.deg)
                            if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                            h = max(0, (min(observer.twilight_morning_astronomical(dk_c, 'next'), se) - max(dk_c, ri)).to(u.second).value - 1200) / 3600
                            acc_h += h
                            if h > 0: log.append({"Date": d.strftime("%m/%d"), "Gain": round(h, 1), "Running Total": round(acc_h + t['captured'], 1)})
                        except: pass
                if acc_h > 0:
                    st.dataframe(pd.DataFrame(log), hide_index=True)
                    if acc_h >= needed: st.success(f"🎯 **Estimated Finish:** {log[-1]['Date']}")
                else: st.warning("Target not viable in current 30-day window.")
