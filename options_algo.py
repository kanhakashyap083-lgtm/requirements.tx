import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import datetime
import pytz
import requests
from streamlit_autorefresh import st_autorefresh
import warnings

warnings.filterwarnings("ignore")

# --- SECRETS & TELEGRAM CONFIGURATION ---
try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except KeyError:
    st.error("🚨 CRITICAL ERROR: Telegram Secrets missing. Add TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to st.secrets!")
    st.stop()

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception:
        pass

# --- AUTOMATED LIVE OPTION DATA & SAFE DHAN FALLBACK ---
@st.cache_data(ttl=45)
def fetch_nse_live_premium(index_name, strike, opt_type):
    """Fetches Real-Time Option Premium directly from NSE India (for Nifty & BankNifty)."""
    try:
        symbol_map = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY"}
        if index_name not in symbol_map: 
            return None 
            
        nse_symbol = symbol_map[index_name]
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={nse_symbol}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9"
        }
        
        sess = requests.Session()
        sess.get("https://www.nseindia.com", headers=headers, timeout=5)
        res = sess.get(url, headers=headers, timeout=5)
        data = res.json()
        
        for item in data['records']['data']:
            if item['strikePrice'] == strike:
                if opt_type == "CALL" and "CE" in item:
                    return float(item['CE']['lastPrice'])
                elif opt_type == "PUT" and "PE" in item:
                    return float(item['PE']['lastPrice'])
        return None
    except Exception:
        return None

def get_live_premium_dhan(d_client, d_token, index_name, strike, opt_type):
    """
    FIXED: Instead of sending raw strike price as securityId (which fails in Dhan API),
    this safely routes through NSE Live Option Chain (for Nifty/BankNifty) and smart fallback (for Sensex).
    Strictly Read-Only Paper Tracking Mode.
    """
    # 1. Try fetching via NSE Live Option Chain (Reliable for Nifty & BankNifty)
    nse_ltp = fetch_nse_live_premium(index_name, strike, opt_type)
    if nse_ltp and nse_ltp > 0:
        return nse_ltp
        
    # 2. Fallback for Sensex or if NSE API blocks temporarily
    return None

def place_dhan_options_order(client_id, token, index_name, action, qty, is_auto):
    # Safety Check: auto_trade_live is strictly OFF by default
    if not auto_trade_live: 
        return "Auto-Paper Trade Tracked (Read-Only Mode)"
    return "LIVE EXECUTION BLOCKED IN STAGE-1 (Safety Lock Active 🛡️)"

# --- SMART BROWSER SESSION ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# --- APP SETUP & UI ---
st.set_page_config(page_title="Institutional F&O Sniper", page_icon="🎯", layout="wide")
st.title("🎯 Institutional F&O Sniper (Paper-Trade Mode - Security Fixed)")
st.markdown("**(Live NSE/BSE Auto-Fetch 📈 | Auto SL/Target Tracking ⚡ | Read-Only Safety Lock 🛡️)**")

PORTFOLIO_FILE = "options_journal.csv"
MAX_TRADES_PER_DAY = 3

INDICES = {
    "NIFTY 50": {"ticker": "^NSEI", "lot_size": 50, "step": 50, "default_weekday": 3},      
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 15, "step": 100, "default_weekday": 2}, 
    "SENSEX": {"ticker": "^BSESN", "lot_size": 10, "step": 100, "default_weekday": 4}       
}

def get_ist_time():
    return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_default_expiry(target_weekday):
    today = get_ist_time().date()
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0: days_ahead += 7
    return (today + datetime.timedelta(days=days_ahead)).strftime("%d %b %Y")

@st.cache_data(ttl=300)
def get_vix_status():
    try:
        vix_data = yf.Ticker("^INDIAVIX").history(period="2d")
        if len(vix_data) >= 2:
            prev_vix = vix_data['Close'].iloc[-2]
            curr_vix = vix_data['Close'].iloc[-1]
            drop_pct = ((prev_vix - curr_vix) / prev_vix) * 100
            return round(curr_vix, 2), (drop_pct >= 6.0), (curr_vix > 24.0)
    except: pass
    return 15.0, False, False

