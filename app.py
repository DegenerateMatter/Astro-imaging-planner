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
st.title("🔭 Astro Imaging Planner Pro V2.6")

# --- 1. DATA & SESSION STATE ---
if 'target_queue' not in st.session_state:
    st.session_state.target_queue = []

NAME_FIXER = {
    "pleiades": "M45", "bode": "M81", "cigar": "M82", "whirlpool": "M51",
    "andromeda": "M31", "orion": "M42", "seagull": "IC 2177", "rho oph": "IC 4604",
    "rosette": "NGC 2237", "pinwheel": "M101", "elephant trunk": "IC 1396",
    "california": "NGC 1499", "witch head": "IC 2118"
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

# --- 3. WEATHER ENGINE ---
def get_weather(lat, lon, api_key):
    if not api_key: return "N/A"
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=imperial"
        data = requests.get(url).json()
        return f"{data['weather'][0]['description'].title()} | {data['clouds']['all']}% Clouds | {data['main']['temp']}°F"
    except: return "Offline"

# --- 4. SIDEBAR ---
st.sidebar.header("🌍 Location & Setup")
owm_key = st.sidebar.text_input("OpenWeatherMap API Key", type="password")
tz_string = st.sidebar.selectbox("Local Timezone", ["America/Phoenix", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"], index=0)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

st.sidebar.header("⚙️ Overheads")
min_alt = st.sidebar.slider("Min Altitude (deg)", 5, 45, 20)
min_sep = st.sidebar.slider("Moon Buffer (deg)", 10, 90, 35)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)
af_time = st.sidebar.number_input("AF Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Every (min)", value=60)
dither_time = st.sidebar.number_input("Dither (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

# --- 5. MISSION BUILDER ---
st.markdown("### 🎯 Mission Briefing")
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
new_t_name = c1.text_input("Target Name/ID")
new_t_exp = c2.number_input("Exposure (s)", value=300)
new_t_goal = c3.number_input("Goal (Total Hrs)", value=10.0)

if c4.button("➕ Add Mission"):
    t_data = lookup_target(new_t_name)
    if t_data:
        st.session_state.target_queue.append({**t_data, "exp": new_t_exp, "goal": new_t_goal, "banked": 0.0})
        st.rerun()

if st.session_state.target_queue:
    for i, t in enumerate(st.session_state.target_queue):
        with st.expander(f"📦 PROJECT: {t['name']} | Status: {int((t['banked']/t['goal'])*100)}% Complete"):
            cA, cB, cC = st.columns([1, 2, 1])
            cA.image(t['thumb'], width=150)
            t['banked'] = cB.number_input(f"Banked Hours for {t['name']}", value=float(t['banked']), step=0.5, key=f"bank_{i}")
            progress = min(t['banked'] / t['goal'], 1.0)
            cB.progress(progress)
            if cC.button(f"Remove", key=f"del_{i}"):
                st.session_state.target_queue.pop(i)
                st.rerun()

st.divider()

tab1, tab2 = st.tabs(["⏱️ Nightly Sequence", "📅 Strategic Roadmap"])

# --- TAB 1: SEQUENCER ---
with tab1:
    st.info(f"☁️ **Live Weather:** {get_weather(lat, lon, owm_key)}")
    s_date = st.date_input("Imaging Night", dt.date.today())
    if st.button("🚀 Sequence Night"):
        if not st.session_state.target_queue: st.warning("Add a mission first.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
            res = []
            for t in st.session_state.target_queue:
                ri, se = observer.target_rise_time(dk, t["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, t["target"], 'next', min_alt*u.deg)
                if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                sl, el = max(dk, ri), min(dw, se)
                if sl < el:
                    raw_s = (el - sl).to(u.second).value
                    net_s = max(0, raw_s - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60))
                    subs = int(net_s // (t["exp"] + dither_time))
                    res.append({"Target": t["name"], "Window": f"{sl.to_datetime(local_tz).strftime('%H:%M')} - {el.to_datetime(local_tz).strftime('%H:%M')}", "Subs": subs, "Gain": round((subs*t['exp'])/3600, 1)})
            st.table(pd.DataFrame(res))

# --- TAB 2: ROADMAP ---
with tab2:
    if st.button("🏁 Run Roadmap"):
        dates = [dt.date.today() + dt.timedelta(days=x) for x in range(30)]
        for t in st.session_state.target_queue:
            rem = t['goal'] - t['banked']
            st.markdown(f"#### 🛰️ {t['name']} (Remaining: {round(rem, 1)}h)")
            if rem <= 0: st.success("✅ Goal Achieved!")
            else:
                acc, log = 0, []
                for d in dates:
                    if acc >= rem: break
                    anc_c = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                    dk_c = observer.twilight_evening_astronomical(anc_c, 'next')
                    m_sep = t["coord"].separation(get_body("moon", dk_c, location)).degree
                    if m_sep > min_sep:
                        try:
                            ri, se = observer.target_rise_time(dk_c, t["target"], 'next', min_alt*u.deg), observer.target_set_time(dk_c, t["target"], 'next', min_alt*u.deg)
                            h = max(0, (min(observer.twilight_morning_astronomical(dk_c, 'next'), se if se > ri else observer.target_set_time(ri, t["target"], 'next', min_alt*u.deg)) - max(dk_c, ri)).to(u.second).value - 1200) / 3600
                        except: h = 0
                        if h > 0: acc += h; log.append({"Date": d.strftime("%m/%d"), "Gain": round(h, 1), "Total": round(acc + t['banked'], 1)})
                st.dataframe(pd.DataFrame(log), hide_index=True)
                if acc >= rem: st.success(f"🎯 Finish Line: {log[-1]['Date']}")
