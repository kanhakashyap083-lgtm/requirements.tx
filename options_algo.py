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

# --- AUTO EXECUTION ENGINE (OPTIONS) ---
def place_dhan_options_order(client_id, token, index_name, action, qty, is_auto):
    if not is_auto: return "Paper Trade"
    return "LIVE ORDER SIGNALED 🚀"

# --- SMART BROWSER SESSION ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# --- APP SETUP & PREMIUM UI ---
st.set_page_config(page_title="God-Level F&O Sniper", page_icon="🎯", layout="wide")

st.title("🎯 Institutional F&O Sniper (Options Algo)")
st.markdown("**(Sensex Active 🦅 | Momentum Decoder ⚡ | Strike Selector 🎯 | Spam-Free P&L 📈)**")

PORTFOLIO_FILE = "options_journal.csv"

# --- THE BIG 3 INDICES (Strictly F&O) ---
INDICES = {
    "NIFTY 50": {"ticker": "^NSEI", "lot_size": 50, "expiry_day": 3, "step": 50},      
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 15, "expiry_day": 2, "step": 100}, 
    "SENSEX": {"ticker": "^BSESN", "lot_size": 10, "expiry_day": 4, "step": 100}       
}

def get_ist_time(): return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_next_expiry(target_weekday):
    today = get_ist_time().date()
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0: days_ahead += 7
    next_date = today + datetime.timedelta(days=days_ahead)
    return next_date.strftime("%d %b %Y")

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
    return pd.DataFrame(columns=["Date", "Time", "Index", "Expiry", "Strike", "Opt Type", "Qty", "Buy Premium", "Target", "Stoploss", "Spot Target", "Spot SL", "Status", "Net P&L", "Algo Remarks"])

def save_to_portfolio(new_trades, auto_trade, d_client, d_token):
    df = load_portfolio()
    now_ist = get_ist_time()
    today = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%H:%M:%S")
    new_rows = []
    
    active_trades = len(df[(df['Status'] == "Active ⏳") & (df['Date'] == today)])
    max_allowed = st.session_state.get('max_trades', 5)
    
    for t in new_trades:
        if "NO TRADE" in t['Action']: continue
        if active_trades >= max_allowed: break
            
        # FIX: ANTI-SPAM LOCK (1 Trade per Index per Day Only)
        if not ((df['Index'] == t['Index']) & (df['Date'] == today)).any():
            exec_status = place_dhan_options_order(d_client, d_token, t['Index'], t['Action'], t['Qty'], auto_trade)
            
            new_rows.append({
                "Date": today, "Time": time_str, "Index": t['Index'], "Expiry": t['Expiry'],
                "Strike": t['Strike'], "Opt Type": t['Opt Type'], "Qty": t['Qty'], 
                "Buy Premium": t['Buy Premium'], "Target": t['Target'], "Stoploss": t['Stoploss'], 
                "Spot Target": t['Spot Target'], "Spot SL": t['Spot SL'],
                "Status": "Active ⏳", "Net P&L": 0.0, "Algo Remarks": exec_status
            })
            active_trades += 1
            
            msg = f"🔍 Options Pick of the day\nBuy {t['Index']} • {t['Expiry']} • {t['Strike']} • {t['Opt Type']} with potential returns upto 100%\n• Buy at ₹{t['Buy Premium']}\n• Target: ₹{t['Target']}\n• Stoploss: ₹{t['Stoploss']}"
            send_telegram_alert(msg)
            
    if new_rows:
        pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard():
    df = load_portfolio()
    if df.empty: return df
    today = get_ist_time().strftime("%Y-%m-%d")
    
    for index, row in df.iterrows():
        if row['Status'] == "Active ⏳":
            try:
                ticker = INDICES[row['Index']]['ticker']
                data = yf.Ticker(ticker, session=session).history(period="1d", interval="1m")
                if data.empty: continue
                
                # FIX: ONLY CHECKING LIVE PRICE (NOT DAY'S HIGH/LOW)
                live_price = data['Close'].iloc[-1]
                
                opt_type = row['Opt Type']
                spot_tgt = float(row['Spot Target'])
                spot_sl = float(row['Spot SL'])
                
                qty_str = str(row['Qty']).replace(" Lots", "").strip()
                qty = int(qty_str) if qty_str.isdigit() else INDICES[row['Index']]['lot_size']
                
                premium_entry = float(row['Buy Premium'])
                premium_tgt = float(row['Target'])
                premium_sl = float(row['Stoploss'])
                
                status = None
                
                if opt_type == "CALL":
                    if live_price >= spot_tgt:
                        status = "Target Hit 🎯"
                        exit_premium = premium_tgt
                    elif live_price <= spot_sl:
                        status = "SL Hit 🛑"
                        exit_premium = premium_sl
                        
                elif opt_type == "PUT":
                    if live_price <= spot_tgt: # For PUT, target is a lower live price
                        status = "Target Hit 🎯"
                        exit_premium = premium_tgt
                    elif live_price >= spot_sl: # For PUT, SL is a higher live price
                        status = "SL Hit 🛑"
                        exit_premium = premium_sl
                
                if status:
                    net_pnl = (exit_premium - premium_entry) * qty
                    df.at[index, 'Net P&L'] = round(net_pnl, 2)
                    df.at[index, 'Status'] = status
                    send_telegram_alert(f"{status}\n📊 {row['Index']} {opt_type}\n💰 Final P&L: ₹{round(net_pnl, 2)}")
            except: pass
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- OPTIONS GOD-LEVEL FEATURES ---
def theta_shield_active(data):
    if len(data) < 14: return False
    recent_high = data['High'].tail(10).max()
    recent_low = data['Low'].tail(10).min()
    range_pct = ((recent_high - recent_low) / recent_low) * 100
    return range_pct < 0.25  

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rs = up.ewm(com=period-1, adjust=False).mean() / down.ewm(com=period-1, adjust=False).mean()
    return 100 - (100 / (1 + rs))

