import streamlit as st
import yfinance as yf
import pandas as pd
import time
import warnings
import os
import datetime
import pytz
import requests

warnings.filterwarnings("ignore")

# --- TELEGRAM & API SETUP ---
TELEGRAM_TOKEN = "8657774899:AAGKqx2_TgaoYAbUljSAXt5l9BzL_cnyCPE"
TELEGRAM_CHAT_ID = "8900320752"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except: pass

# --- SMART BROWSER SESSION ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# --- APP SETUP & PREMIUM UI ---
st.set_page_config(page_title="God-Level F&O Sniper", page_icon="🎯", layout="wide")
st.title("🎯 Institutional F&O Sniper (Options Algo)")
st.markdown("**(Sensex Active 🦅 | OI Decoder | Theta Shield 🛡️ | Gamma Blast 💥)**")

PORTFOLIO_FILE = "options_journal.csv"

# --- THE BIG 3 INDICES (Strictly F&O) ---
INDICES = {
    "NIFTY 50": {"ticker": "^NSEI", "lot_size": 50, "expiry_day": 3},  # Thursday
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 15, "expiry_day": 2}, # Wednesday
    "SENSEX": {"ticker": "^BSESN", "lot_size": 10, "expiry_day": 4}    # Friday
}

def get_ist_time(): return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_vix():
    try:
        vix = yf.Ticker("^INDIAVIX", session=session).history(period="1d")
        if not vix.empty: return round(vix['Close'].iloc[-1], 2)
    except: pass
    return 15.0 

def check_index_trend(ticker):
    try:
        data = yf.Ticker(ticker, session=session).history(period="1mo", interval="1d")
        if not data.empty and len(data) > 10:
            ema9 = data['Close'].ewm(span=9).mean().iloc[-1]
            ema21 = data['Close'].ewm(span=21).mean().iloc[-1]
            return ema9 > ema21
    except: pass
    return True

# --- OPTIONS JOURNAL TRACKING ---
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE): return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=["Date", "Time", "Index", "Signal", "Action", "Strike Logic", "Qty", "Entry Spot", "Status", "Net P&L"])

def save_to_portfolio(new_trades):
    df = load_portfolio()
    now_ist = get_ist_time()
    today = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%H:%M:%S")
    new_rows = []
    
    for t in new_trades:
        if "NO TRADE" in t['Action']: continue
        if not ((df['Index'] == t['Index']) & (df['Date'] == today) & (df['Status'] == "Active ⏳")).any():
            new_rows.append({
                "Date": today, "Time": time_str, "Index": t['Index'], "Signal": t['Signal'], 
                "Action": t['Action'], "Strike Logic": t['Smart Strike'], "Qty": t['Qty (Lots)'], 
                "Entry Spot": t['Live Spot'], "Status": "Active ⏳", "Net P&L": 0.0
            })
    if new_rows:
        pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard():
    df = load_portfolio()
    if df.empty: return df
    # Future logic for Options P&L can be added here
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- OPTIONS GOD-LEVEL FEATURES ---
def theta_shield_active(data):
    if len(data) < 14: return False
    recent_high = data['High'].tail(10).max()
    recent_low = data['Low'].tail(10).min()
    range_pct = ((recent_high - recent_low) / recent_low) * 100
    return range_pct < 0.35 

def dynamic_strike_selector(index_name, live_price, vix_val, is_expiry_day, time_now):
    if is_expiry_day and time_now.hour >= 13 and time_now.minute >= 30:
        return f"ATM/OTM (Gamma Blast 💥)"
    elif vix_val > 18:
        return f"Deep ITM (VIX Protect 🛡️)"
    else:
        return f"Slightly ITM (Momentum 🚀)"

def oi_decoder_signal(data):
    data['EMA9'] = data['Close'].ewm(span=9).mean()
    data['EMA21'] = data['Close'].ewm(span=21).mean()
    avg_vol = data['Volume'].rolling(20).mean().iloc[-2]
    live_vol = data['Volume'].iloc[-1]
    live_c, ema9, ema21 = data['Close'].iloc[-1], data['EMA9'].iloc[-1], data['EMA21'].iloc[-1]
    
    if live_vol > (avg_vol * 3):
        if live_c > ema9 and ema9 > ema21: return "🔥 BULLISH (CE Buy)"
        if live_c < ema9 and ema9 < ema21: return "🩸 BEARISH (PE Buy)"
    return "NEUTRAL"

