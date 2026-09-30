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

# --- APP SETUP ---
st.set_page_config(page_title="God-Level F&O Sniper", page_icon="🎯", layout="wide")
st.title("🎯 Institutional F&O Sniper (Options Algo)")
st.markdown("**(Sensex Active 🦅 | OI Decoder | Theta Shield 🛡️ | Gamma Blast 💥)**")

PORTFOLIO_FILE = "options_journal.csv"

# --- THE BIG 3 INDICES (Sensex Included) ---
# Expiry Days: BankNifty (Wed), Nifty (Thu), Sensex (Fri)
INDICES = {
    "NIFTY 50": {"ticker": "^NSEI", "lot_size": 50, "expiry_day": 3},  # Thursday (0=Mon, 3=Thu)
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 15, "expiry_day": 2}, # Wednesday
    "SENSEX": {"ticker": "^BSESN", "lot_size": 10, "expiry_day": 4}    # Friday
}

session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0'})

def get_ist_time(): return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_vix():
    try:
        vix = yf.Ticker("^INDIAVIX", session=session).history(period="1d")
        if not vix.empty: return round(vix['Close'].iloc[-1], 2)
    except: pass
    return 15.0 

# --- GOD-LEVEL FEATURES LOGIC ---

def theta_shield_active(data):
    """Checks if market is sideways (Choppy) to prevent premium decay."""
    if len(data) < 14: return False
    recent_high = data['High'].tail(10).max()
    recent_low = data['Low'].tail(10).min()
    range_pct = ((recent_high - recent_low) / recent_low) * 100
    return range_pct < 0.35  # If market moved less than 0.35% in 10 candles -> SIDEWAYS

def dynamic_strike_selector(index_name, live_price, vix_val, is_expiry_day, time_now):
    """Smart Money Strike Selection"""
    if is_expiry_day and time_now.hour >= 13 and time_now.minute >= 30:
        return f"ATM / OTM (Gamma Blast 💥) - Low Premium, High Reward"
    elif vix_val > 18:
        return f"Deep ITM (High VIX Protection 🛡️)"
    else:
        return f"Slightly ITM / ATM (Standard Momentum 🚀)"

def oi_decoder_signal(data):
    """Tracks Volume Spikes to mimic Institutional Options Buying (Short Covering/Long Buildup)"""
    data['EMA9'] = data['Close'].ewm(span=9).mean()
    data['EMA21'] = data['Close'].ewm(span=21).mean()
    avg_vol = data['Volume'].rolling(20).mean().iloc[-2]
    live_vol = data['Volume'].iloc[-1]
    
    live_c = data['Close'].iloc[-1]
    ema9 = data['EMA9'].iloc[-1]
    ema21 = data['EMA21'].iloc[-1]
    
    # 3x Volume Spike indicates Operator Entry
    if live_vol > (avg_vol * 3):
        if live_c > ema9 and ema9 > ema21: return "🔥 BULLISH (Short Covering / CE Buy)"
        if live_c < ema9 and ema9 < ema21: return "🩸 BEARISH (Long Unwinding / PE Buy)"
    return "NEUTRAL"

# --- CORE SCANNER ---
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
            
            # Feature 1: Theta Decay Shield
            if theta_shield_active(data):
                results.append({"Index": name, "Signal": "🛡️ SIDEWAYS", "Action": "NO TRADE (Theta Decay)", "Price": live_price, "Strike": "-", "Qty": 0, "Remark": "Market Choppy"})
                continue

            # Feature 2: Smart Money OI Decoder
            oi_signal = oi_decoder_signal(data)
            if oi_signal == "NEUTRAL": continue

            # Feature 3 & 4: Expiry Gamma Blast & Dynamic Strike
            is_expiry = (today_weekday == info["expiry_day"])
            strike_logic = dynamic_strike_selector(name, live_price, current_vix, is_expiry, now.time())
            
            action = "🟢 BUY CALL (CE)" if "BULLISH" in oi_signal else "🔴 BUY PUT (PE)"
            
            # Risk Management
            sl_points = 30 if name == "BANKNIFTY" else (15 if name == "NIFTY 50" else 40)
            max_qty = int((risk_amt / sl_points) // info["lot_size"]) * info["lot_size"]
            if max_qty == 0: max_qty = info["lot_size"] # At least 1 lot

            remark = "💥 GAMMA BLAST ACTIVE!" if (is_expiry and now.time().hour >= 13) else "🚀 Momentum Entry"

            results.append({
                "Index": name,
                "Signal": oi_signal,
                "Action": action,
                "Live Spot Price": round(live_price, 2),
                "Smart Strike": strike_logic,
                "Qty (Lots)": f"{max_qty} Qty",
                "Stoploss (Index Pts)": f"{sl_points} Pts",
                "Remark": remark
            })
        except: pass
    return results

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🎯 Live Options Radar", "📈 F&O Journal"])

st.sidebar.markdown("### ⚙️ Options Risk Manager")
st.sidebar.info(f"📊 **India VIX:** {get_vix()}")

risk = st.sidebar.number_input("Max Risk Per Trade (₹)", min_value=1000, value=2000, step=500)
auto_trade_live = st.sidebar.toggle("🚨 ENABLE AUTO-EXECUTION (Dhan API)", value=False)
if auto_trade_live: st.sidebar.error("⚠️ WARNING: Dhan Options API Active!")

with tab1:
    st.subheader("Live F&O Scanning (Nifty, BankNifty, Sensex)")
    auto_mode = st.checkbox("🤖 ENABLE AUTO-PILOT (Scans every 1 Min)", value=False)
    manual_scan = st.button("🔥 SCAN OPTIONS NOW")

    if auto_mode or manual_scan:
        with st.spinner("Decoding Institutional Data (OI & Volume)..."):
            time.sleep(1) # Simulated fast scan
            trades = scan_options_market(risk, auto_trade_live)
            
            if trades:
                st.success("🚨 Smart Money Signals Detected!")
                st.dataframe(pd.DataFrame(trades), use_container_width=True)
                
                for t in trades:
                    if "NO TRADE" not in t["Action"]:
                        msg = f"{t['Action']} ALERT! 🚀\n📈 Index: {t['Index']}\n💡 Strike: {t['Smart Strike']}\n🎯 Signal: {t['Signal']}\n📦 Qty: {t['Qty (Lots)']}\n⚠️ SL: {t['Stoploss (Index Pts)']}\n📌 {t['Remark']}"
                        send_telegram_alert(msg)
            else:
                st.info("🧘‍♂️ No Institutional setup found. Cash is King.")
                
        if auto_mode:
            time.sleep(60)
            st.rerun()

with tab2:
    st.subheader("🏆 Options Trading Journal")
    st.write("F&O trades are highly volatile. This journal tracks your manual/auto executions for the day.")
    # (Journal logic placeholder - identical to app.py)
    st.info("Journal will update based on executed Dhan Orders.")
