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
st.title("🔭 Astro Imaging Planner Pro V1.3")

# --- COLLOQUIAL NAME MAPPING ---
NAME_FIXER = {
    "rho ophiuchi": "IC 4604", "rho oph": "IC 4604", "rosette": "NGC 2237",
    "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396",
    "wizard": "NGC 7380", "bubble": "NGC 7635", "pacman": "NGC 281"
}

BORTLE_FACTORS = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.5, 5: 6.0, 6: 10.0, 7: 18.0, 8: 30.0, 9: 50.0}

def get_moon_phase_name(t):
    illum = moon_illumination(t)
    waxing = moon_illumination(t + 1*u.day) > illum
    icon = "🌑" if illum < 0.05 else "🌕" if illum > 0.95 else "🌓" if waxing else "🌗"
    return f"{icon} {illum*100:.0f}%"

# --- SIDEBAR ---
st.sidebar.header("🌍 Location & Setup")
tz_list = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "UTC"]
tz_string = st.sidebar.selectbox("Local Timezone", tz_list, index=3)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

st.sidebar.header("⚙️ Precision Variables")
min_alt = st.sidebar.number_input("Min Altitude (Horizon)", value=25)
min_sep = st.sidebar.slider("Dynamic Moon Buffer (deg)", 10, 90, 35)
st.sidebar.markdown("---")
# Precision Overhead Items
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)
af_time = st.sidebar.number_input("Autofocus Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Frequency (minutes between runs)", value=60)
dither_time = st.sidebar.number_input("Dither Settle Time (sec)", value=10)

tab1, tab2 = st.tabs(["⏱️ Sub-Exposure Sequencer", "📅 Campaign Planner"])

# --- SHARED TARGET LOOKUP ---
def lookup_target(name):
    try:
        if not name or name.strip() == "": return None
        search_name = NAME_FIXER.get(name.lower().strip(), name)
        co = SkyCoord.from_name(search_name)
        return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name)}
    except:
        return None

# --- TAB 1: SEQUENCER ---
with tab1:
    st.subheader("Single Night Sub-Exposure Detail")
    c1, c2, c3, c4 = st.columns(4)
    s_date = c1.date_input("Night", dt.date.today())
    target_input = c2.text_input("Target Name/ID", "Rho Ophiuchi")
    t_type = c3.selectbox("Filter", ["Narrowband", "Broadband"])
    t_exp = c4.number_input("Sub Duration (s)", 300)

    target_data = lookup_target(target_input)
    
    if st.button("🚀 Calculate Precision Subs"):
        if not target_data:
            st.error("Target not found. Please check spelling or use a catalog ID.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            a_dusk = observer.twilight_evening_astronomical(anc, 'next')
            a_dawn = observer.twilight_morning_astronomical(a_dusk, 'next')
            
            # Target Window
            ri = observer.target_rise_time(a_dusk, target_data["target"], 'next', horizon=min_alt*u.deg)
            se = observer.target_set_time(a_dusk, target_data["target"], 'next', horizon=min_alt*u.deg)
            if se < ri: se = observer.target_set_time(ri, target_data["target"], 'next', horizon=min_alt*u.deg)
            
            sl, el = max(a_dusk, ri), min(a_dawn, se)
            
            if sl >= el:
                st.error("Target never crosses the altitude threshold during astronomical dark.")
            else:
                raw_time_sec = (el - sl).to(u.second).value
                # THE PRECISION MATH
                total_af_time = (raw_time_sec / 60 / af_freq) * (af_time * 60)
                net_time = raw_time_sec - total_af_time - (flip_time * 60)
                subs = int(net_time // (t_exp + dither_time))
                
                st.success(f"💎 **VERDICT:** You can capture **{subs} subs** totaling **{round((subs*t_exp)/3600, 1)} hours** of integration.")
                
                c_a, c_b = st.columns(2)
                c_a.metric("Total Window", f"{round(raw_time_sec/3600, 1)} hrs")
                c_b.metric("Overhead Loss", f"{round((raw_time_sec - (subs*t_exp))/60, 0)} min")

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.subheader("Multi-Target Acquisition Strategy")
    
    # Range Selection
    dr = st.date_input("Campaign Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=21)])
    
    st.markdown("### Target Queue")
    colA, colB = st.columns(2)
    t1_input = colA.text_input("Primary Target", "Rho Ophiuchi")
    t2_input = colB.text_input("Secondary Target (Optional)", "N/A")
    
    if st.button("📅 Generate Full Campaign Report"):
        if len(dr) != 2:
            st.warning("Please select a range on the calendar.")
        else:
            t1 = lookup_target(t1_input)
            t2 = lookup_target(t2_input) if t2_input.upper() != "N/A" else None
            
            if not t1:
                st.error("Primary target missing or invalid.")
            else:
                # Target Info Display
                st.info(f"📍 **Target Info:** {t1['name']} | RA: {t1['coord'].ra.to_string(unit=u.hour, sep=':')} | Dec: {t1['coord'].dec.to_string(sep=':')}")
                
                dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)]
                report = []
                
                for d in dates:
                    anc = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                    dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
                    
                    # Moon Check
                    m_pos = get_body("moon", dk, location)
                    sep = t1["coord"].separation(m_pos).degree
                    illum = moon_illumination(dk)*100
                    
                    if sep < min_sep or (t_type == "Broadband" and illum > 50):
                        status, hrs = "🔴 Moon", 0
                    else:
                        try:
                            # Primary Target Window
                            ri, se = observer.target_rise_time(dk, t1["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, t1["target"], 'next', min_alt*u.deg)
                            if se < ri: se = observer.target_set_time(ri, t1["target"], 'next', min_alt*u.deg)
                            sl, el = max(dk, ri), min(dw, se)
                            
                            # Calculate Subs with Overheads
                            raw_s = (el-sl).to(u.second).value
                            if raw_s > 0:
                                net_s = raw_s - (af_time*60 * (raw_s/3600)) - (flip_time*60)
                                sub_count = int(net_s // (t_exp + dither_time))
                                hrs = round((sub_count * t_exp) / 3600, 1)
                                status = "🟢 Go"
                            else:
                                status, hrs = "⚫ Low", 0
                        except:
                            status, hrs = "⚠️ Error", 0
                    
                    report.append({"Date": d.strftime("%m/%d"), "Phase": get_moon_phase_name(dk), "Sep": f"{int(sep)}°", "Status": status, "Subs": int(hrs*3600/t_exp) if hrs > 0 else 0, "Hrs": hrs})
                
                df = pd.DataFrame(report)
                st.table(df)
                st.success(f"✨ Total Campaign Integration: **{df['Hrs'].sum():.1f} hours**")
