import streamlit as st
import numpy as np
import time as pytime
import datetime as dt
import pandas as pd
import pytz
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz, get_sun, get_body
import astropy.units as u
from astroplan import Observer, FixedTarget, moon_illumination
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import warnings
from astropy.utils.exceptions import AstropyWarning

# Suppress annoying warnings
warnings.simplefilter('ignore', category=AstropyWarning)

# Page Setup
st.set_page_config(layout="wide", page_title="Astro Imaging Planner Pro", page_icon="🔭")
st.title("🔭 Astro Imaging Planner Pro V1.0")

# --- USER FRIENDLY QUICK-START ---
with st.expander("📖 New here? Quick-Start Guide & Instructions"):
    st.markdown("""
    1. **Set your location** in the sidebar. This ensures the orbital math matches your backyard.
    2. **Choose your filter type**: 
        * **Broadband (RGB)**: Triggers strict Moon avoidance (>50% illumination = Skip).
        * **Narrowband (SHO)**: Allows imaging during brighter moons if the distance is safe.
    3. **Set your Overheads**: Factor in the time your mount takes to flip and focus.
    4. **The Verdict**: Look for the **Green Diamond** 💎 for the best possible imaging nights!
    """)

# --- TARGET DATABASE ---
COMMON_NAMES = {
    "seagull nebula": "IC 2177", "rosette nebula": "NGC 2237", "orion nebula": "M42",
    "andromeda galaxy": "M31", "pleiades": "M45", "trifid nebula": "M20",
    "lagoon nebula": "M8", "eagle nebula": "M16", "omega nebula": "M17",
    "swan nebula": "M17", "dumbbell nebula": "M27", "ring nebula": "M57",
    "crab nebula": "M1", "sombrero galaxy": "M104", "pinwheel galaxy": "M101",
    "whirlpool galaxy": "M51", "cigar galaxy": "M82", "bode's galaxy": "M81",
    "heart nebula": "IC 1805", "soul nebula": "IC 1848", "california nebula": "NGC 1499",
    "elephant's trunk nebula": "IC 1396", "north america nebula": "NGC 7000",
    "pelican nebula": "IC 5070", "witch head nebula": "IC 2118", "flame nebula": "NGC 2024",
    "horsehead nebula": "Barnard 33", "helix nebula": "NGC 7293", "veil nebula": "NGC 6960",
    "crescent nebula": "NGC 6888", "thor's helmet": "NGC 2359", "tarantula nebula": "NGC 2070",
    "carina nebula": "NGC 3372", "statue of liberty nebula": "NGC 3576", "pacman nebula": "NGC 281",
    "wizard nebula": "NGC 7380", "bubble nebula": "NGC 7635", "jellyfish nebula": "IC 443",
    "monkey head nebula": "NGC 2174", "spaghetti nebula": "Simeis 147", "iris nebula": "NGC 7023",
    "sunflower galaxy": "M63", "black eye galaxy": "M64", 
    "rho ophiuchi": "IC 4604", "rho oph": "IC 4604" 
}

BORTLE_FACTORS = {1: 1.0, 2: 1.5, 3: 2.2, 4: 3.5, 5: 6.0, 6: 10.0, 7: 18.0, 8: 30.0, 9: 50.0}

def get_moon_phase_name(time_obj):
    illum = moon_illumination(time_obj)
    tend = moon_illumination(time_obj + 1*u.day)
    waxing = tend > illum
    if illum < 0.05: return "🌑 New Moon"
    if illum > 0.95: return "🌕 Full Moon"
    if 0.45 <= illum <= 0.55: return "🌓 1st Qtr" if waxing else "🌗 Last Qtr"
    return ("🌒 Waxing" if waxing else "🌘 Waning") + (" Cres" if illum < 0.5 else " Gibb")

# --- SIDEBAR: GLOBAL SETTINGS ---
st.sidebar.header("🌍 Location & Setup")
tz_list = ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "Europe/London", "UTC"]
tz_string = st.sidebar.selectbox("Local Timezone", tz_list, index=3)
local_tz = pytz.timezone(tz_string)

lat = st.sidebar.number_input("Latitude", value=33.4484)
lon = st.sidebar.number_input("Longitude", value=-112.0740)
bortle = st.sidebar.slider("Bortle Class", 1, 9, 6)

location = EarthLocation(lat=lat*u.deg, lon=lon*u.deg, height=331*u.m)
observer = Observer(location=location, timezone=local_tz, name="Observer")

st.sidebar.header("⚙️ Gear & Constraints")
moon_sep_limit = st.sidebar.number_input("Min Moon Separation (deg)", value=45)
min_alt = st.sidebar.number_input("Min Target Altitude (deg)", value=20)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=4)
af_int = st.sidebar.number_input("AF Every (min)", value=60)

# --- TABS ---
tab1, tab2 = st.tabs(["⏱️ Night Sequencer", "📅 Campaign Planner"])

