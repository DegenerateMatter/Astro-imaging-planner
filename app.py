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
st.title("🔭 Astro Imaging Planner Pro V1.0")

with st.expander("📖 Quick-Start Guide & Instructions"):
    st.markdown("""
    1. **Set your location** in the sidebar to match your backyard.
    2. **Choose your filter type**: Broadband (RGB) skips bright moons; Narrowband (SHO) is more tolerant.
    3. **Set your Overheads**: Factor in your mount's meridian flip and autofocus time.
    4. **The Verdict**: A **Green Diamond** 💎 means clear skies and high altitudes!
    """)

# Simplified target mapping
COMMON_NAMES = {"rho ophiuchi": "IC 4604", "rosette": "NGC 2237", "orion": "M42", "andromeda": "M31"}
BORTLE_FACTORS = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.5, 5: 6.0, 6: 10.0, 7: 18.0, 8: 30.0, 9: 50.0}

def get_moon_phase_name(t):
    illum = moon_illumination(t)
    waxing = moon_illumination(t + 1*u.day) > illum
    if illum < 0.05: return "🌑 New Moon"
    if illum > 0.95: return "🌕 Full Moon"
    return ("🌓" if waxing else "🌗") + f" {illum*100:.0f}%"

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

st.sidebar.header("⚙️ Gear & Constraints")
moon_sep_limit = st.sidebar.number_input("Min Moon Separation (deg)", value=45)
min_alt = st.sidebar.number_input("Min Target Altitude (deg)", value=20)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=4)

tab1, tab2 = st.tabs(["⏱️ Night Sequencer", "📅 Campaign Planner"])

with tab1:
    c_d, c_s, c_e = st.columns(3)
    s_date = c_d.date_input("Imaging Night", dt.date.today())
    s_mode = c_s.selectbox("Start At", ["Astronomical Dusk", "Sunset"])
    e_mode = c_e.selectbox("End At", ["Astronomical Dawn", "Sunrise"])
    
    st.markdown("### Target Setup")
    c1, c2, c3, c4 = st.columns(4)
    t_name = c1.text_input("Object", "Rho Ophiuchi")
    t_type = c2.selectbox("Filter", ["Broadband", "Narrowband"])
    t_exp = c3.number_input("Exposure (s)", 120)
    t_subs = c4.number_input("Desired Subs", 60)

    if st.button("🚀 Calculate Window"):
        try:
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            g_s = observer.twilight_evening_astronomical(anc, 'next') if s_mode == "Astronomical Dusk" else observer.sun_set_time(anc, 'next')
            g_e = observer.twilight_morning_astronomical(g_s, 'next') if e_mode == "Astronomical Dawn" else observer.sun_rise_time(g_s, 'next')
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Night Length", f"{(g_e - g_s).to(u.hour).value:.1f} hrs")
            m2.metric("Moon Phase", get_moon_phase_name(g_s))
            m3.metric("Moon Illum", f"{moon_illumination(g_s)*100:.1f}%")

            qn = COMMON_NAMES.get(t_name.lower().strip(), t_name)
            co = SkyCoord.from_name(qn)
            to = FixedTarget(coord=co, name=t_name)
            
            ri = observer.target_rise_time(g_s, to, 'next', horizon=min_alt*u.deg)
            se = observer.target_set_time(g_s, to, 'next', horizon=min_alt*u.deg)
            if se < ri: se = observer.target_set_time(ri, to, 'next', horizon=min_alt*u.deg)
            
            sl, el = max(g_s, ri), min(g_e, se)
            
            if sl >= el:
                st.error("❌ Target is not visible tonight within limits.")
            else:
                usable = max(0, (el-sl).to(u.second).value - (flip_time*60))
                final_subs = int(usable // (t_exp + 5))
                st.success(f"💎 **VERDICT:** You can capture **{final_subs} subs** ({usable/3600:.1f} hrs) tonight.")
                
                with st.expander("✅ Imaging Checklist"):
                    st.checkbox("Dew heaters on?"); st.checkbox("Lens cap removed?"); st.checkbox("Polar alignment verified?")

                with st.expander("📝 Timing Logs & Charts"):
                    fig, ax = plt.subplots(figsize=(10, 4))
                    tm = g_s - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    ax.plot(tm.plot_date, co.transform_to(AltAz(obstime=tm, location=location)).alt.degree, color='#00ffcc')
                    ax.axvspan(sl.plot_date, el.plot_date, alpha=0.2, color='#00ffcc')
                    ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
                    fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white'); st.pyplot(fig)
        except Exception as e:
            st.error(f"Error: {e}. Check target spelling.")

with tab2:
    st.subheader("Campaign Strategy")
    if st.button("📅 Generate Strategy"):
        try:
            sd, ed = win if 'win' in locals() else (dt.date.today(), dt.date.today()+dt.timedelta(14))
            qn = COMMON_NAMES.get(t_name.lower().strip(), t_name)
            co = SkyCoord.from_name(qn)
            to = FixedTarget(coord=co, name=t_name)
            vd = [sd + dt.timedelta(x) for x in range((ed-sd).days+1)]
            acc, log = 0, []
            for d in vd:
                anc = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
                mp, ms = moon_illumination(dk)*100, co.separation(get_body("moon", dk, location)).degree
                if (ms < moon_sep_limit and mp > 15) or (t_type=="Broadband" and mp > 50):
                    usable, status = 0, "🔴 Moon"
                else:
                    try:
                        ri, se = observer.target_rise_time(dk, to, 'next', min_alt*u.deg), observer.target_set_time(dk, to, 'next', min_alt*u.deg)
                        sl, el = max(dk, ri), min(dw, se); usable = max(0, (el-sl).to(u.second).value - 1200)
                    except: usable = 0
                    status = "🟢 Clear" if usable > 0 else "⚫ Low"
                acc += usable
                log.append({"Date": d.strftime("%m/%d"), "Status": status, "Gain": round(usable/3600, 1)})
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)
            if bortle > 3: st.warning(f"Bortle {bortle} Reality: This equals {acc/3600/BORTLE_FACTORS[bortle]:.1f} dark-site hours.")
        except: st.error("Target lookup failed.")