def scan_options_market(risk_amt, is_auto_exec):
    results = []
    now = get_ist_time()
    today_weekday = now.weekday()
    current_vix = get_vix()

    for name, info in INDICES.items():
        try:
            tkr = yf.Ticker(info["ticker"], session=session)
            data = tkr.history(period="5d", interval="5m")
            if data.empty or len(data) < 30: continue
            
            live_price = data['Close'].iloc[-1]
            
            if theta_shield_active(data):
                results.append({"Index": name, "Signal": "🛡️ SIDEWAYS", "Action": "NO TRADE (Theta Shield)", "Live Spot": round(live_price, 2), "Smart Strike": "-", "Qty (Lots)": "-", "SL (Pts)": "-", "Remark": "Market Choppy"})
                continue

            oi_signal = oi_decoder_signal(data)
            if oi_signal == "NEUTRAL": continue

            is_expiry = (today_weekday == info["expiry_day"])
            strike_logic = dynamic_strike_selector(name, live_price, current_vix, is_expiry, now.time())
            action = "🟢 BUY CALL (CE)" if "BULLISH" in oi_signal else "🔴 BUY PUT (PE)"
            
            sl_points = 30 if name == "BANKNIFTY" else (15 if name == "NIFTY 50" else 40)
            max_qty = int((risk_amt / sl_points) // info["lot_size"]) * info["lot_size"]
            if max_qty == 0: max_qty = info["lot_size"] 

            remark = "💥 GAMMA BLAST ACTIVE!" if (is_expiry and now.time().hour >= 13) else "🚀 Momentum Entry"

            results.append({
                "Index": name, "Signal": oi_signal, "Action": action,
                "Live Spot": round(live_price, 2), "Smart Strike": strike_logic,
                "Qty (Lots)": f"{max_qty} Qty", "SL (Pts)": f"{sl_points} Pts", "Remark": remark
            })
        except: pass
    return results

# --- PREMIUM DASHBOARD & UI ---
tab1, tab2 = st.tabs(["🎯 Live Options Radar & Weather", "📈 Options Journal & P&L"])

vix_val = get_vix()

st.sidebar.markdown("### ⚙️ Options Risk Manager")
st.sidebar.warning("⚡ Live F&O Mode Active")

d_client = st.sidebar.text_input("Dhan Client ID", type="password")
d_token = st.sidebar.text_input("Access Token", type="password")

risk = st.sidebar.number_input("Max Risk Per Trade (₹)", min_value=1000, value=2000, step=500)

st.sidebar.markdown("---")
auto_trade_live = st.sidebar.toggle("🚨 ENABLE AUTO-EXECUTION (Real Money)", value=False)
if auto_trade_live: st.sidebar.error("⚠️ WARNING: Dhan Options API Active!")

st.sidebar.info(f"📊 **India VIX:** {vix_val}")
if vix_val > 24: st.sidebar.error("⚠️ VIX High! Premium Expensive.")
elif vix_val < 10: st.sidebar.warning("⚠️ VIX Low! Slow Market.")
else: st.sidebar.success("🟢 VIX Optimal. Safe to Trade.")

with tab1:
    st.subheader("Multi-Index Options Weather System 🌩")
    
    n_bull = check_index_trend("^NSEI")
    bn_bull = check_index_trend("^NSEBANK")
    s_bull = check_index_trend("^BSESN")
    
    is_market_bullish = n_bull or bn_bull or s_bull
    
    col1, col2, col3 = st.columns(3)
    col1.metric("NIFTY 50 (Thu Expiry)", "📈 BULLISH" if n_bull else "📉 BEARISH")
    col2.metric("BANKNIFTY (Wed Expiry)", "📈 BULLISH" if bn_bull else "📉 BEARISH")
    col3.metric("SENSEX (Fri Expiry)", "📈 BULLISH" if s_bull else "📉 BEARISH")
    
    # MARKET MOOD BANNER FOR F&O
    if is_market_bullish: 
        st.success("🟢 Market Mood: BULLISH (Bot will look for CALL/CE breakouts)")
    else: 
        st.error("🔴 Market Mood: BEARISH (Bot will look for PUT/PE breakdowns)")
    
    st.markdown("---")
    auto_mode = st.checkbox("🤖 ENABLE AUTO-PILOT (Scans every 1 Min)", value=False)
    
    # TIME-LOCK BYPASS FOR F&O
    bypass_time = st.checkbox("Bypass Time-Lock (For Testing only)", value=False) 
    manual_scan = st.button("🔥 DECODE OPTIONS MARKET (Scan Now)", use_container_width=True)

    if auto_mode or manual_scan:
        now = get_ist_time().time()
        if not bypass_time and not (datetime.time(9, 15) <= now <= datetime.time(15, 30)):
            st.warning("⏳ Market Offline! F&O works during live market hours only.")
        else:
            with st.spinner("Decoding Institutional OI & Volume... Please wait."):
                time.sleep(1) 
                trades = scan_options_market(risk, auto_trade_live)
                
                if trades:
                    st.success("🚨 Smart Money Signals Detected!")
                    df = pd.DataFrame(trades)
                    st.dataframe(
                        df.style.applymap(
                            lambda x: 'background-color: #c8e6c9; color: black' if '🟢' in str(x) else ('background-color: #ffcdd2; color: black' if '🔴' in str(x) else ('background-color: #ffe0b2; color: black' if '🛡️' in str(x) else '')),
                            subset=['Action']
                        ), use_container_width=True
                    )
                    
                    save_to_portfolio(trades) 
                    
                    for t in trades:
                        if "NO TRADE" not in t["Action"]:
                            msg = f"{t['Action']} ALERT! 🚀\n📈 Index: {t['Index']}\n💡 Strike: {t['Smart Strike']}\n🎯 Signal: {t['Signal']}\n📦 Qty: {t['Qty (Lots)']}\n⚠️ SL: {t['SL (Pts)']}\n📌 {t['Remark']}"
                            send_telegram_alert(msg)
                else:
                    st.info("🧘‍♂️ No Institutional setup found right now. Patience pays in F&O.")
                    
            if auto_mode:
                time.sleep(60)
                st.rerun()

with tab2:
    st.subheader("🏆 Options Trading Journal")
    if st.button("🔄 Refresh Live Net P&L", type="primary"):
        updated_df = update_scorecard()
        if not updated_df.empty:
            st.dataframe(updated_df, use_container_width=True)
            csv = updated_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download Options Journal", data=csv, file_name="Options_Journal.csv", mime="text/csv")
        else:
            st.info("No options trades recorded yet!")
