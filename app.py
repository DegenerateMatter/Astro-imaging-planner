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
st.title("🔭 Astro Imaging Planner Pro V3.0")

# --- TARGET NICKNAMES ---
NAME_FIXER = {
    "seagull nebula": "IC 2177", "seagull": "IC 2177", "rho ophiuchi": "IC 4604", 
    "rosette": "NGC 2237", "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396"
}

if 'target_queue' not in st.session_state:
    st.session_state.target_queue = []

def lookup_target(name):
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

# --- LEFT PANE: ADVANCED COMMAND CENTER ---
st.sidebar.header("🌍 Location & Sky Conditions")
tz_string = st.sidebar.selectbox("Timezone", ["America/Phoenix", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "UTC"], index=0)
local_tz = pytz.timezone(tz_string)
lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

st.sidebar.header("⚙️ Optics & Filter Settings")
active_filter = st.sidebar.selectbox("Primary Filter", [
    "Antlia Duo Narrowband Ha OIII 3nm",
    "Antlia Duo Narrowband SII Ha-b 5nm",
    "Antlia Quadband",
    "Optolong L-Pro",
    "Generic Broadband (RGB)",
    "Generic Narrowband (SHO)"
])
min_alt = st.sidebar.slider("Min Target Altitude (deg)", 10, 50, 25)
base_moon_buffer = st.sidebar.slider("Base Moon Buffer (deg)", 10, 90, 35)

