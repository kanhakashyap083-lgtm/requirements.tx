import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz
import time
import requests
import warnings

warnings.filterwarnings("ignore")

# --- APP SETUP & CUSTOM CSS (PRO-UI) ---
st.set_page_config(page_title="F&O Sniper Bot", page_icon="🎯", layout="wide")

# 🎨 Custom UI Magic
st.markdown("""
<style>
    /* Gradient Text for Main Title */
    .main-title {
        text-align: center;
        font-size: 45px;
        font-weight: 900;
        background: -webkit-linear-gradient(45deg, #FF416C, #FF4B2B);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    
    /* Styling the Metric Cards (Nifty/BankNifty/Sensex Prices) */
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.1);
        border-radius: 12px;
        padding: 15px 20px;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.05);
        border-left: 6px solid #FF4B2B;
        transition: transform 0.2s ease-in-out;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        border-left: 6px solid #00FFA3;
    }
    
    /* Super-Premium Scan Button */
    .stButton > button {
        background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
        color: white !important;
        border-radius: 12px;
        border: none;
        padding: 12px 24px;
        font-size: 20px;
        font-weight: 800;
        letter-spacing: 1px;
        box-shadow: 0px 8px 15px rgba(255, 75, 43, 0.3);
        transition: all 0.3s ease 0s;
        width: 100%;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0px 12px 20px rgba(255, 75, 43, 0.5);
    }
    
    /* Sidebar Styling tweaks */
    [data-testid="stSidebar"] {
        background-color: rgba(128, 128, 128, 0.03);
        border-right: 1px solid rgba(128, 128, 128, 0.2);
    }
</style>
""", unsafe_allow_html=True)


# --- TELEGRAM SETUP ---
TELEGRAM_TOKEN = "8657774899:AAGKqx2_TgaoYAbUljSAXt5l9BzL_cnyCPE"
TELEGRAM_CHAT_ID = "8900320752"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload, timeout=5)
    except: pass