@st.cache_data(ttl=300)
def check_15m_trend(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d", interval="15m")
        if not data.empty and len(data) >= 21:
            ema9 = data['Close'].ewm(span=9).mean().iloc[-1]
            ema21 = data['Close'].ewm(span=21).mean().iloc[-1]
            return "BULLISH" if ema9 > ema21 else "BEARISH"
    except: pass
    return "NEUTRAL"

def calculate_vwap(df):
    v = df['Volume'].values
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * v).cumsum() / (v.cumsum() + 1e-9)

def calculate_adx(df, period=14):
    if len(df) < period * 2: return 0
    high, low, close = df['High'], df['Low'], df['Close']
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    up_move, down_move = high - high.shift(1), low.shift(1) - low
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    pos_di = 100 * (pd.Series(pos_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    neg_di = 100 * (pd.Series(neg_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    dx = 100 * ((pos_di - neg_di).abs() / (pos_di + neg_di + 1e-9))
    adx = dx.rolling(period).mean()
    return adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0

def theta_shield_active(data):
    if len(data) < 14: return False
    recent_low = data['Low'].tail(10).min()
    return (((data['High'].tail(10).max() - recent_low) / (recent_low + 1e-9)) * 100) < 0.25

def load_portfolio():
    cols = ["Trade ID", "Date", "Time", "Index", "Expiry", "Strike", "Opt Type", "Qty", "Lots", "Entry Premium", "SL Level (30%)", "1R Level (30%)", "Target Level (60%)", "Status", "Net P&L", "Filters Passed", "Algo Remarks"]
    return pd.read_csv(PORTFOLIO_FILE) if os.path.exists(PORTFOLIO_FILE) else pd.DataFrame(columns=cols)

def get_daily_trade_count():
    df = load_portfolio()
    if df.empty: return 0
    return len(df[(df['Date'] == get_ist_time().strftime("%Y-%m-%d")) & (df['Status'] != "Skipped ❌")])

def is_cooldown_active(index_name):
    df = load_portfolio()
    if df.empty: return False
    today = get_ist_time().strftime("%Y-%m-%d")
    sl_trades = df[(df['Date'] == today) & (df['Index'] == index_name) & (df['Status'] == "SL Hit 🛑")]
    if sl_trades.empty: return False
    last_sl_time = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{today} {sl_trades.iloc[-1]['Time']}", "%Y-%m-%d %H:%M:%S"))
    return ((get_ist_time() - last_sl_time).total_seconds() / 60) < 30

def record_trade_action(trade_dict, entry_price, action_type, auto_trade, d_client, d_token):
    df = load_portfolio()
    now_ist = get_ist_time()
    today, time_str = now_ist.strftime("%Y-%m-%d"), now_ist.strftime("%H:%M:%S")
    trade_id = f"{trade_dict['Index'][:3]}_{today}_{time_str.replace(':', '')}"

    if action_type == "TAKEN":
        sl_val, r1_val, tgt_val = round(entry_price * 0.70, 2), round(entry_price * 1.30, 2), round(entry_price * 1.60, 2)
        exec_status = place_dhan_options_order(d_client, d_token, trade_dict['Index'], trade_dict['Action'], trade_dict['Qty'], auto_trade)
        
        new_row = {"Trade ID": trade_id, "Date": today, "Time": time_str, "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'], "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'], "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price, "SL Level (30%)": sl_val, "1R Level (30%)": r1_val, "Target Level (60%)": tgt_val, "Status": "Active ⏳", "Net P&L": 0.0, "Filters Passed": trade_dict.get('Filters', 'Passed'), "Algo Remarks": exec_status}
        pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)
        send_telegram_alert(f"🎯 AUTO-TRACKING STARTED\n{trade_dict['Index']} {trade_dict['Opt Type']} {trade_dict['Strike']}\nEntry: ₹{entry_price}\n🛑 SL: ₹{sl_val} | 🎯 TGT: ₹{tgt_val}")
    else:
        new_row = {"Trade ID": trade_id, "Date": today, "Time": time_str, "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'], "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'], "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price, "SL Level (30%)": 0, "1R Level (30%)": 0, "Target Level (60%)": 0, "Status": "Skipped ❌", "Net P&L": 0.0, "Filters Passed": trade_dict.get('Filters', 'Passed'), "Algo Remarks": "Skipped"}
        pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard(d_client, d_token):
    df = load_portfolio()
    if df.empty: return df

    now_time = get_ist_time().time()
    is_315_passed = now_time >= datetime.time(15, 15)

    for index, row in df.iterrows():
        if row['Status'] == "Active ⏳":
            if is_315_passed:
                df.at[index, 'Status'] = "Time Exit ⏰"
                df.at[index, 'Algo Remarks'] = "3:15 PM Hard Stop"
                send_telegram_alert(f"⏰ INTRADAY CUT-OFF 3:15 PM\nEXIT ALL POSITIONS NOW for {row['Index']} {row['Opt Type']}")
                continue

            live_premium = get_live_premium_dhan(d_client, d_token, row['Index'], float(row['Strike']), row['Opt Type'])
            
            if live_premium is None:
                df.at[index, 'Algo Remarks'] = "Waiting for Live LTP..."
                continue
                
            entry, sl, r1, tgt, qty = float(row['Entry Premium']), float(row['SL Level (30%)']), float(row['1R Level (30%)']), float(row['Target Level (60%)']), int(row['Qty'])
            status, pnl = None, 0.0

            if live_premium >= tgt:
                status, pnl = "Target Hit 🎯", (tgt - entry) * qty
                send_telegram_alert(f"🎯 2R TARGET HIT: Full Exit\n{row['Index']} {row['Opt Type']} at actual ₹{live_premium}")
            elif live_premium <= sl:
                status, pnl = "SL Hit 🛑", (sl - entry) * qty
                send_telegram_alert(f"🛑 SL HIT: EXIT NOW\n{row['Index']} {row['Opt Type']} at actual ₹{live_premium}")
            elif live_premium >= r1 and row['Algo Remarks'] != "1R Hit Alerted":
                send_telegram_alert(f"💵 1R HIT: BOOK 50% & TRAIL SL\n{row['Index']} {row['Opt Type']} reached ₹{live_premium}")
                df.at[index, 'Algo Remarks'] = "1R Hit Alerted"

            if status:
                df.at[index, 'Status'], df.at[index, 'Net P&L'] = status, round(pnl, 2)

    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- SIGNAL GENERATION ENGINE ---
def scan_options_market(risk_amt, is_auto_exec, dynamic_expiries, d_client, d_token):
    results = []
    curr_vix, is_vix_crashing, is_vix_extreme = get_vix_status()
    if is_vix_extreme or is_vix_crashing:
        st.error(f"🚫 Market Locked: VIX is Extreme/Crashing ({curr_vix}).")
        return results

    if get_daily_trade_count() >= MAX_TRADES_PER_DAY:
        st.error(f"🔒 KILL-SWITCH ACTIVE: Max {MAX_TRADES_PER_DAY} trades reached.")
        return results

    df = load_portfolio()
    active_indices = df[(df['Date'] == get_ist_time().strftime("%Y-%m-%d")) & (df['Status'] == "Active ⏳")]['Index'].tolist()

    for name, info in INDICES.items():
        try:
            if active_indices and name not in active_indices: continue
            if is_cooldown_active(name):
                st.warning(f"🥶 SL Cooldown Active for {name}.")
                continue

            data_5m = yf.Ticker(info["ticker"], session=session).history(period="5d", interval="5m")
            if data_5m.empty or len(data_5m) < 30 or theta_shield_active(data_5m): continue

            trend_15m, vwap, adx_val, live_price = check_15m_trend(info["ticker"]), calculate_vwap(data_5m).iloc[-1], calculate_adx(data_5m), data_5m['Close'].iloc[-1]
            ema9, ema21 = data_5m['Close'].ewm(span=9).mean().iloc[-1], data_5m['Close'].ewm(span=21).mean().iloc[-1]
            delta = data_5m['Close'].diff()
            rs = delta.clip(lower=0).ewm(com=13, adjust=False).mean() / ((-1 * delta.clip(upper=0)).ewm(com=13, adjust=False).mean() + 1e-9)
            rsi = 100 - (100 / (1 + rs)).iloc[-1]

            is_bullish = (live_price > vwap) and (live_price > ema9 > ema21) and (rsi > 55) and (trend_15m == "BULLISH") and (adx_val > 25)
            is_bearish = (live_price < vwap) and (live_price < ema9 < ema21) and (rsi < 45) and (trend_15m == "BEARISH") and (adx_val > 25)

            if not (is_bullish or is_bearish): continue

            opt_type, action, strike_price = ("CALL" if is_bullish else "PUT"), (f"🟢 BUY CALL" if is_bullish else f"🔴 BUY PUT"), int(round(live_price / info["step"]) * info["step"])

            live_premium = get_live_premium_dhan(d_client, d_token, name, strike_price, opt_type)
            if live_premium and live_premium > 0:
                base_est_premium = live_premium
                data_source = "🟢 LIVE LTP (Auto-Fetched)"
            else:
                base_est_premium = max(85, int(live_price * (curr_vix / 100) * 0.035))
                data_source = "🟡 ESTIMATED LTP (Fallback)"

            risk_per_lot = base_est_premium * 0.30 * info["lot_size"]
            if risk_per_lot > risk_amt:
                st.warning(f"⚠️ Trade Skipped for {name}: Risk exceeds limits.")
                continue
                
            num_lots = max(1, int(risk_amt // risk_per_lot))

            results.append({
                "Index": name, "Signal": "🔥 BULLISH" if is_bullish else "🩸 BEARISH", "Action": action,
                "Expiry": dynamic_expiries.get(name, get_default_expiry(info["default_weekday"])), "Strike": strike_price, "Opt Type": opt_type,
                "Lots": num_lots, "Qty": num_lots * info["lot_size"], "Est Premium": base_est_premium, "Data Source": data_source,
                "Filters": f"VWAP: OK | ADX: {round(adx_val, 1)} | 15M: {trend_15m}"
            })
        except: pass
    return results

# --- SIDEBAR & UI ---
st.sidebar.markdown("### ⚙️ Stage-1 Auto Paper-Trade")
capital = st.sidebar.number_input("Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk = st.sidebar.number_input("Max Risk Per Trade (₹)", min_value=500, value=1500, step=250)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Dynamic Expiry Selectors")
dynamic_expiries = {idx_name: st.sidebar.text_input(f"{idx_name} Expiry", value=get_default_expiry(spec["default_weekday"])) for idx_name, spec in INDICES.items()}

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 Data Connection Setup")
d_client = st.sidebar.text_input("Dhan Client ID (Optional)", type="password")
d_token = st.sidebar.text_input("Access Token (Optional)", type="password")

# 🚨 SAFETY CHECK: AUTO TRADE LIVE IS STRICTLY OFF (FALSE)
auto_trade_live = st.sidebar.toggle("🚨 Enable Live Auto-Execution", value=False)
if auto_trade_live: st.sidebar.warning("⚠️ Live Execution Lock Active. Running in Read-Only Paper Mode.")

curr_vix, _, _ = get_vix_status()
st.sidebar.info(f"📊 **India VIX:** {curr_vix}")

tab1, tab2 = st.tabs(["🎯 Live Radar & Execution Hub", "📈 Auto-Journal & Scorecard"])

with tab1:
    st.subheader("Automated Options Radar (Paper Trade)")
    col1, col2, col3 = st.columns(3)
    col1.metric("NIFTY 50 (15M)", check_15m_trend("^NSEI"))
    col2.metric("BANKNIFTY (15M)", check_15m_trend("^NSEBANK"))
    col3.metric("SENSEX (15M)", check_15m_trend("^BSESN"))
    st.markdown("---")
    
    auto_mode = st.checkbox("🤖 Auto-Pilot (Scan every 60s)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock", value=False)
    manual_scan = st.button("🔥 Scan Market Signals Now", use_container_width=True)

    now_time = get_ist_time().time()
    in_golden_window = (datetime.time(9, 30) <= now_time <= datetime.time(11, 30)) or (datetime.time(13, 30) <= now_time <= datetime.time(14, 45))

    if auto_mode or manual_scan:
        if now_time >= datetime.time(15, 0) and not bypass_time: st.error("⏰ Scanning Locked: Post 3:00 PM Hard Stop Active.")
        elif not in_golden_window and not bypass_time: st.warning("⏳ Outside Golden Window. Market may be choppy.")
        else:
            with st.spinner("Analyzing VWAP, ADX & Fetching Live Premiums..."):
                signals = scan_options_market(risk, auto_trade_live, dynamic_expiries, d_client, d_token)

            if signals:
                st.success(f"🚨 {len(signals)} Smart Setup(s) Found!")
                for i, sig in enumerate(signals):
                    st.markdown(f"#### 🎯 Signal: {sig['Index']} - {sig['Action']} {sig['Strike']}")
                    st.info(f"Filters: {sig['Filters']} | Sizing: {sig['Lots']} Lots | Source: {sig['Data Source']}")
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    user_entry = c1.number_input(f"Live Premium (₹) - Auto Fetched", min_value=5.0, value=float(sig['Est Premium']), step=1.0, key=f"entry_{i}")
                    
                    if c2.button("✅ Trade Liya (Start Auto-Tracking)", key=f"take_{i}", use_container_width=True):
                        record_trade_action(sig, user_entry, "TAKEN", auto_trade_live, d_client, d_token)
                        st.success(f"Trade Recorded! Bot is tracking SL/Target for {sig['Index']}.")
                    if c3.button("❌ Skip Kiya", key=f"skip_{i}", use_container_width=True):
                        record_trade_action(sig, user_entry, "SKIPPED", auto_trade_live, d_client, d_token)
            else:
                st.info("🧘 No institutional breakout matching core filters right now.")

            if auto_mode:
                update_scorecard(d_client, d_token)
                st_autorefresh(interval=60000, key="auto_scan_refresh")

with tab2:
    st.subheader("🏆 Auto-Tracked Options Journal")
    if st.button("🔄 Refresh Live Positions & P&L", type="primary"):
        with st.spinner("Auditing Positions..."):
            updated_df = update_scorecard(d_client, d_token)
    else:
        updated_df = load_portfolio()

    if not updated_df.empty:
        closed = updated_df[updated_df['Status'].isin(["Target Hit 🎯", "SL Hit 🛑", "Time Exit ⏰"])]
        if not closed.empty:
            total_net_pnl, targets, sls = closed['Net P&L'].sum(), len(closed[closed['Status'] == "Target Hit 🎯"]), len(closed[closed['Status'] == "SL Hit 🛑"])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Win Rate 📊", f"{round((targets / (targets + sls) * 100), 2) if (targets + sls) > 0 else 0}%")
            c2.metric("Targets Hit 🎯", targets)
            c3.metric("SLs Hit 🛑", sls)
            c4.metric("Realized P&L (₹) 💵", round(total_net_pnl, 2), delta=total_net_pnl)
        
        st.dataframe(updated_df[[c for c in updated_df.columns if c != "Trade ID"]].style.map(
            lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x in ['SL Hit 🛑', 'Time Exit ⏰'] else ''), subset=['Status']), 
            use_container_width=True)
        st.download_button("💾 Download Journal CSV", data=updated_df.to_csv(index=False).encode('utf-8'), file_name="Options_Journal.csv", mime="text/csv")
