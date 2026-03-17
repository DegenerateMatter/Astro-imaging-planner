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
st.title("🔭 Astro Imaging Planner Pro V1.4")

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
min_sep = st.sidebar.slider("Moon Buffer (deg)", 10, 90, 35)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)
af_time = st.sidebar.number_input("AF Routine (min)", value=3)
af_freq = st.sidebar.number_input("AF Frequency (min)", value=60)
dither_time = st.sidebar.number_input("Dither Settle (sec)", value=10)

tab1, tab2 = st.tabs(["⏱️ Multi-Target Sequencer", "📅 Campaign Planner"])

# --- HELPERS ---
def lookup_target(name):
    if not name or name.strip().upper() == "N/A": return None
    try:
        search_name = NAME_FIXER.get(name.lower().strip(), name)
        co = SkyCoord.from_name(search_name)
        return {"coord": co, "name": name, "target": FixedTarget(coord=co, name=name)}
    except: return None

# --- TAB 1: MULTI-TARGET SEQUENCER ---
with tab1:
    st.subheader("Night Mission Control")
    s_date = st.date_input("Imaging Night", dt.date.today())
    
    st.markdown("### 🎯 Target Queue")
    c1, c2, c3 = st.columns(3)
    
    with c1:
        t1_name = st.text_input("Target 1", "Rho Ophiuchi")
        t1_exp = st.number_input("T1 Exposure (s)", 300, key="e1")
    with c2:
        t2_name = st.text_input("Target 2", "M42")
        t2_exp = st.number_input("T2 Exposure (s)", 120, key="e2")
    with c3:
        t3_name = st.text_input("Target 3", "N/A")
        t3_exp = st.number_input("T3 Exposure (s)", 60, key="e3")

    if st.button("🚀 Sequence My Night"):
        targets = [lookup_target(n) for n in [t1_name, t2_name, t3_name] if lookup_target(n)]
        exposures = [t1_exp, t2_exp, t3_exp]
        
        if not targets:
            st.error("No valid targets found in the queue.")
        else:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            a_dusk = observer.twilight_evening_astronomical(anc, 'next')
            a_dawn = observer.twilight_morning_astronomical(a_dusk, 'next')
            
            st.info(f"Astronomical Night: {a_dusk.to_datetime(local_tz).strftime('%H:%M')} to {a_dawn.to_datetime(local_tz).strftime('%H:%M')}")
            
            results = []
            fig, ax = plt.subplots(figsize=(10, 4))
            
            for i, t in enumerate(targets):
                # Calculate window for THIS specific target
                ri = observer.target_rise_time(a_dusk, t["target"], 'next', horizon=min_alt*u.deg)
                se = observer.target_set_time(a_dusk, t["target"], 'next', horizon=min_alt*u.deg)
                if se < ri: se = observer.target_set_time(ri, t["target"], 'next', horizon=min_alt*u.deg)
                
                sl, el = max(a_dusk, ri), min(a_dawn, se)
                
                if sl < el:
                    raw_s = (el - sl).to(u.second).value
                    # Apply overheads
                    net_s = raw_s - (af_time*60 * (raw_s/3600)) - (flip_time*60)
                    subs = int(net_s // (exposures[i] + dither_time))
                    
                    results.append({
                        "Target": t["name"],
                        "Start": sl.to_datetime(local_tz).strftime('%H:%M'),
                        "End": el.to_datetime(local_tz).strftime('%H:%M'),
                        "Subs": subs,
                        "Integration": f"{round((subs*exposures[i])/3600, 1)} hrs"
                    })
                    
                    # Add to plot
                    tm = a_dusk - 0.5*u.hour + np.linspace(0, 12, 100)*u.hour
                    alt = t["coord"].transform_to(AltAz(obstime=tm, location=location)).alt.degree
                    ax.plot(tm.plot_date, alt, label=t["name"], lw=2)
                else:
                    results.append({"Target": t["name"], "Status": "Not Visible"})

            st.table(pd.DataFrame(results))
            
            # Styling the chart
            ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
            fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white')
            st.pyplot(fig)

with tab2:
    st.subheader("📅 Long-Range Multi-Date Planner")
    dr = st.date_input("Select Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=14)])
    st.markdown("*(The Campaign Planner currently focuses on your Primary Target (T1) to ensure SNR goals are met)*")
    # ... (Campaign logic remains stable from V1.3)
