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
st.title("🔭 Astro Imaging Planner Pro V1.5")

# --- EXPANDED TARGET NICKNAMES ---
NAME_FIXER = {
    "seagull nebula": "IC 2177", "seagull": "IC 2177", "rho ophiuchi": "IC 4604", 
    "rosette": "NGC 2237", "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396"
}

BORTLE_FACTORS = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.5, 5: 6.0, 6: 10.0, 7: 18.0, 8: 30.0, 9: 50.0}

# --- HELPERS ---
def get_moon_phase_name(t):
    illum = moon_illumination(t)
    waxing = moon_illumination(t + 1*u.day) > illum
    icon = "🌑" if illum < 0.05 else "🌕" if illum > 0.95 else "🌓" if waxing else "🌗"
    return f"{icon} {illum*100:.0f}%"

def lookup_target(name):
    if not name or name.strip().upper() == "N/A": return None
    try:
        search_name = NAME_FIXER.get(name.lower().strip(), name)
        co = SkyCoord.from_name(search_name)
        return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name)}
    except: return None

# --- SIDEBAR ---
st.sidebar.header("🌍 Location & Setup")
tz_list = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "UTC"]
tz_string = st.sidebar.selectbox("Local Timezone", tz_list, index=3)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

st.sidebar.header("⚙️ Overheads & Safety")
min_alt = st.sidebar.number_input("Min Altitude", value=25)
min_sep = st.sidebar.slider("Moon Buffer (deg)", 10, 90, 35)
flip_time = st.sidebar.number_input("Flip Time (min)", value=5)
af_time = st.sidebar.number_input("AF Time (min)", value=3)
af_freq = st.sidebar.number_input("AF Frequency (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

tab1, tab2 = st.tabs(["⏱️ Single Night Sequencer", "📅 Campaign Planner"])

# --- TAB 1: SEQUENCER ---
with tab1:
    st.subheader("Target Preview & Acquisition")
    c1, c2, c3 = st.columns(3)
    s_date = c1.date_input("Night", dt.date.today())
    t_name = c2.text_input("Target Name", "Seagull Nebula")
    t_exp = c3.number_input("Sub Exposure (s)", 300)
    
    t_data = lookup_target(t_name)
    if t_data:
        st.info(f"📍 **Coordinates Found:** RA {t_data['coord'].ra.to_string(unit=u.hour, sep=':')} | Dec {t_data['coord'].dec.to_string(sep=':')}")

    if st.button("🚀 Calculate Single Night"):
        if not t_data:
            st.error("Target not found. Check spelling or use NGC/IC/M catalog number.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            a_dusk = observer.twilight_evening_astronomical(anc, 'next')
            a_dawn = observer.twilight_morning_astronomical(a_dusk, 'next')
            ri = observer.target_rise_time(a_dusk, t_data["target"], 'next', horizon=min_alt*u.deg)
            se = observer.target_set_time(a_dusk, t_data["target"], 'next', horizon=min_alt*u.deg)
            if se < ri: se = observer.target_set_time(ri, t_data["target"], 'next', horizon=min_alt*u.deg)
            sl, el = max(a_dusk, ri), min(a_dawn, se)
            
            if sl >= el: st.error("Target is below horizon during darkness.")
            else:
                raw_s = (el-sl).to(u.second).value
                net_s = raw_s - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                subs = int(net_s // (t_exp + dither_time))
                st.success(f"💎 **Result:** {subs} subs ({round((subs*t_exp)/3600, 1)} hrs) possible.")

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.subheader("Multi-Night Planning Mode")
    mode = st.radio("Input Method", ["Date Range", "Specific Weekends", "Single Night (Next 14 Days)"], horizontal=True)
    
    cA, cB = st.columns(2)
    if mode == "Date Range":
        dr = cA.date_input("Select Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=14)])
        target_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)] if len(dr)==2 else []
    elif mode == "Specific Weekends":
        dr = cA.date_input("Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=30)])
        days = cB.multiselect("Days", ["Friday", "Saturday", "Sunday"], ["Friday", "Saturday"])
        target_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1) if (dr[0]+dt.timedelta(days=x)).strftime("%A") in days] if len(dr)==2 else []
    else:
        target_dates = [dt.date.today() + dt.timedelta(days=x) for x in range(14)]

    if st.button("📅 Generate Multi-Night Report"):
        if not t_data: st.error("Enter a target in Tab 1 first.")
        elif not target_dates: st.warning("Please select a valid date range.")
        else:
            report = []
            for d in target_dates:
                anc = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
                m_pos = get_body("moon", dk, location)
                sep = t_data["coord"].separation(m_pos).degree
                illum = moon_illumination(dk)*100
                
                if sep < min_sep: status, hrs = "🔴 Moon Sep", 0
                else:
                    try:
                        ri, se = observer.target_rise_time(dk, t_data["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, t_data["target"], 'next', min_alt*u.deg)
                        sl, el = max(dk, ri), min(dw, se)
                        usable = max(0, (el-sl).to(u.second).value - 1800)
                        hrs = round(usable/3600, 1)
                        status = "🟢 Clear" if hrs > 0 else "⚫ Low"
                    except: status, hrs = "⚫ Below", 0
                report.append({"Date": d.strftime("%m/%d"), "Moon": get_moon_phase_name(dk), "Sep": f"{int(sep)}°", "Status": status, "Hrs": hrs})
            
            df = pd.DataFrame(report)
            st.table(df)
            st.success(f"✨ Total Project Potential: {df['Hrs'].sum():.1f} hours.")
