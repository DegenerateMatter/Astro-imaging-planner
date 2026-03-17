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
st.title("🔭 Astro Imaging Planner Pro V2.0")

# --- CORE ENGINE & NICKNAMES ---
NAME_FIXER = {
    "seagull nebula": "IC 2177", "seagull": "IC 2177", "rho ophiuchi": "IC 4604", 
    "rosette": "NGC 2237", "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396"
}

BORTLE_FACTORS = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.5, 5: 6.0, 6: 10.0, 7: 18.0, 8: 30.0, 9: 50.0}

def lookup_target(name):
    if not name or name.strip().upper() == "N/A": return None
    try:
        search_name = NAME_FIXER.get(name.lower().strip(), name)
        co = SkyCoord.from_name(search_name)
        return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name)}
    except: return None

def get_moon_phase_name(t):
    illum = moon_illumination(t)
    waxing = moon_illumination(t + 1*u.day) > illum
    icon = "🌑" if illum < 0.05 else "🌕" if illum > 0.95 else "🌓" if waxing else "🌗"
    return f"{icon} {illum*100:.0f}%"

# --- SIDEBAR: MISSION PARAMETERS ---
st.sidebar.header("🌍 Location & Setup")
tz_string = st.sidebar.selectbox("Local Timezone", ["America/Phoenix", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"], index=0)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

st.sidebar.header("⚙️ Overheads & Precision")
min_alt = st.sidebar.slider("Min Altitude (deg)", 5, 45, 20)
min_sep = st.sidebar.slider("Moon Buffer (deg)", 10, 90, 35)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)
af_time = st.sidebar.number_input("AF Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Interval (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

tab1, tab2 = st.tabs(["⏱️ Nightly Multi-Target Sequencer", "📅 Seasonal Campaign Planner"])

# --- TAB 1: SEQUENCER ---
with tab1:
    st.subheader("Night Mission Control")
    s_date = st.date_input("Imaging Night", dt.date.today())
    
    st.markdown("### 🎯 Target Queue")
    c1, c2, c3 = st.columns(3)
    t1_n = c1.text_input("Target 1", "Seagull Nebula")
    t1_e = c1.number_input("T1 Exposure (s)", 300, key="e1")
    t2_n = c2.text_input("Target 2", "Rho Ophiuchi")
    t2_e = c2.number_input("T2 Exposure (s)", 120, key="e2")
    t3_n = c3.text_input("Target 3", "N/A")
    t3_e = c3.number_input("T3 Exposure (s)", 60, key="e3")

    if st.button("🚀 Sequence My Night"):
        targets = [lookup_target(n) for n in [t1_n, t2_n, t3_n] if lookup_target(n)]
        exposures = [t1_e, t2_e, t3_e]
        
        if not targets:
            st.error("No valid targets found.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
            
            st.success(f"Astronomical Dark: {dk.to_datetime(local_tz).strftime('%H:%M')} to {dw.to_datetime(local_tz).strftime('%H:%M')}")
            
            results = []
            fig, ax = plt.subplots(figsize=(10, 4))
            
            for i, t in enumerate(targets):
                ri = observer.target_rise_time(dk, t["target"], 'next', horizon=min_alt*u.deg)
                se = observer.target_set_time(dk, t["target"], 'next', horizon=min_alt*u.deg)
                if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                
                sl, el = max(dk, ri), min(dw, se)
                
                if sl < el:
                    raw_s = (el - sl).to(u.second).value
                    net_s = raw_s - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                    subs = int(net_s // (exposures[i] + dither_time))
                    hrs = round((subs*exposures[i])/3600, 1)
                    
                    results.append({"Target": t["name"], "Window": f"{sl.to_datetime(local_tz).strftime('%H:%M')} - {el.to_datetime(local_tz).strftime('%H:%M')}", "Subs": subs, "Total Hrs": hrs})
                    
                    # Plotting
                    tm = dk - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    alt = t["coord"].transform_to(AltAz(obstime=tm, location=location)).alt.degree
                    ax.plot(tm.plot_date, alt, label=t["name"], lw=2)
                    ax.axvspan(sl.plot_date, el.plot_date, alpha=0.1)
                
            st.table(pd.DataFrame(results))
            ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
            fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white'); st.pyplot(fig)

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.subheader("Seasonal Strategy & Go/No-Go Decision")
    mode = st.radio("Planning Mode", ["Date Range", "Specific Weekends", "Single Night (Auto-14 Days)"], horizontal=True)
    
    cA, cB = st.columns(2)
    if mode == "Date Range":
        dr = cA.date_input("Select Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=21)])
        t_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)] if len(dr)==2 else []
    elif mode == "Specific Weekends":
        dr = cA.date_input("Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=45)])
        days = cB.multiselect("Allowed Days", ["Friday", "Saturday", "Sunday"], ["Friday", "Saturday"])
        t_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1) if (dr[0]+dt.timedelta(days=x)).strftime("%A") in days] if len(dr)==2 else []
    else:
        t_dates = [dt.date.today() + dt.timedelta(days=x) for x in range(14)]

    if st.button("📅 Generate Season Report"):
        primary = lookup_target(t1_n)
        if not primary: st.error("Please enter Target 1 in the Sequencer tab.")
        else:
            report = []
            for d in t_dates:
                anc_c = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                dk, dw = observer.twilight_evening_astronomical(anc_c, 'next'), observer.twilight_morning_astronomical(anc_c, 'next')
                m_pos = get_body("moon", dk, location)
                sep = primary["coord"].separation(m_pos).degree
                illum = moon_illumination(dk)*100
                
                if sep < min_sep: status, h = "🔴 Moon Sep", 0
                else:
                    try:
                        ri, se = observer.target_rise_time(dk, primary["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, primary["target"], 'next', min_alt*u.deg)
                        sl, el = max(dk, ri), min(dw, se)
                        h = round(max(0, (el-sl).to(u.second).value - 1800)/3600, 1)
                        status = "🟢 Clear" if h > 0 else "⚫ Low"
                    except: status, h = "⚫ Below", 0
                
                report.append({"Date": d.strftime("%a %m/%d"), "Moon": get_moon_phase_name(dk), "Sep": f"{int(sep)}°", "Status": status, "Hrs": h})
            
            df = pd.DataFrame(report)
            st.table(df)
            st.info(f"✨ **Campaign Goal Performance:** Total Found: **{df['Hrs'].sum():.1f} hrs**. Equivalent Dark-Site SNR: **{df['Hrs'].sum()/BORTLE_FACTORS[bortle]:.1f} hrs**.")
