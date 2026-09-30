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

st.markdown("""
<style>
    .main-title {
        text-align: center;
        font-size: 45px;
        font-weight: 900;
        background: -webkit-linear-gradient(45deg, #00FFA3, #03E1FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    [data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.1);
        border-radius: 12px;
        padding: 15px 20px;
        box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.05);
        border-left: 6px solid #00FFA3;
    }
    .stButton > button {
        background: linear-gradient(135deg, #00FFA3 0%, #03E1FF 100%);
        color: black !important;
        border-radius: 12px;
        border: none;
        padding: 12px 24px;
        font-size: 20px;
        font-weight: 800;
        box-shadow: 0px 8px 15px rgba(0, 255, 163, 0.3);
        width: 100%;
        transition: all 0.3s ease 0s;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
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

st.markdown('<p class="main-title">🎯 F&O Options Sniper (Pro)</p>', unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray; font-size: 16px; font-weight: 600;'>(Powered by DhanHQ Zero-Delay API ⚡)</p>", unsafe_allow_html=True)
st.markdown("---")

# --- THE THREE KINGS (Indices Data) ---
INDICES = {
    "^NSEI": {"name": "NIFTY 50", "dhan_id": "13", "exch": "IDX_I", "lot_size": 25, "step": 50},
    "^NSEBANK": {"name": "BANKNIFTY", "dhan_id": "25", "exch": "IDX_I", "lot_size": 15, "step": 100},
    "^BSESN": {"name": "SENSEX", "dhan_id": "51", "exch": "IDX_I", "lot_size": 10, "step": 100}
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

# --- LIVE HIGH-SPEED DATA ENGINE ---
def fetch_data(symbol, info, client_id, token):
    if client_id and token:
        try:
            url = "https://api.dhan.co/v2/charts/intraday"
            now = get_ist_time()
            past = now - datetime.timedelta(days=5)
            payload = {
                "securityId": str(info["dhan_id"]),
                "exchangeSegment": info["exch"],
                "instrument": "INDEX",
                "interval": "5",
                "fromDate": past.strftime("%Y-%m-%d"),
                "toDate": now.strftime("%Y-%m-%d")
            }
            headers = {"access-token": token, "client-id": client_id, "Content-Type": "application/json"}
            resp = requests.post(url, json=payload, headers=headers, timeout=5).json()
            if resp.get("status") == "success" and "data" in resp:
                d = resp["data"]
                df = pd.DataFrame({"Close": d.get("close", []), "High": d.get("high", []), "Low": d.get("low", []), "Open": d.get("open", [])})
                if len(df) > 30: return df, "DhanHQ API ⚡"
        except: pass
    
    try:
        df = yf.Ticker(symbol, session=session).history(period="5d", interval="5m")
        if len(df) > 30: return df, "Yahoo (Delayed ⚠️)"
    except: pass
    return None, "Offline"

def get_latest_price(symbol, info, client_id, token):
    try:
        df, _ = fetch_data(symbol, info, client_id, token)
        if df is not None and not df.empty:
            return df['Close'].iloc[-1]
    except: pass
    return 0.0

# --- THE SNIPER LOGIC ---
def analyze_index_options(symbol, info, risk_amt, client_id, token):
    try:
        data, source = fetch_data(symbol, info, client_id, token)
        if data is None: return None
        
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
        
        signal, action_text = None, ""
        
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
            ideal_lots = max(1, int(risk_amt / risk_per_lot)) if risk_per_lot > 0 else 1
            total_qty = ideal_lots * info['lot_size']
            
            return {
                "Index": info['name'],
                "Signal": signal,
                "Action": action_text,
                "Lots": f"📦 {ideal_lots} Lots",
                "Total Qty": total_qty,
                "Spot Price": f"₹{round(live_price, 2)}",
                "Target": f"₹{round(tgt_spot, 2)}",
                "SL": f"₹{round(sl_spot, 2)}",
                "Data Feed": source
            }
    except: pass
    return None

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🚀 Live Pro Scanner", "📓 Audit & Journal"])

st.sidebar.markdown("### 🔑 DhanHQ Live Connection")
d_client_id = st.sidebar.text_input("Dhan Client ID", type="password", help="Enter your Dhan Client ID")
d_token = st.sidebar.text_input("Access Token", type="password", help="Paste today's token here")

if d_client_id and d_token:
    st.sidebar.success("🟢 Dhan API Connected (Zero Delay)")
else:
    st.sidebar.warning("⚠️ Using Yahoo Data (Delayed). Enter details above for Live Action.")

st.sidebar.markdown("### ⚙️ Pro Risk Manager")
capital = st.sidebar.number_input("Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk_pct = st.sidebar.slider("Risk per Trade (%)", min_value=0.5, max_value=2.0, value=1.0, step=0.5)
risk_per_trade = capital * (risk_pct / 100)
st.sidebar.success(f"💼 Allowed Risk Per Trade: **₹{risk_per_trade}**")

with tab1:
    # 📌 TOP METRIC CARDS (Fixed & Added Back)
    c1, c2, c3 = st.columns(3)
    p_nifty = get_latest_price("^NSEI", INDICES["^NSEI"], d_client_id, d_token)
    p_bank = get_latest_price("^NSEBANK", INDICES["^NSEBANK"], d_client_id, d_token)
    p_sen = get_latest_price("^BSESN", INDICES["^BSESN"], d_client_id, d_token)
    
    c1.metric("📌 NIFTY 50 Spot", f"₹{round(p_nifty, 2)}" if p_nifty else "Offline")
    c2.metric("🏦 BANKNIFTY Spot", f"₹{round(p_bank, 2)}" if p_bank else "Offline")
    c3.metric("📊 SENSEX Spot", f"₹{round(p_sen, 2)}" if p_sen else "Offline")
    
    st.write("<br>", unsafe_allow_html=True)
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
            if auto_mode: time.sleep(60); st.rerun()
        elif lunch_start <= now <= lunch_end:
            st.error("🍔 Lunch Time Lock! Sniper avoids Theta Decay (Sideways Market).")
            if auto_mode: time.sleep(60); st.rerun()
        else:
            with st.spinner("📡 Intercepting Market Data..."):
                results = []
                for symbol, info in INDICES.items():
                    trade = analyze_index_options(symbol, info, risk_per_trade, d_client_id, d_token)
                    if trade: results.append(trade)
            
            if results:
                st.balloons()
                st.success(f"🚨 TARGETS ACQUIRED! Found {len(results)} Explosive Breakout(s).")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
                for res in results:
                    # 📌 Quantity added back in Telegram Alert
                    msg = f"💥 {res['Action']} ALERT!\n🎯 {res['Signal']}\n{res['Lots']} (Qty: {res['Total Qty']})\n🛡️ SL: {res['SL']}\n🚀 TGT: {res['Target']}\n📡 Source: {res['Data Feed']}"
                    send_telegram_alert(msg)
            else:
                st.info("🧘‍♂ Market is choppy. Zero setups found. Sniper is waiting for the perfect shot.")
                
            if auto_mode:
                time.sleep(120)
                st.rerun()
                
with tab2:
    st.subheader("🛡️ Pro-Trader Doctrine")
    st.info("""
    **The 4 Pillars of Option Buying:**
    1. **Wait for the Squeeze:** Options only make money when the market explodes out of a tight range. 
    2. **Spot is God:** Premium charts are manipulated. Always follow the Index Spot levels for SL and Target.
    3. **Protect the Capital:** Surviving to trade tomorrow is more important than catching a risky trade today.
    4. **Avoid the Middle:** Never trade between 11:45 AM and 1:15 PM (Theta Decay zone).
    """)
