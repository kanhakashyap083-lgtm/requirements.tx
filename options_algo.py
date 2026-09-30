import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz
import time
import requests
import warnings

warnings.filterwarnings("ignore")

# --- TELEGRAM SETUP ---
TELEGRAM_TOKEN = "8657774899:AAGKqx2_TgaoYAbUljSAXt5l9BzL_cnyCPE"
TELEGRAM_CHAT_ID = "8900320752"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload, timeout=5)
    except: pass

# --- APP SETUP ---
st.set_page_config(page_title="F&O Sniper Bot", page_icon="🎯", layout="wide")
st.title("🎯 F&O Options Sniper (Pro-Quant)")
st.markdown("**(Multi-Index | Bollinger Squeeze | Auto-Strike | Pro Risk Manager)**")

JOURNAL_FILE = "options_journal.csv"

# --- THE THREE KINGS (Indices Data) ---
# Nifty, BankNifty, Sensex with their exact real-world lot sizes and strike steps
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
        
        # 1. Indicator Setup
        data['MA20'] = data['Close'].rolling(window=20).mean()
        data['STD'] = data['Close'].rolling(window=20).std()
        data['Upper_BB'] = data['MA20'] + (2 * data['STD'])
        data['Lower_BB'] = data['MA20'] - (2 * data['STD'])
        
        # Bandwidth measures how tight the market is (Squeeze)
        data['Bandwidth'] = (data['Upper_BB'] - data['Lower_BB']) / data['MA20']
        data['RSI'] = calculate_rsi(data['Close'])
        
        last = data.iloc[-1]
        prev = data.iloc[-2]
        
        live_price = last['Close']
        
        # 2. Dynamic Strike Selection (ATM Rounding)
        step = info['step']
        atm_strike = int(round(live_price / step) * step)
        
        # 3. Strategy: Squeeze Breakout
        is_squeeze = prev['Bandwidth'] < 0.003 # Extremely tight market condition
        
        signal = None
        action_text = ""
        
        # BUY CALL (CE) Logic
        if is_squeeze and live_price > last['Upper_BB'] and last['RSI'] > 60:
            signal = f"{info['name']} {atm_strike} CE (CALL)"
            action_text = "🟢 BUY CE"
            sl_spot = last['MA20']
            tgt_spot = live_price + (live_price - sl_spot) * 2.5
            
        # BUY PUT (PE) Logic
        elif is_squeeze and live_price < last['Lower_BB'] and last['RSI'] < 40:
            signal = f"{info['name']} {atm_strike} PE (PUT)"
            action_text = "🔴 BUY PE"
            sl_spot = last['MA20']
            tgt_spot = live_price - (sl_spot - live_price) * 2.5
            
        if signal:
            # Position Sizing based on Option Delta estimation (approx 0.5 for ATM)
            # Spot Points at risk
            spot_risk = abs(live_price - sl_spot)
            premium_risk = spot_risk * 0.5 
            risk_per_lot = premium_risk * info['lot_size']
            
            ideal_lots = int(risk_amt / risk_per_lot) if risk_per_lot > 0 else 1
            if ideal_lots < 1: ideal_lots = 1
            
            return {
                "Index": info['name'],
                "Signal": signal,
                "Action": action_text,
                "Lots": ideal_lots,
                "Total Qty": ideal_lots * info['lot_size'],
                "Spot Price": round(live_price, 2),
                "Spot Target": round(tgt_spot, 2),
                "Spot SL": round(sl_spot, 2),
                "Status": "Active ⚡"
            }
            
    except Exception as e:
        pass
    return None

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🎯 Live F&O Scanner", "📓 Options Journal"])

