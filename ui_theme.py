"""ui_theme.py - Premium Look & Feel for Institutional F&O Sniper.
No trading logic, just pure modern CSS magic.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* Global Typography - Strictly avoiding st- classes to preserve Streamlit native icons */
html, body, p, span, div, h1, h2, h3, h4, h5, h6, button, input, textarea, label {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* Tabular numbers for price & P&L to keep columns aligned perfectly */
[data-testid="stMetricValue"], [data-testid="stDataFrame"], input[type="number"], .levels {
    font-variant-numeric: tabular-nums;
}

/* Main container spacing */
.block-container { 
    padding-top: 1.5rem; 
    max-width: 1400px; 
}
footer { visibility: hidden; }

/* Modern Metrics Cards (Subtle background, shadow & smooth corners) */
[data-testid="stMetric"] {
    background: rgba(128, 128, 128, 0.04);
    border: 1px solid rgba(128, 128, 128, 0.15);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 12px rgba(0,0,0,0.06);
}
[data-testid="stMetricLabel"] p { font-size: 0.85rem; opacity: 0.75; text-transform: uppercase; letter-spacing: 0.5px; }
[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; }

/* Enhanced Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 2rem; border-bottom: 2px solid rgba(128,128,128,0.1); }
.stTabs [data-baseweb="tab"] { 
    height: 3rem; 
    font-weight: 600; 
    font-size: 1.05rem;
}

/* Buttons, Alerts, and Sidebar */
.stButton > button { 
    border-radius: 8px; 
    font-weight: 600; 
    transition: all 0.2s ease;
}
.stButton > button:hover {
    transform: scale(1.02);
}
div[data-testid="stAlert"] { border-radius: 8px; border-left-width: 4px; }
section[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,0.15); }
h4 { font-size: 1.1rem; font-weight: 600; margin: 0.5rem 0 0.3rem; }

/* Signal Cards - Premium Institutional Look */
.sig-card {
    background: rgba(128, 128, 128, 0.03);
    border: 1px solid rgba(128,128,128,0.15);
    border-left-width: 6px;
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.8rem 0 0.5rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.sig-card:hover {
    box-shadow: 0 6px 12px rgba(0,0,0,0.08);
    transform: translateY(-1px);
}
.sig-call { border-left-color: #00b894; } /* Vibrant Green */
.sig-put  { border-left-color: #d63031; } /* Vibrant Red */

.sig-card .title { font-size: 1.15rem; font-weight: 700; margin-bottom: 0.4rem; }
.sig-card .levels { font-size: 0.95rem; margin-top: 0.4rem; font-weight: 500; opacity: 0.85; }

/* Modern Status Chips with dynamic text coloring */
.chip {
    display: inline-block; 
    padding: 0.25rem 0.7rem; 
    margin-right: 0.4rem; 
    margin-bottom: 0.4rem;
    border-radius: 999px; 
    font-size: 0.78rem; 
    font-weight: 600;
    letter-spacing: 0.2px;
    border: 1px solid rgba(128,128,128,0.25);
}
.chip-ok   { background: rgba(0, 184, 148, 0.12); border-color: rgba(0, 184, 148, 0.4); color: #00b894; }
.chip-warn { background: rgba(253, 203, 110, 0.12); border-color: rgba(253, 203, 110, 0.4); color: #e1b12c; }
.chip-bad  { background: rgba(214, 48, 49, 0.12); border-color: rgba(214, 48, 49, 0.4); color: #d63031; }
.chip-neutral { background: rgba(128, 128, 128, 0.08); color: inherit; }
</style>
"""

def apply_theme():
    """Injects the custom CSS into the Streamlit app. Call right after st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)

def chip(text, kind="neutral"):
    """Generates HTML for a small, styled status chip.
    Args:
        text: The text to display inside the chip.
        kind: "ok" (Green), "warn" (Yellow), "bad" (Red), or "neutral" (Gray).
    """
    cls_map = {
        "ok": "chip chip-ok", 
        "warn": "chip chip-warn", 
        "bad": "chip chip-bad",
        "neutral": "chip chip-neutral"
    }
    cls = cls_map.get(kind, "chip chip-neutral")
    return f'<span class="{cls}">{text}</span>'