st.sidebar.header("⏱️ Gear Overheads")
caa_time = st.sidebar.number_input("ZWO CAA Rotation/Framing (min)", value=2)
flip_time = st.sidebar.number_input("Meridian Flip Time (min)", value=5)
af_time = st.sidebar.number_input("Autofocus Time (min)", value=3)
af_freq = st.sidebar.number_input("Autofocus Interval (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz)

# Dynamic Moon Logic based on Filter
def is_moon_safe(sep, illum, filter_name):
    if "3nm" in filter_name: return sep > (base_moon_buffer * 0.4) # Super tight bandpass handles moon well
    if "5nm" in filter_name or "Narrowband" in filter_name: return sep > (base_moon_buffer * 0.6)
    if "Quadband" in filter_name: return sep > (base_moon_buffer * 0.8) and illum < 80
    # L-Pro or Broadband
    return sep > base_moon_buffer and illum < 60

# --- TARGET BUILDER ---
st.markdown("### 🎯 Mission Target Queue")
c1, c2, c3 = st.columns([2, 1, 1])
new_t_name = c1.text_input("Enter DSO Name or Catalog ID (e.g. Seagull, M42)")
new_t_exp = c2.number_input("Exposure (s)", value=300)

if c3.button("➕ Add to Session"):
    t_data = lookup_target(new_t_name)
    if t_data:
        st.session_state.target_queue.append({**t_data, "exp": new_t_exp})
    else:
        st.error("Target not found. Try catalog ID.")

if st.session_state.target_queue:
    st.info(f"**Loaded Targets:** {', '.join([t['name'] for t in st.session_state.target_queue])}")
    if st.button("🗑️ Clear Queue"):
        st.session_state.target_queue = []
        st.rerun()

st.divider()

tab1, tab2 = st.tabs(["⏱️ Nightly Multi-Target Sequence", "📅 Seasonal Campaign Planner"])

# --- TAB 1: NIGHTLY SEQUENCE ---
with tab1:
    st.markdown("#### Plan a Specific Night")
    s_date = st.date_input("Select Imaging Date", dt.date.today(), key="night_date")
    
    if st.button("🚀 Sequence My Target Queue"):
        if not st.session_state.target_queue:
            st.warning("Add targets to your queue first!")
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
                    # Apply all advanced overheads
                    net_s = raw_s - (caa_time * 60) - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                    subs = int(net_s // (t["exp"] + dither_time)) if net_s > 0 else 0
                    
                    results.append({
                        "Target": t["name"], 
                        "Imaging Window": f"{sl.to_datetime(local_tz).strftime('%H:%M')} - {el.to_datetime(local_tz).strftime('%H:%M')}", 
                        "Subs": subs, 
                        "True Time": f"{round((subs*t['exp'])/3600, 1)} hrs"
                    })
                    
                    tm = dk - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    alt = t["coord"].transform_to(AltAz(obstime=tm, location=location)).alt.degree
                    ax.plot(tm.plot_date, alt, label=t["name"], lw=2)
                else:
                    results.append({"Target": t["name"], "Imaging Window": "Below Altitude Threshold", "Subs": 0, "True Time": "0 hrs"})
                
            st.table(pd.DataFrame(results))
            ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
            fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white')
            ax.legend()
            st.pyplot(fig)

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.markdown("#### Plan a Multi-Day Strategy")
    mode = st.radio("Scheduling Method", ["Custom Date Picker", "Date Range", "Specific Weekends"], horizontal=True)
    
    if mode == "Custom Date Picker":
        # Generate next 30 days for user to pick from
        date_options = [dt.date.today() + dt.timedelta(days=i) for i in range(30)]
        selected_dates = st.multiselect("Select the exact days you plan to image:", date_options, default=date_options[:2])
    elif mode == "Date Range":
        dr = st.date_input("Select Date Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=14)])
        selected_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)] if len(dr)==2 else []
    else:
        dr = st.date_input("Select Month Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=30)])
        days = st.multiselect("Allowed Days", ["Friday", "Saturday", "Sunday"], ["Friday", "Saturday"])
        selected_dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1) if (dr[0]+dt.timedelta(days=x)).strftime("%A") in days] if len(dr)==2 else []

    if st.button("📅 Generate Tactical Campaign"):
        if not st.session_state.target_queue:
            st.warning("Add targets to your queue first.")
        elif not selected_dates:
            st.warning("Please select valid dates.")
        else:
            for t in st.session_state.target_queue:
                st.markdown(f"#### 🔭 Forecast for: **{t['name']}**")
                report = []
                for d in selected_dates:
                    anc_c = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                    dk, dw = observer.twilight_evening_astronomical(anc_c, 'next'), observer.twilight_morning_astronomical(anc_c, 'next')
                    m_pos = get_body("moon", dk, location)
                    sep = t["coord"].separation(m_pos).degree
                    illum = moon_illumination(dk)*100
                    
                    if not is_moon_safe(sep, illum, active_filter): 
                        status, h, subs = "🔴 Moon Interference", 0, 0
                    else:
                        try:
                            ri, se = observer.target_rise_time(dk, t["target"], 'next', min_alt*u.deg), observer.target_set_time(dk, t["target"], 'next', min_alt*u.deg)
                            sl, el = max(dk, ri), min(dw, se)
                            raw_s = (el-sl).to(u.second).value
                            if raw_s > 0:
                                net_s = raw_s - (caa_time * 60) - (af_time*60 * (raw_s/(af_freq*60))) - (flip_time*60)
                                subs = int(net_s // (t["exp"] + dither_time)) if net_s > 0 else 0
                                h = round((subs*t["exp"])/3600, 1)
                                status = "🟢 Optimal" if h > 0 else "⚫ Low Time"
                            else:
                                status, h, subs = "⚫ Below Altitude", 0, 0
                        except: 
                            status, h, subs = "⚫ Not Visible", 0, 0
                    
                    report.append({"Date": d.strftime("%a %m/%d"), "Moon Phase": get_moon_phase_name(dk), "Moon Sep": f"{int(sep)}°", "Verdict": status, "Subs": subs, "True Integration": f"{h} hrs"})
                
                df = pd.DataFrame(report)
                st.table(df)
                total_hrs = sum([float(x.split(' ')[0]) for x in df['True Integration']])
                st.success(f"**{t['name']} Summary:** You can expect **{total_hrs:.1f} hours** of usable data. *(Bortle {bortle} Equivalent SNR: {total_hrs/BORTLE_FACTORS[bortle]:.1f} dark-site hours)*")