# --- TAB 1: NIGHT SEQUENCER ---
with tab1:
    c_d, c_s, c_e = st.columns(3)
    s_date = c_d.date_input("Imaging Night", dt.date.today(), format="MM/DD/YYYY")
    s_mode = c_s.selectbox("Start Imaging At", ["Astronomical Dusk", "Nautical Dusk", "Sunset", "Custom"])
    e_mode = c_e.selectbox("End Imaging At", ["Astronomical Dawn", "Nautical Dawn", "Sunrise", "Custom"])

    st.markdown("### Target Setup")
    c1, c2, c3, c4 = st.columns(4)
    with c1: t_name = st.text_input("Object", "Rho Ophiuchi")
    with c2: t_type = st.selectbox("Filter", ["Broadband", "Narrowband"])
    with c3: t_exp = st.number_input("Exposure (s)", 120)
    with c4: t_subs = st.number_input("Desired Subs", 60)

    if st.button("🚀 Calculate Imaging Window"):
        anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
        sunset = observer.sun_set_time(anc, 'next')
        s_rise = observer.sun_rise_time(anc, 'next')
        a_dusk = observer.twilight_evening_astronomical(anc, 'next')
        a_dawn = observer.twilight_morning_astronomical(sunset, 'next')
        
        g_s = a_dusk if s_mode == "Astronomical Dusk" else sunset
        g_e = a_dawn if e_mode == "Astronomical Dawn" else s_rise
        
        m_pct = moon_illumination(g_s)*100
        m_phase = get_moon_phase_name(g_s)
        
        # Dashboard KPIs
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("Night Length", f"{(g_e - g_s).to(u.hour).value:.1f} hrs")
        m2.metric("Moon Phase", m_phase)
        m3.metric("Illumination", f"{m_pct:.1f}%")

        qn = COMMON_NAMES.get(t_name.lower().strip(), t_name)
        try:
            co = SkyCoord.from_name(qn); to = FixedTarget(coord=co, name=t_name)
            tr = observer.target_meridian_transit_time(anc, to, 'next')
            ri = observer.target_rise_time(g_s, to, 'next', horizon=min_alt*u.deg)
            se = observer.target_set_time(g_s, to, 'next', horizon=min_alt*u.deg)
            if se < ri: se = observer.target_set_time(ri, to, 'next', horizon=min_alt*u.deg)
            sl, el = max(g_s, ri), min(g_e, se)
            
            if sl >= el:
                st.error("❌ Target is not visible tonight within your window/altitude limits.")
            else:
                raw_sec = (el-sl).to(u.second).value
                usable = max(0, raw_sec - (flip_time*60))
                final_subs = int(usable // (t_exp + 5))
                
                st.success(f"💎 **VERDICT:** Go for it! You can capture **{final_subs} subs** ({usable/3600:.1f} hrs) of {t_name} tonight.")
                
                # CHECKLIST FEATURE
                with st.expander("✅ Imaging Checklist"):
                    st.checkbox("Dew heaters turned on?")
                    st.checkbox("Lens cap removed?")
                    st.checkbox("Camera cooled to target temp?")
                    st.checkbox("Polar alignment verified?")
                    st.checkbox("Disk space checked (enough room for subs)?")

                with st.expander("📝 Detailed Timing Logs & Charts"):
                    st.write(f"Imaging Start: {sl.to_datetime(local_tz).strftime('%H:%M')} | Imaging End: {el.to_datetime(local_tz).strftime('%H:%M')}")
                    fig, ax = plt.subplots(figsize=(10, 4))
                    tm = sunset - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    ax.plot(tm.plot_date, co.transform_to(AltAz(obstime=tm, location=location)).alt.degree, label=t_name, color='#00ffcc', lw=2)
                    ax.axvspan(sl.plot_date, el.plot_date, alpha=0.2, color='#00ffcc')
                    ax.axhline(min_alt, ls="--", color="red", alpha=0.5)
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
                    fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white')
                    st.pyplot(fig)
        except: st.error("Target lookup failed. Check spelling or catalog ID.")

# --- TAB 2: CAMPAIGN PLANNER ---
with tab2:
    st.subheader("Deep Sky Project Planner")
    cA, cB = st.columns(2)
    win = cA.date_input("Project Range", (dt.date.today(), dt.date.today()+dt.timedelta(30)), format="MM/DD/YYYY")
    dys = cB.multiselect("Active Days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], ["Friday", "Saturday"])
    
    col1, col2, col3 = st.columns(3)
    ct = col1.text_input("Object Name", "Rho Ophiuchi", key="c_name")
    ct_t = col2.selectbox("Filter Type", ["Broadband", "Narrowband"], key="c_type")
    cg = col3.number_input("Goal (hrs)", 30.0)

    if st.button("📅 Generate Strategy Calendar"):
        sd, ed = win if len(win)==2 else (win[0], win[0])
        vd = [sd + dt.timedelta(x) for x in range((ed-sd).days+1) if (sd+dt.timedelta(x)).strftime("%A") in dys]
        qn = COMMON_NAMES.get(ct.lower().strip(), ct)
        try:
            co = SkyCoord.from_name