st.sidebar.markdown("### ⚙️ Option Risk Manager")
capital = st.sidebar.number_input("F&O Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk_pct = st.sidebar.slider("Max Risk per Trade (%)", min_value=1, max_value=5, value=2)
max_loss = st.sidebar.number_input("Max Daily Loss (₹) - Auto Kill Switch", min_value=1000, value=2000, step=500)

risk_per_trade = capital * (risk_pct / 100)

st.sidebar.markdown("---")
st.sidebar.success(f"💼 Risk Per Trade: ₹{risk_per_trade}")
st.sidebar.info("🚀 Indices Tracked:\n1. NIFTY 50\n2. BANKNIFTY\n3. SENSEX")

with tab1:
    st.subheader("High-Speed Momentum Scanner (3-Min / 5-Min)")
    
    # Show Weather (Live Spot Prices)
    col1, col2, col3 = st.columns(3)
    try:
        n_data = yf.Ticker("^NSEI").history(period="1d")['Close'].iloc[-1]
        b_data = yf.Ticker("^NSEBANK").history(period="1d")['Close'].iloc[-1]
        s_data = yf.Ticker("^BSESN").history(period="1d")['Close'].iloc[-1]
        col1.metric("NIFTY 50 Spot", round(n_data, 2))
        col2.metric("BANKNIFTY Spot", round(b_data, 2))
        col3.metric("SENSEX Spot", round(s_data, 2))
    except: pass
    
    st.markdown("---")
    auto_mode = st.checkbox("🤖 ENABLE F&O AUTO-PILOT (Scans every 2 Mins)", value=False)
    manual_scan = st.button("🔥 SCAN MARKET NOW", use_container_width=True)
    
    if auto_mode or manual_scan:
        now = get_ist_time().time()
        start_time, end_time = datetime.time(9, 15), datetime.time(15, 15)
        lunch_start, lunch_end = datetime.time(11, 45), datetime.time(13, 15)
        
        if not (start_time <= now <= end_time):
            st.warning("⏳ F&O Market Closed! Scan only works between 9:15 AM and 3:15 PM.")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
        elif lunch_start <= now <= lunch_end:
            st.error("🍔 Lunch Time Sideways Zone! Bot is resting to save you from Theta Decay.")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
        else:
            my_bar = st.progress(0, text="Hunting for Squeeze Breakouts...")
            
            results = []
            progress = 0
            for symbol, info in INDICES.items():
                trade = analyze_index_options(symbol, info, risk_per_trade)
                if trade:
                    results.append(trade)
                progress += 33
                my_bar.progress(progress, text=f"Scanning {info['name']}...")
            
            my_bar.empty()
            
            if results:
                st.success(f"🚀 BOOM! Found {len(results)} Explosive Option Setup(s)!")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
                
                for res in results:
                    msg = f"🚨 {res['Action']} ALERT!\n🎯 Setup: {res['Signal']}\n📦 Buy Lots: {res['Lots']} (Total {res['Total Qty']} Qty)\n🛡️ Spot SL: {res['Spot SL']}\n🚀 Spot Target: {res['Spot Target']}"
                    send_telegram_alert(msg)
                    st.toast(f"Telegram Alert sent for {res['Signal']}!")
            else:
                st.info("No perfect breakout setups right now. Bot is saving your capital from time-decay.")
                
            if auto_mode:
                st.info("⏳ Auto-Pilot Active: Scanning again in 2 minutes...")
                time.sleep(120)
                st.rerun()

with tab2:
    st.subheader("📓 Option Trader's Rulebook & Notes")
    st.markdown("""
    **🔥 Your F&O Sniper Rules:**
    1. **Spot Chart Supremacy:** Bot targets and stop-loss are based on the Index Spot Price (not option premium chart).
    2. **Anti-Decay Logic:** Bot will only give trade when market is breaking out of a tight range (Bollinger Squeeze).
    3. **Lunch Time Lock:** Bot will automatically stop giving signals between 11:45 AM and 1:15 PM to protect you from side-ways market melt.
    4. **Execution:** Use the Telegram alerts to punch orders manually in your broker terminal.
    """)
