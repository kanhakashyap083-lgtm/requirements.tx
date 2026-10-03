"""ui_theme.py - sirf look & feel. Isme koi trading logic, API call ya file read/write nahi hai.

Use:
    from ui_theme import apply_theme, chip
    st.set_page_config(...)
    apply_theme()          # set_page_config ke TURANT baad
"""
import streamlit as st

# Hare/lal rang sirf matlab ke liye: hara = bullish/profit, lal = bearish/loss.
# Baaki interface neutral rakha hai taaki light aur dark dono theme me chale.
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="st-"], button, input, textarea {
    font-family: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
}
/* Daam aur P&L ke ankon ki chaudai barabar, taaki columns seedhe dikhein */
[data-testid="stMetricValue"], [data-testid="stDataFrame"], input[type="number"] {
    font-variant-numeric: tabular-nums;
}

.block-container { padding-top: 2rem; max-width: 1400px; }
footer { visibility: hidden; }

/* Metrics: halka dabba, bada ank, chhota label */
[data-testid="stMetric"] {
    border: 1px solid rgba(128,128,128,.28);
    border-radius: 6px;
    padding: .65rem .9rem;
}
[data-testid="stMetricLabel"] p { font-size: .82rem; opacity: .75; }
[data-testid="stMetricValue"] { font-size: 1.6rem; font-weight: 600; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 1.5rem; }
.stTabs [data-baseweb="tab"] { height: 2.8rem; font-weight: 500; }

/* Buttons, alerts, sidebar */
.stButton > button { border-radius: 6px; font-weight: 600; }
div[data-testid="stAlert"] { border-radius: 6px; }
section[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.22); }
h4 { font-size: 1.05rem; font-weight: 600; margin: .4rem 0 .2rem; }

/* Signal card: baayi patti ka rang hi direction batata hai */
.sig-card {
    border: 1px solid rgba(128,128,128,.28);
    border-left-width: 5px;
    border-radius: 6px;
    padding: .7rem 1rem;
    margin: .6rem 0 .3rem;
}
.sig-call { border-left-color: #1f9d6b; }
.sig-put  { border-left-color: #d64545; }
.sig-card .title { font-size: 1.1rem; font-weight: 600; }
.sig-card .levels { margin-top: .3rem; font-variant-numeric: tabular-nums; opacity: .9; }

/* Chhote status chip */
.chip {
    display: inline-block; padding: .12rem .55rem; margin-right: .35rem;
    border-radius: 999px; font-size: .78rem; font-weight: 500;
    border: 1px solid rgba(128,128,128,.35);
}
.chip-ok   { background: rgba(31,157,107,.14); border-color: rgba(31,157,107,.5); }
.chip-warn { background: rgba(201,138,27,.14); border-color: rgba(201,138,27,.5); }
.chip-bad  { background: rgba(214,69,69,.14);  border-color: rgba(214,69,69,.5); }
</style>
"""


def apply_theme():
    """Page par CSS lagata hai. st.set_page_config ke baad ek baar call karo."""
    st.markdown(_CSS, unsafe_allow_html=True)


def chip(text, kind="neutral"):
    """Chhota label (HTML string). kind: ok | warn | bad | neutral.
    Use: st.markdown(chip("Auto-Pilot ON", "ok") + chip("VIX 14.2"), unsafe_allow_html=True)
    """
    cls = {"ok": "chip chip-ok", "warn": "chip chip-warn", "bad": "chip chip-bad"}.get(kind, "chip")
    return f'<span class="{cls}">{text}</span>'
