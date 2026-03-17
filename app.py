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
st.title("🔭 Astro Imaging Planner Pro V1.2")

# --- DATA & CONSTANTS ---
NAME_FIXER = {
    "rho ophiuchi": "IC 4604", "rho oph": "IC 4604", "rosette": "NGC 2237",
    "orion": "M42", "andromeda": "M31", "thor's helmet": "NGC 2359",
    "crescent": "NGC 6888", "eagle": "M16", "lagoon": "M8", "trifid": "M20",
    "dumbbell": "M27", "ring": "M57", "whirlpool": "M51", "pinwheel": "M101",
    "heart": "IC 1805", "soul": "IC 1848", "california": "NGC 1499",
    "north america": "NGC 7000", "pelican": "IC 5070", "elephant trunk": "IC 1396",
    "wizard": "NGC 7380", "bubble": "NGC 7635", "pacman": "NGC 281",
    "m42": "M42", "m31": "M31", "m101": "M101", "m51": "M51"
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

st.sidebar.header("⚙️ Gear & Safety")
# MOON SAFETY: Now dynamic but with a "Danger Zone" floor
min_sep_allowed = st.sidebar.slider("Safety Buffer from Moon (deg)", 10, 90, 35)
min_alt = st.sidebar.number_input("Min Target Altitude (deg)", value=25)
flip_time = st.sidebar.number_input("Meridian Flip (min)", value=5)

tab1, tab2 = st.tabs(["⏱️ Session Sequencer", "📅 Campaign Planner"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    s_date = c1.date_input("Night", dt.date.today())
    t_name = c2.text_input("Object", "Rho Ophiuchi")
    t_type = c3.selectbox("Filter Type", ["Broadband (RGB)", "Narrowband (SHO/Dual)"])
    t_exp = c4.number_input("Exposure (s)", 120)

    if st.button("🚀 Run Session Forecast"):
        try:
            search_name = NAME_FIXER.get(t_name.lower().strip(), t_name)
            co = SkyCoord.from_name(search_name)
            to = FixedTarget(coord=co, name=t_name)
            
            # Times
            anc = Time(local_tz.localize(dt.datetime.combine(s_date, dt.time(12, 0))))
            a_dusk = observer.twilight_evening_astronomical(anc, 'next')
            a_dawn = observer.twilight_morning_astronomical(a_dusk, 'next')
            
            # Moon Position Logic
            moon_pos = get_body("moon", a_dusk, location)
            sep = co.separation(moon_pos).degree
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            m1.metric("Night Length", f"{(a_dawn - a_dusk).to(u.hour).value:.1f} hrs")
            m2.metric("Moon Phase", get_moon_phase_name(a_dusk))
            m3.metric("Target-Moon Sep", f"{sep:.1f}°")

            # Visibility Window
            ri = observer.target_rise_time(a_dusk, to, 'next', horizon=min_alt*u.deg)
            se = observer.target_set_time(a_dusk, to, 'next', horizon=min_alt*u.deg)
            if se < ri: se = observer.target_set_time(ri, to, 'next', horizon=min_alt*u.deg)
            sl, el = max(a_dusk, ri), min(a_dawn, se)

            # Dynamic Moon Separation Check
            if sep < min_sep_allowed:
                st.warning(f"⚠️ Warning: Target is only {sep:.1f}° from the Moon. Contrast may be severely degraded.")

            if sl >= el:
                st.error("❌ Target below altitude limits tonight.")
            else:
                usable = max(0, (el-sl).to(u.second).value - (flip_time*60))
                st.success(f"💎 **VERDICT:** Go! You have **{usable/3600:.1f} hours** of clear target time.")
                
                with st.expander("📈 Session Altitude Chart"):
                    fig, ax = plt.subplots(figsize=(10, 4))
                    tm = a_dusk - 1*u.hour + np.linspace(0, 12, 100)*u.hour
                    ax.plot(tm.plot_date, co.transform_to(AltAz(obstime=tm, location=location)).alt.degree, color='#00ffcc', label=t_name)
                    ax.axvspan(sl.plot_date, el.plot_date, alpha=0.2, color='#00ffcc')
                    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=local_tz))
                    fig.patch.set_facecolor('#0e1117'); ax.set_facecolor('#0e1117'); ax.tick_params(colors='white'); st.pyplot(fig)
        except Exception as e:
            st.error(f"Lookup Failed. Try a Catalog ID (M42, NGC 7000).")

with tab2:
    st.subheader("📅 Flexible Project Planning")
    mode = st.radio("Selection Mode", ["Single Date", "Date Range", "Specific Weekends"], horizontal=True)
    
    cA, cB = st.columns(2)
    if mode == "Single Date":
        dates = [cA.date_input("Select Date", dt.date.today())]
    elif mode == "Date Range":
        dr = cA.date_input("Select Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=14)])
        dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1)] if len(dr)==2 else []
    else:
        dr = cA.date_input("Select Month Range", [dt.date.today(), dt.date.today() + dt.timedelta(days=30)])
        days = cB.multiselect("Days", ["Friday", "Saturday", "Sunday"], ["Friday", "Saturday"])
        dates = [dr[0] + dt.timedelta(days=x) for x in range((dr[1]-dr[0]).days + 1) if (dr[0]+dt.timedelta(days=x)).strftime("%A") in days] if len(dr)==2 else []

    if st.button("📅 Generate Calendar Report"):
        try:
            search_name = NAME_FIXER.get(t_name.lower().strip(), t_name)
            co = SkyCoord.from_name(search_name)
            to = FixedTarget(coord=co, name=t_name)
            acc, log = 0, []
            
            for d in dates:
                anc = Time(local_tz.localize(dt.datetime.combine(d, dt.time(12, 0))))
                dk, dw = observer.twilight_evening_astronomical(anc, 'next'), observer.twilight_morning_astronomical(anc, 'next')
                
                # Dynamic Moon Separation for this specific date
                moon_at_dk = get_body("moon", dk, location)
                curr_sep = co.separation(moon_at_dk).degree
                illum = moon_illumination(dk)*100
                
                # Rule: Skip if too close OR if moon is too bright for Broadband
                if curr_sep < min_sep_allowed or (t_type.startswith("Broadband") and illum > 50):
                    usable, status = 0, "🔴 Moon Interference"
                else:
                    try:
                        ri, se = observer.target_rise_time(dk, to, 'next', min_alt*u.deg), observer.target_set_time(dk, to, 'next', min_alt*u.deg)
                        sl_c, el_c = max(dk, ri), min(dw, se)
                        usable = max(0, (el_c-sl_c).to(u.second).value - 1200)
                    except: usable = 0
                    status = "🟢 Clear" if usable > 0 else "⚫ Below Horizon"
                
                acc += usable
                log.append({"Date": d.strftime("%a %m/%d"), "Separation": f"{curr_sep:.0f}°", "Status": status, "Hours": round(usable/3600, 1)})
            
            st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True)
            st.info(f"✨ Total Project Time: **{acc/3600:.1f} hours** ({acc/3600/BORTLE_FACTORS[bortle]:.1f} dark-site hours)")
        except:
            st.error("Please enter a target in the first tab.")