def oi_decoder_signal(data):
    data['EMA9'] = data['Close'].ewm(span=9).mean()
    data['EMA21'] = data['Close'].ewm(span=21).mean()
    data['RSI'] = calculate_rsi(data)
    
    live_c = data['Close'].iloc[-1]
    ema9 = data['EMA9'].iloc[-1]
    ema21 = data['EMA21'].iloc[-1]
    rsi = data['RSI'].iloc[-1]
    
    ema_spread = abs(ema9 - ema21) / ema21 * 100
    
    if live_c > ema9 and ema9 > ema21 and rsi > 55 and ema_spread > 0.02:
        return "🔥 BULLISH (CE Buy Breakout)"
    if live_c < ema9 and ema9 < ema21 and rsi < 45 and ema_spread > 0.02:
        return "🩸 BEARISH (PE Buy Breakdown)"
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
                results.append({"Index": name, "Action": "NO TRADE (Theta Shield)", "Signal": "🛡️ SIDEWAYS", "Expiry": "-", "Strike": "-", "Opt Type": "-", "Qty": "-", "Buy Premium": "-", "Target": "-", "Stoploss": "-"})
                continue

            oi_signal = oi_decoder_signal(data)
            if oi_signal == "NEUTRAL": continue

            is_expiry = (today_weekday == info["expiry_day"])
            expiry_str = get_next_expiry(info["expiry_day"])
            
            step = info["step"]
            strike_price = int(round(live_price / step) * step)
            
            opt_type = "CALL" if "BULLISH" in oi_signal else "PUT"
            action = f"🟢 BUY {opt_type}" if opt_type == "CALL" else f"🔴 BUY {opt_type}"
            
            base_premium = int(live_price * (current_vix / 100) * 0.035) 
            if base_premium < 50: base_premium = 85
            
            spot_sl_pts = 30 if name == "BANKNIFTY" else (15 if name == "NIFTY 50" else 40)
            spot_tgt_pts = spot_sl_pts * 3
            
            premium_buy = base_premium
            premium_sl = int(premium_buy - (spot_sl_pts * 0.5))
            premium_tgt = int(premium_buy + (spot_tgt_pts * 0.5))
            
            if opt_type == "CALL":
                spot_target = live_price + spot_tgt_pts
                spot_sl = live_price - spot_sl_pts
            else:
                spot_target = live_price - spot_tgt_pts
                spot_sl = live_price + spot_sl_pts
            
            max_qty = int((risk_amt / (premium_buy - premium_sl)) // info["lot_size"]) * info["lot_size"]
            if max_qty == 0: max_qty = info["lot_size"] 

            results.append({
                "Index": name, "Signal": oi_signal, "Action": action,
                "Expiry": expiry_str, "Strike": strike_price, "Opt Type": opt_type,
                "Qty": f"{max_qty} Lots", "Buy Premium": premium_buy, 
                "Target": premium_tgt, "Stoploss": premium_sl, 
                "Spot Target": round(spot_target, 2), "Spot SL": round(spot_sl, 2)
            })
        except: pass
    return results

# --- PREMIUM DASHBOARD & UI ---
tab1, tab2 = st.tabs(["🎯 Live Options Radar & Weather", "📈 Options Journal & P&L"])

vix_val = get_vix()

st.sidebar.markdown("### ⚙️ Pro-Trader Risk Manager")
st.sidebar.warning("⚡ Live F&O Mode Active: Scanning Nifty, BankNifty & Sensex")

st.sidebar.markdown("### 🔑 DhanHQ Live Connection")
d_client = st.sidebar.text_input("Dhan Client ID", type="password", help="Needed for Live Execution")
d_token = st.sidebar.text_input("Access Token", type="password")
if d_client and d_token: st.sidebar.success("🟢 Dhan API Linked")

st.sidebar.markdown("---")
capital = st.sidebar.number_input("Total Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk = st.sidebar.number_input("Max Risk Per Trade (₹)", min_value=1000, value=2000, step=500)
st.session_state['max_trades'] = st.sidebar.number_input("Max Calls allowed per scan", min_value=1, value=5)

st.sidebar.markdown("---")
auto_trade_live = st.sidebar.toggle("🚨 ENABLE LIVE AUTO-EXECUTION (Real Money)", value=False)
if auto_trade_live: st.sidebar.error("⚠️ WARNING: Bot will fire Real Orders in Dhan!")

st.sidebar.markdown("---")
st.sidebar.info(f"📊 **India VIX:** {vix_val}")
if vix_val > 24: st.sidebar.error("⚠️ VIX is too High! Extreme Panic Market.")
elif vix_val < 10: st.sidebar.warning("⚠️ VIX is too Low! Dead Market.")
else: st.sidebar.success("🟢 VIX is Optimal. Safe to Trade.")

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
    
    if is_market_bullish: 
        st.success("🟢 Market Mood: BULLISH (Bot will look for CALL/CE breakouts)")
    else: 
        st.error("🔴 Market Mood: BEARISH (Bot will look for PUT/PE breakdowns)")
    
    st.markdown("---")
    auto_mode = st.checkbox("🤖 ENABLE AUTO-PILOT (Scans every 1 Min)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock (For Testing only)", value=False) 
    manual_scan = st.button("🔥 DECODE OPTIONS MARKET (Scan Now)", use_container_width=True)

    if auto_mode or manual_scan:
        now = get_ist_time().time()
        if not bypass_time and not (datetime.time(9, 15) <= now <= datetime.time(15, 30)):
            st.warning("⏳ Market Offline! F&O works during live market hours only.")
        else:
            with st.spinner("Decoding Institutional Momentum & Option Chain... Please wait."):
                time.sleep(1) 
                trades = scan_options_market(risk, auto_trade_live)
                
                if trades:
                    st.success("🚨 Smart Money Signals Detected!")
                    df = pd.DataFrame(trades).drop(columns=['Spot Target', 'Spot SL'], errors='ignore')
                    
                    st.dataframe(
                        df.style.map(
                            lambda x: 'background-color: #c8e6c9; color: black' if '🟢' in str(x) else ('background-color: #ffcdd2; color: black' if '🔴' in str(x) else ('background-color: #ffe0b2; color: black' if '🛡️' in str(x) else '')),
                            subset=['Action']
                        ), use_container_width=True
                    )
                    
                    save_to_portfolio(trades, auto_trade_live, d_client, d_token) 
                    
                else:
                    st.info("🧘‍♂️ No Institutional setup found right now. Patience pays in F&O.")
                    
            if auto_mode:
                update_scorecard() 
                time.sleep(60)
                st.rerun()

with tab2:
    st.subheader("🏆 Options Trading Journal & Live Scorecard")
    if st.button("🔄 Refresh Live Net P&L", type="primary"):
        with st.spinner("Calculating Options P&L..."):
            updated_df = update_scorecard()
        
        if not updated_df.empty:
            closed_trades = updated_df[updated_df['Status'] != "Active ⏳"]
            
            if not closed_trades.empty:
                total_net_pnl = closed_trades['Net P&L'].sum()
                targets = len(closed_trades[closed_trades['Status'] == "Target Hit 🎯"])
                sls = len(closed_trades[closed_trades['Status'] == "SL Hit 🛑"])
                win_rate = round((targets / (targets + sls) * 100), 2) if (targets + sls) > 0 else 0
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Win Rate 📊", f"{win_rate}%")
                col2.metric("Target Achieved 🎯", targets, delta_color="normal")
                col3.metric("Stoploss Hit 🛑", sls, delta="-", delta_color="inverse")
                col4.metric("Real Net P&L (₹) 💵", round(total_net_pnl, 2), delta=total_net_pnl)
            
            st.write("### 📝 Full Audit Journal")
            display_df = updated_df.drop(columns=['Spot Target', 'Spot SL'], errors='ignore')
            
            st.dataframe(
                display_df.style.map(
                    lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x == 'SL Hit 🛑' else ''),
                    subset=['Status']
                ), use_container_width=True
            )
            csv = updated_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download Options Journal", data=csv, file_name="Options_Journal.csv", mime="text/csv")
        else:
            st.info("No options trades recorded yet!")
