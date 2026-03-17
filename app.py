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
st.title("🔭 Astro Imaging Planner Pro V1.7")

# --- CORE LOOKUP ENGINE ---
# We now use the full power of SkyCoord.from_name for real-time data
def lookup_target(name):
    if not name or name.strip().upper() == "N/A": return None
    # Common Fixes for SIMBAD
    fixes = {"seagull nebula": "IC 2177", "rho ophiuchi": "IC 4604", "rosette": "NGC 2237"}
    search_name = fixes.get(name.lower().strip(), name)
    try:
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
min_alt_limit = st.sidebar.slider("Min Altitude Threshold (deg)", 5, 45, 15)
min_sep = st.sidebar.slider("Moon Buffer (deg)", 10, 90, 30)
flip_time = st.sidebar.number_input("Flip Time (min)", value=5)
af_time = st.sidebar.number_input("AF Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Interval (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

tab1, tab2 = st.tabs(["⏱️ Night Sequencer", "📅 Long-Range Planner"])

# --- TAB 1: SEQUENCER ---
with tab1:
    st.subheader("Live Target Diagnostics")
    c1, c2, c3 = st.columns(3)
    s_date = c1.date_input("Imaging Night", dt.date.today())
    t_name = c2.text_input("Target Name/ID", "Seagull Nebula")
    t_exp = c3.number_input("Sub Exposure (s)", 300)
    
    t_data = lookup_target(t_name)
    
    if t_data:
        anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
        # Calculate Rise/Set/Transit for the target
        transit = observer.target_meridian_transit_time(anc, t_data["target"], which='next')
        rise = observer.target_rise_time(anc, t_data["target"], which='next', horizon=min_alt_limit*u.deg)
        setting = observer.target_set_time(anc, t_data["target"], which='next', horizon=min_alt_limit*u.deg)
        
        st.success(f"✅ **{t_name} Found:** RA {t_data['coord'].ra.to_string(unit=u.hour, sep=':')} | Dec {t_data['coord'].dec.to_string(sep=':')}")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Meridian Transit", transit.to_datetime(local_tz).strftime('%H:%M'))
        m2.metric("Rises Above Limit", rise.to_datetime(local_tz).strftime('%H:%M') if rise else "N/A")
        m3.metric("Sets Below Limit", setting.to_datetime(local_tz).strftime('%H:%M') if setting else "N/A")

    if st.button("🚀 Run Precision Forecast"):
        if not t_data:
            st.error("Target not found. Please verify spelling.")
        else:
            # Imaging Window Logic
            dusk = observer.twilight_evening_astronomical(anc, which='next')
            dawn = observer.twilight_morning_astronomical(dusk, which='next')
            
            # Start imaging at whichever is later: Dusk or when it rises above min_alt
            start_time = max(dusk, rise) if rise else dusk
            # End imaging at whichever is earlier: Dawn or when it sets
            end_time = min(dawn, setting) if setting else dawn
            
            if start_time >= end_time:
                st.warning("⚠️ Target is not above your altitude threshold during astronomical darkness tonight.")
            else:
                raw_sec = (end_time - start_time).to(u.second).value
                # Overhead Calculation
                num_af = (raw_sec / 60) / af_freq
                total_overhead = (num_af * af_time * 60) + (flip_time * 60)
                net_sec = max(0, raw_sec - total_overhead)
                subs = int(net_sec // (t_exp + dither_time))
                
                st.info(f"💎 **Total Integration:** {round((subs*t_exp)/3600, 1)} hours ({subs} subs)")
                
                # Charting
                fig, ax = plt.subplots(figsize=(10, 4))
                times = dusk - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                altaz = t_data["coord"].transform_to(AltAz(obstime=times, location=location))
                ax.plot(times.plot_date, altaz.alt.degree, color='#00ffcc', lw=2)
                ax.axvspan(start_time.plot_date, end_time.plot_date, color='#00ffcc', alpha=0.15)
                ax.axhline(min_alt_limit, color='red', ls='--', alpha=0.5)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
                fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white')
                st.pyplot(fig)

with tab2:
    st.subheader("📅 Long-Range Strategy")
    if t_data:
        dr = st.date_input("Project Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=21)])
        if st.button("📅 Generate Report"):
            dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)]
            report = []
            for d in dates:
                anc_c = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                dk = observer.twilight_evening_astronomical(anc_c, 'next')
                # Simple check for each day
                m_pos = get_body("moon", dk, location)
                sep = t_data["coord"].separation(m_pos).degree
                report.append({"Date": d.strftime("%m/%d"), "Moon Sep": f"{int(sep)}°", "Status": "🟢" if sep > min_sep else "🔴"})
            st.table(pd.DataFrame(report))
