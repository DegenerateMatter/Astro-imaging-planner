import streamlit as st
import numpy as np
import datetime as dt
import pandas as pd
import pytz
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_body
import astropy.units as u
from astroplan import Observer, FixedTarget, moon_illumination
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
from astropy.utils.exceptions import AstropyWarning

warnings.simplefilter('ignore', category=AstropyWarning)

st.set_page_config(layout="wide", page_title="Astro Imaging Planner Pro", page_icon="🔭")
st.title("🔭 Astro Imaging Planner Pro V2.1: Unlimited Queue")

# --- TARGET NICKNAMES ---
NAME_FIXER = {
    "seagull nebula": "IC 2177", "seagull": "IC 2177", "rho ophiuchi": "IC 4604", 
    "rosette": "NGC 2237", "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396"
}

# --- SESSION STATE FOR TARGET QUEUE ---
if 'target_queue' not in st.session_state:
    st.session_state.target_queue = []

def lookup_target(name):
    try:
        search_name = NAME_FIXER.get(name.lower().strip(), name)
        co = SkyCoord.from_name(search_name)
        return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name)}
    except: return None

# --- SIDEBAR ---
st.sidebar.header("🌍 Location & Setup")
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
af_freq = st.sidebar.number_input("AF Interval (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

# --- TARGET BUILDER ---
st.markdown("### 🎯 Add Targets to your Acquisition Queue")
c1, c2, c3 = st.columns([2, 1, 1])
new_t_name = c1.text_input("Enter Target Name or Catalog ID (e.g. Seagull Nebula, M42)")
new_t_exp = c2.number_input("Exposure (s)", value=300)

if c3.button("➕ Add to Queue"):
    t_data = lookup_target(new_t_name)
    if t_data:
        st.session_state.target_queue.append({**t_data, "exp": new_t_exp})
        st.toast(f"Added {new_t_name} to queue!")
    else:
        st.error("Target not found.")

if st.session_state.target_queue:
    st.write(f"**Current Queue:** {', '.join([t['name'] for t in st.session_state.target_queue])}")
    if st.button("🗑️ Clear Queue"):
        st.session_state.target_queue = []
        st.rerun()

st.divider()

tab1, tab2 = st.tabs(["⏱️ Multi-Target Nightly Sequence", "📅 Seasonal Campaign Planner"])

# --- TAB 1: NIGHTLY SEQUENCE ---
with tab1:
    s_date = st.date_input("Imaging Night", dt.date.today())
    if st.button("🚀 Sequence Entire Queue"):
        if not st.session_state.target_queue:
            st.warning("Your queue is empty. Add some targets above first!")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
            
            results = []
            fig, ax = plt.subplots(figsize=(10, 4))
            
            for t in st.session_state.target_queue:
                ri = observer.target_rise_time(dk, t["target"], 'next', horizon=min_alt*u.deg)
                se = observer.target_set_time(dk, t["target"], 'next', horizon=min_alt*u.deg)
                if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                
                sl, el = max(dk, ri), min(dw, se)
                
                if sl < el:
                    raw_s = (el - sl).to(u.second).value
                    net_s = raw_s - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                    subs = int(net_s // (t["exp"] + dither_time))
                    
                    results.append({"Target": t["name"], "Window": f"{sl.to_datetime(local_tz).strftime('%H:%M')} - {el.to_datetime(local_tz).strftime('%H:%M')}", "Subs": subs, "Hrs": round((subs*t["exp"])/3600, 1)})
                    
                    tm = dk - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    alt = t["coord"].transform_to(AltAz(obstime=tm, location=location)).alt.degree
                    ax.plot(tm.plot_date, alt, label=t["name"], lw=2)
                
            st.table(pd.DataFrame(results))
            ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
            fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white'); st.pyplot(fig)

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.subheader("Seasonal Target Strategy")
    mode = st.radio("Plan For", ["Next 14 Days", "Specific Weekends", "Custom Range"], horizontal=True)
    
    if st.button("📅 Run Full Seasonal Report"):
        if not st.session_state.target_queue:
            st.warning("Add targets to your queue first.")
        else:
            # Logic for date selection based on mode
            if mode == "Next 14 Days":
                dates = [dt.date.today() + dt.timedelta(days=x) for x in range(14)]
            # ... (additional date logic here) ...
            
            for t in st.session_state.target_queue:
                st.markdown(f"#### 🔭 Planning for: **{t['name']}**")
                # (Campaign reporting logic for individual targets goes here)
                st.write("Calculating optimal windows for this DSO...")