st.markdown('<p class="main-title">🎯 F&O Options Sniper</p>', unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray; font-size: 16px; font-weight: 600;'>(Multi-Index | Bollinger Squeeze | Auto-Strike | Pro Risk Manager)</p>", unsafe_allow_html=True)
st.markdown("---")

JOURNAL_FILE = "options_journal.csv"

# --- THE THREE KINGS (Indices Data) ---
INDICES = {
    "^NSEI": {"name": "NIFTY 50", "lot_size": 25, "step": 50},
    "^NSEBANK": {"name": "BANKNIFTY", "lot_size": 15, "step": 100},
    "^BSESN": {"name": "SENSEX", "lot_size": 10, "step": 100}
}

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

def get_ist_time():
    return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- THE SNIPER LOGIC (Bollinger Squeeze + Momentum) ---
def analyze_index_options(symbol, info, risk_amt):
    try:
        data = yf.Ticker(symbol, session=session).history(period="5d", interval="5m")
        if len(data) < 30: return None
        
        data['MA20'] = data['Close'].rolling(window=20).mean()
        data['STD'] = data['Close'].rolling(window=20).std()
        data['Upper_BB'] = data['MA20'] + (2 * data['STD'])
        data['Lower_BB'] = data['MA20'] - (2 * data['STD'])
        
        data['Bandwidth'] = (data['Upper_BB'] - data['Lower_BB']) / data['MA20']
        data['RSI'] = calculate_rsi(data['Close'])
        
        last = data.iloc[-1]
        prev = data.iloc[-2]
        live_price = last['Close']
        
        step = info['step']
        atm_strike = int(round(live_price / step) * step)
        
        is_squeeze = prev['Bandwidth'] < 0.003
        
        signal = None
        action_text = ""
        
        if is_squeeze and live_price > last['Upper_BB'] and last['RSI'] > 60:
            signal = f"{info['name']} {atm_strike} CE"
            action_text = "🟢 BUY CE"
            sl_spot = last['MA20']
            tgt_spot = live_price + (live_price - sl_spot) * 2.5
            
        elif is_squeeze and live_price < last['Lower_BB'] and last['RSI'] < 40:
            signal = f"{info['name']} {atm_strike} PE"
            action_text = "🔴 BUY PE"
            sl_spot = last['MA20']
            tgt_spot = live_price - (sl_spot - live_price) * 2.5
            
        if signal:
            spot_risk = abs(live_price - sl_spot)
            premium_risk = spot_risk * 0.5 
            risk_per_lot = premium_risk * info['lot_size']
            
            ideal_lots = int(risk_amt / risk_per_lot) if risk_per_lot > 0 else 1
            if ideal_lots < 1: ideal_lots = 1
            
            return {
                "Index": info['name'],
                "Signal": signal,
                "Action": action_text,
                "Lots": f"📦 {ideal_lots} Lots",
                "Total Qty": ideal_lots * info['lot_size'],
                "Spot Price": f"₹{round(live_price, 2)}",
                "Target (Spot)": f"₹{round(tgt_spot, 2)}",
                "SL (Spot)": f"₹{round(sl_spot, 2)}",
                "Status": "⚡ Active"
            }
            
    except Exception as e:
        pass
    return None

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🚀 Live Pro Scanner", "📓 Audit & Journal"])

st.sidebar.markdown("### ⚙️ Institutional Risk Manager")
capital = st.sidebar.number_input("F&O Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk_pct = st.sidebar.slider("Max Risk per Trade (%)", min_value=1, max_value=5, value=2)
max_loss = st.sidebar.number_input("Max Daily Loss (₹) Kill Switch", min_value=1000, value=2000, step=500)

risk_per_trade = capital * (risk_pct / 100)

st.sidebar.markdown("---")
st.sidebar.success(f"💼 Allowed Risk Per Trade: **₹{risk_per_trade}**")
st.sidebar.info("🛰️ **Live Radars:**\n- NIFTY 50\n- BANKNIFTY\n- SENSEX")

with tab1:
    # High-Speed Market Weather Cards
    col1, col2, col3 = st.columns(3)
    try:
        n_data = yf.Ticker("^NSEI").history(period="1d")['Close'].iloc[-1]
        b_data = yf.Ticker("^NSEBANK").history(period="1d")['Close'].iloc[-1]
        s_data = yf.Ticker("^BSESN").history(period="1d")['Close'].iloc[-1]
        
        col1.metric("📌 NIFTY 50", f"{round(n_data, 2)}")
        col2.metric("🏦 BANKNIFTY", f"{round(b_data, 2)}")
        col3.metric("📊 SENSEX", f"{round(s_data, 2)}")
    except: pass
    
    st.write("<br>", unsafe_allow_html=True) # Adds a little clean spacing
    auto_mode = st.checkbox("🤖 ENABLE AI AUTO-PILOT (Scans silently every 2 Mins)", value=False)
    
    st.write("<br>", unsafe_allow_html=True)
    manual_scan = st.button("🔥 DEPLOY SNIPER SQUADS (SCAN NOW)")
    st.write("<br>", unsafe_allow_html=True)
    
    if auto_mode or manual_scan:
        now = get_ist_time().time()
        start_time, end_time = datetime.time(9, 15), datetime.time(15, 15)
        lunch_start, lunch_end = datetime.time(11, 45), datetime.time(13, 15)
        
        if not (start_time <= now <= end_time):
            st.warning("⚠️ Market Offline! Sniper rests outside 9:15 AM - 3:15 PM.")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
        elif lunch_start <= now <= lunch_end:
            st.error("🍔 Lunch Time Lock! Sniper avoids Theta Decay (Sideways Market).")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
        else:
            with st.spinner("📡 Intercepting Market Data..."):
                results = []
                for symbol, info in INDICES.items():
                    trade = analyze_index_options(symbol, info, risk_per_trade)
                    if trade: results.append(trade)
            
            if results:
                st.balloons()
                st.success(f"🚨 TARGETS ACQUIRED! Found {len(results)} Explosive Breakout(s).")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
                
                for res in results:
                    msg = f"💥 {res['Action']} ALERT!\n🎯 {res['Signal']}\n{res['Lots']} ({res['Total Qty']} Qty)\n🛡️ SL: {res['SL (Spot)']}\n🚀 TGT: {res['Target (Spot)']}"
                    send_telegram_alert(msg)
            else:
                st.info("🧘‍♂️ Market is choppy. Zero setups found. Sniper is waiting for the perfect shot.")
                
            if auto_mode:
                time.sleep(120)
                st.rerun()

with tab2:
    st.subheader("🛡️ Pro-Trader Doctrine")
    st.info("""
    **The 4 Pillars of Option Buying:**
    1. **Wait for the Squeeze:** Options only make money when the market explodes out of a tight range. 
    2. **Spot is God:** Premium charts are manipulated by operators. Always follow the Index Spot levels for SL and Target.
    3. **Protect the Capital:** Surviving to trade tomorrow is more important than catching a risky trade today.
    4. **Avoid the Middle:** Never trade between 11:45 AM and 1:15 PM.
    """)
