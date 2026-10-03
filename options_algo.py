import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
import datetime
import calendar
import pytz
import requests
from streamlit_autorefresh import st_autorefresh
import warnings

warnings.filterwarnings("ignore")

# --- GLOBAL ERROR STATE & TELEGRAM ---
if 'api_error_count' not in st.session_state:
    st.session_state.api_error_count = 0
if 'last_error_time' not in st.session_state:
    st.session_state.last_error_time = None

try:
    TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
    TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except KeyError:
    st.error("🚨 CRITICAL ERROR: Telegram Secrets missing. Add TELEGRAM_TOKEN and TELEGRAM_CHAT_ID to st.secrets!")
    st.stop()

def get_ist_time():
    return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5)
    except Exception as e:
        print(f"Telegram Alert Failed: {e}")

def log_and_alert_error(msg):
    st.session_state.api_error_count += 1
    now = get_ist_time()
    print(f"ERROR LOG: {msg}")
    if st.session_state.last_error_time is None or (now - st.session_state.last_error_time).total_seconds() > 3600:
        send_telegram_alert(f"⚠️ SYSTEM ERROR WARNING: {msg}")
        st.session_state.last_error_time = now

# --- INDICES & EXPIRIES ---
INDICES = {
    "NIFTY 50": {"ticker": "^NSEI", "lot_size": 65, "step": 50, "expiry_type": "weekly", "weekday": 1},      # Tue
    "BANKNIFTY": {"ticker": "^NSEBANK", "lot_size": 30, "step": 100, "expiry_type": "monthly", "weekday": 1}, # Last Tue
    "SENSEX": {"ticker": "^BSESN", "lot_size": 20, "step": 100, "expiry_type": "weekly", "weekday": 3}        # Thu
}

def get_weekly_expiry(target_weekday):
    today = get_ist_time().date()
    days_ahead = target_weekday - today.weekday()
    if days_ahead < 0: days_ahead += 7
    return (today + datetime.timedelta(days=days_ahead)).strftime("%d-%b-%Y")

def get_monthly_expiry(target_weekday):
    today = get_ist_time().date()
    def last_day_of_month(y, m, w):
        last_day = calendar.monthrange(y, m)[1]
        last_date = datetime.date(y, m, last_day)
        offset = (last_date.weekday() - w) % 7
        return last_date - datetime.timedelta(days=offset)
    
    expiry = last_day_of_month(today.year, today.month, target_weekday)
    if today > expiry:
        if today.month == 12: expiry = last_day_of_month(today.year + 1, 1, target_weekday)
        else: expiry = last_day_of_month(today.year, today.month + 1, target_weekday)
    return expiry.strftime("%d-%b-%Y")

# --- DATA FETCHING & API CALLS ---
@st.cache_data(ttl=86400)
def fetch_dhan_master_cached():
    df = pd.read_csv("https://images.dhan.co/api-data/api-scrip-master.csv", low_memory=False)
    if df.empty: raise ValueError("Downloaded Dhan CSV is empty")
    return df[df['SEM_INSTRUMENT_NAME'] == 'OPTIDX']

def get_dhan_security_id(index_name, strike, opt_type, expiry_str):
    try:
        df = fetch_dhan_master_cached()
        sym = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}.get(index_name)
        target_date = datetime.datetime.strptime(expiry_str, "%d-%b-%Y").date()
        opt = "CE" if opt_type == "CALL" else "PE"
        
        match = df[(df['SEM_CUSTOM_SYMBOL'].str.startswith(sym, na=False)) & (df['SEM_STRIKE_PRICE'] == float(strike)) & (df['SEM_OPTION_TYPE'] == opt)]
        for _, row in match.iterrows():
            if str(target_date) == str(row['SEM_EXPIRY_DATE']).split(' ')[0]:
                return int(row['SEM_SMST_SECURITY_ID'])
    except Exception as e:
        log_and_alert_error(f"Dhan Scrip Master Error: {e}")
    return None

@st.cache_data(ttl=45)
def fetch_nse_live_premium(index_name, strike, opt_type, target_expiry):
    try:
        symbol_map = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY"}
        if index_name not in symbol_map: return None 
        nse_symbol = symbol_map[index_name]
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={nse_symbol}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/option-chain"
        }
        
        sess = requests.Session()
        sess.get("https://www.nseindia.com", headers=headers, timeout=5)
        res = sess.get(url, headers=headers, timeout=5).json()
        
        for item in res['records']['data']:
            if item['strikePrice'] == strike and item['expiryDate'].lower() == target_expiry.lower():
                key = "CE" if opt_type == "CALL" else "PE"
                if key in item: return float(item[key]['lastPrice'])
        return None
    except Exception as e:
        log_and_alert_error(f"NSE Option Chain Error: {e}")
        return None

def get_live_premium_dhan(d_client, d_token, index_name, strike, opt_type, expiry):
    nse_ltp = fetch_nse_live_premium(index_name, strike, opt_type, expiry)
    if nse_ltp and nse_ltp > 0: return nse_ltp
        
    if d_client and d_token:
        sec_id = get_dhan_security_id(index_name, strike, opt_type, expiry)
        if sec_id:
            try:
                exchange_seg = "BSE_FNO" if index_name == "SENSEX" else "NSE_FNO"
                headers = {"access-token": d_token, "client-id": d_client, "Content-Type": "application/json", "Accept": "application/json"}
                payload = {exchange_seg: [int(sec_id)]} 
                
                import time
                time.sleep(1.05) 
                
                res = requests.post("https://api.dhan.co/v2/marketfeed/ltp", headers=headers, json=payload, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    ltp = data.get('data', {}).get(exchange_seg, {}).get(str(sec_id), {}).get('last_price')
                    if ltp: return float(ltp)
                else:
                    log_and_alert_error(f"Dhan API Error {res.status_code}: {res.text}")
            except Exception as e:
                log_and_alert_error(f"Dhan Request Error: {e}")
    return None

@st.cache_data(ttl=300)
def get_vix_data_cached():
    return yf.Ticker("^INDIAVIX").history(period="2d")

def get_vix_status():
    try:
        vix_data = get_vix_data_cached()
        if not vix_data.empty and len(vix_data) >= 2:
            prev_vix = vix_data['Close'].iloc[-2]
            curr_vix = vix_data['Close'].iloc[-1]
            return round(curr_vix, 2), (((prev_vix - curr_vix) / prev_vix) * 100 >= 6.0), (curr_vix > 24.0)
    except Exception as e:
        log_and_alert_error(f"VIX Fetch Failed: {e}")
    return None, False, False 

@st.cache_data(ttl=300)
def check_15m_trend(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d", interval="15m")
        if not data.empty and len(data) >= 21:
            ema9, ema21 = data['Close'].ewm(span=9).mean().iloc[-1], data['Close'].ewm(span=21).mean().iloc[-1]
            return "BULLISH" if ema9 > ema21 else "BEARISH"
    except Exception as e:
        log_and_alert_error(f"15m Trend Error: {e}")
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
    up, down = high - high.shift(1), low.shift(1) - low
    pos_dm = np.where((up > down) & (up > 0), up, 0.0)
    neg_dm = np.where((down > up) & (down > 0), down, 0.0)
    pos_di = 100 * (pd.Series(pos_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    neg_di = 100 * (pd.Series(neg_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    dx = 100 * ((pos_di - neg_di).abs() / (pos_di + neg_di + 1e-9))
    adx = dx.rolling(period).mean()
    return adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0

def theta_shield_active(data):
    if len(data) < 14: return False
    recent_low = data['Low'].tail(10).min()
    return (((data['High'].tail(10).max() - recent_low) / (recent_low + 1e-9)) * 100) < 0.25

# --- PORTFOLIO & SCORECARD ---
PORTFOLIO_FILE = "options_journal.csv"
FIXED_COST_PER_TRADE = 100 

def load_portfolio():
    cols = ["Trade ID", "Date", "Time", "Index", "Expiry", "Strike", "Opt Type", "Qty", "Lots", "Entry Premium", "SL Level", "1R Level", "Target Level", "Status", "Net P&L", "Verified", "1R Booked", "1R Fill", "Signal Time", "Exit Time", "Algo Remarks"]
    if os.path.exists(PORTFOLIO_FILE):
        dtypes = {'Exit Time': str, 'Signal Time': str, 'Algo Remarks': str}
        return pd.read_csv(PORTFOLIO_FILE, dtype=dtypes)
    return pd.DataFrame(columns=cols)

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
    
    last_exit_str = sl_trades.iloc[-1].get('Exit Time')
    if pd.isna(last_exit_str) or not last_exit_str: return False
    last_exit = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{today} {last_exit_str}", "%Y-%m-%d %H:%M:%S"))
    return ((get_ist_time() - last_exit).total_seconds() / 60) < 30

def is_recently_skipped(index_name, opt_type):
    df = load_portfolio()
    if df.empty: return False
    today = get_ist_time().strftime("%Y-%m-%d")
    skipped = df[(df['Date'] == today) & (df['Index'] == index_name) & (df['Opt Type'] == opt_type) & (df['Status'] == "Skipped ❌")]
    if skipped.empty: return False
    last_skip_str = skipped.iloc[-1]['Time']
    last_skip = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{today} {last_skip_str}", "%Y-%m-%d %H:%M:%S"))
    return ((get_ist_time() - last_skip).total_seconds() / 60) < 15

def record_trade_action(trade_dict, entry_price, action_type):
    df = load_portfolio()
    now_ist = get_ist_time()
    today, time_str = now_ist.strftime("%Y-%m-%d"), now_ist.strftime("%H:%M:%S")
    trade_id = f"{trade_dict['Index'][:3]}_{today}_{time_str.replace(':', '')}"

    if action_type == "TAKEN":
        sl_val, r1_val, tgt_val = round(entry_price * 0.70, 2), round(entry_price * 1.30, 2), round(entry_price * 1.60, 2)
        is_verified = "ESTIMATED" not in str(trade_dict['Data Source']).upper()
        
        new_row = {"Trade ID": trade_id, "Date": today, "Time": time_str, "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'], "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'], "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price, "SL Level": sl_val, "1R Level": r1_val, "Target Level": tgt_val, "Status": "Active ⏳", "Net P&L": 0.0, "Verified": is_verified, "1R Booked": False, "1R Fill": 0.0, "Signal Time": trade_dict['Signal Time'], "Exit Time": "", "Algo Remarks": "Paper Tracked"}
        pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)
        send_telegram_alert(f"🎯 TRADE ENTERED\n{trade_dict['Index']} {trade_dict['Opt Type']} {trade_dict['Strike']}\nEntry: ₹{entry_price}\n🛑 SL: ₹{sl_val} | 💵 1R: ₹{r1_val}")
    else:
        new_row = {"Trade ID": trade_id, "Date": today, "Time": time_str, "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'], "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'], "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price, "SL Level": 0, "1R Level": 0, "Target Level": 0, "Status": "Skipped ❌", "Net P&L": 0.0, "Verified": False, "1R Booked": False, "1R Fill": 0.0, "Signal Time": trade_dict['Signal Time'], "Exit Time": time_str, "Algo Remarks": "Skipped"}
        pd.concat([df, pd.DataFrame([new_row])], ignore_index=True).to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard(d_client, d_token):
    df = load_portfolio()
    if df.empty: return df

    now = get_ist_time()
    is_315_passed = now.time() >= datetime.time(15, 15)
    modified = False
    exit_time_str = now.strftime("%H:%M:%S")

    for index, row in df.iterrows():
        if row['Status'] == "Active ⏳":
            entry_premium = float(row['Entry Premium'])
            trade_entry_time = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{row['Date']} {row['Time']}", "%Y-%m-%d %H:%M:%S"))
            mins_active = (now - trade_entry_time).total_seconds() / 60
            
            if is_315_passed:
                df.at[index, 'Status'] = "Pending Exit Price ⏳"
                df.at[index, 'Algo Remarks'] = str(row['Algo Remarks']) + " | 3:15 PM Hard Stop - Needs Manual Exit"
                send_telegram_alert(f"⏰ 3:15 PM EXIT: {row['Index']} requires manual exit price input on dashboard.")
                modified = True
                continue

            live_premium = get_live_premium_dhan(d_client, d_token, row['Index'], float(row['Strike']), row['Opt Type'], row['Expiry'])
            
            if mins_active >= 20 and "Time-Stop Alerted" not in str(row['Algo Remarks']):
                if live_premium is not None:
                    if (0.90 * entry_premium) <= live_premium <= (1.10 * entry_premium):
                        send_telegram_alert(f"⏱️ TIME-STOP WARNING: {row['Index']} flat & active > 20 mins. Consider exit.")
                        df.at[index, 'Algo Remarks'] = str(row['Algo Remarks']) + " | Time-Stop Alerted"
                        modified = True
                else:
                    send_telegram_alert(f"⏱️ TIME-STOP WARNING: {row['Index']} active > 20 mins (LTP missing). Consider exit.")
                    df.at[index, 'Algo Remarks'] = str(row['Algo Remarks']) + " | Time-Stop Alerted"
                    modified = True

            if live_premium is None: 
                continue
                
            entry, sl, r1, tgt, qty = entry_premium, float(row['SL Level']), float(row['1R Level']), float(row['Target Level']), int(row['Qty'])
            one_r_booked = row.get('1R Booked', False)
            one_r_fill = float(row.get('1R Fill', 0.0))
            status, pnl = None, 0.0

            if live_premium >= tgt:
                status = "Target Hit 🎯"
                pnl = (((one_r_fill - entry) * (qty * 0.5)) + ((live_premium - entry) * (qty * 0.5)) - FIXED_COST_PER_TRADE) if one_r_booked else ((live_premium - entry) * qty - FIXED_COST_PER_TRADE)
                send_telegram_alert(f"🎯 TARGET HIT: {row['Index']} exited at live ₹{live_premium}")
            
            elif live_premium >= r1 and not one_r_booked:
                df.at[index, '1R Booked'] = True
                df.at[index, '1R Fill'] = live_premium
                df.at[index, 'Algo Remarks'] = str(row['Algo Remarks']) + " | 1R Booked"
                send_telegram_alert(f"💵 1R HIT: 50% Booked & SL Trailed to Cost for {row['Index']} at live ₹{live_premium}")
                modified = True
                
            elif live_premium <= sl and not one_r_booked:
                status, pnl = "SL Hit 🛑", (live_premium - entry) * qty - FIXED_COST_PER_TRADE
                send_telegram_alert(f"🛑 SL HIT: {row['Index']} exited at live ₹{live_premium}")
                
            elif one_r_booked and live_premium <= entry:
                status = "Trailed SL Hit 🛡️"
                pnl = (((one_r_fill - entry) * (qty * 0.5)) + ((live_premium - entry) * (qty * 0.5)) - FIXED_COST_PER_TRADE)
                send_telegram_alert(f"🛡️ TRAILED SL HIT: {row['Index']} exited at live ₹{live_premium}.")

            if status:
                df.at[index, 'Status'], df.at[index, 'Net P&L'], df.at[index, 'Exit Time'] = status, round(pnl, 2), exit_time_str
                modified = True

    if modified: df.to_csv(PORTFOLIO_FILE, index=False)
    return df

def scan_options_market(risk_amt, dynamic_expiries, d_client, d_token):
    results = []
    curr_vix, is_vix_crashing, is_vix_extreme = get_vix_status()
    
    if curr_vix is None:
        st.error("🚫 Market Locked: VIX is unavailable (Data fetch failed).")
        return results
    if is_vix_extreme or is_vix_crashing:
        st.error(f"🚫 Market Locked: VIX is Extreme/Crashing ({curr_vix}).")
        return results

    if get_daily_trade_count() >= 3:
        st.error(f"🔒 KILL-SWITCH ACTIVE: Max 3 trades reached.")
        return results

    df = load_portfolio()
    active_indices = df[(df['Date'] == get_ist_time().strftime("%Y-%m-%d")) & (df['Status'] == "Active ⏳")]['Index'].tolist()
    if active_indices:
        return results

    for name, info in INDICES.items():
        try:
            if is_cooldown_active(name): continue

            data_5m = yf.Ticker(info["ticker"]).history(period="5d", interval="5m")
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
            expiry_str = dynamic_expiries.get(name)
            
            if is_recently_skipped(name, opt_type):
                continue

            live_premium = get_live_premium_dhan(d_client, d_token, name, strike_price, opt_type, expiry_str)
            if live_premium and live_premium > 0:
                base_est_premium, data_source = live_premium, "🟢 LIVE LTP (Verified)"
            else:
                base_est_premium, data_source = max(85, int(live_price * (curr_vix / 100) * 0.035)), "🟡 ESTIMATED LTP (Unverified)"

            risk_per_lot = base_est_premium * 0.30 * info["lot_size"]
            if risk_per_lot > risk_amt:
                st.warning(f"⚠️ Trade Skipped for {name}: {info['lot_size']} Qty Risk (₹{round(risk_per_lot, 2)}) > Max Limit (₹{int(risk_amt)})")
                continue
                
            num_lots = max(1, int(risk_amt // risk_per_lot))

            results.append({
                "Index": name, "Signal": "🔥 BULLISH" if is_bullish else "🩸 BEARISH", "Action": action,
                "Expiry": expiry_str, "Strike": strike_price, "Opt Type": opt_type, "Lots": num_lots, "Qty": num_lots * info["lot_size"], 
                "Est Premium": base_est_premium, "Data Source": data_source, "Signal Time": get_ist_time().strftime("%H:%M:%S"),
                "Filters": f"VWAP: OK | ADX: {round(adx_val, 1)} | 15M: {trend_15m}"
            })
        except Exception as e:
            log_and_alert_error(f"Scanner Loop Error ({name}): {e}")
    return results

# --- SIDEBAR & UI ---
st.set_page_config(page_title="Institutional F&O Sniper", page_icon="🎯", layout="wide")
st.title("🎯 Institutional F&O Sniper (V1 - Frozen for Paper Trade)")

if st.session_state.api_error_count > 0:
    st.error(f"⚠️ System encountered {st.session_state.api_error_count} API errors. Check terminal for logs.")

st.sidebar.markdown("### ⚙️ Capital & Risk Management")
capital = st.sidebar.number_input("Total Trading Capital (₹)", min_value=10000, value=100000, step=5000)
risk_pct = st.sidebar.slider("Max Risk per Trade (%)", min_value=1.0, max_value=5.0, value=2.0, step=0.5)
risk_amt = capital * (risk_pct / 100)
st.sidebar.info(f"💰 Allowed Risk per Trade: **₹{int(risk_amt)}**")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Dynamic Expiry Selectors")
dynamic_expiries = {}
for idx_name, spec in INDICES.items():
    val = get_monthly_expiry(spec["weekday"]) if spec["expiry_type"] == "monthly" else get_weekly_expiry(spec["weekday"])
    dynamic_expiries[idx_name] = st.sidebar.text_input(f"{idx_name} Expiry", value=val)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 Data Connection Setup")
d_client = st.sidebar.text_input("Dhan Client ID (Optional)", type="password")
d_token = st.sidebar.text_input("Access Token (Optional)", type="password")
st.sidebar.warning("⚠️ Strictly Read-Only Paper Mode.")

curr_vix, _, _ = get_vix_status()
if curr_vix: st.sidebar.info(f"📊 **India VIX:** {curr_vix}")

tab1, tab2 = st.tabs(["🎯 Live Radar & Execution Hub", "📈 Auto-Journal & Scorecard"])

if 'current_signals' not in st.session_state: st.session_state.current_signals = []
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None

with tab1:
    col1, col2, col3 = st.columns(3)
    col1.metric("NIFTY 50 (15M)", check_15m_trend("^NSEI"))
    col2.metric("BANKNIFTY (15M)", check_15m_trend("^NSEBANK"))
    col3.metric("SENSEX (15M)", check_15m_trend("^BSESN"))
    st.markdown("---")
    
    auto_mode = st.checkbox("🤖 Auto-Pilot (Scan every 55s)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock", value=False)
    manual_scan = st.button("🔥 Scan Market Signals Now", use_container_width=True)

    now = get_ist_time()
    now_time = now.time()
    in_golden_window = (datetime.time(9, 30) <= now_time <= datetime.time(11, 30)) or (datetime.time(13, 30) <= now_time <= datetime.time(14, 45))

    active_signals = []
    for sig in st.session_state.current_signals:
        stale_time = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{now.strftime('%Y-%m-%d')} {sig['Signal Time']}", "%Y-%m-%d %H:%M:%S"))
        if (now - stale_time).total_seconds() <= 180:
            active_signals.append(sig)
    st.session_state.current_signals = active_signals

    if manual_scan or (auto_mode and (st.session_state.last_scan_time is None or (now - st.session_state.last_scan_time).total_seconds() >= 55)):
        if now_time >= datetime.time(15, 0) and not bypass_time: 
            st.error("⏰ Scanning Locked: Post 3:00 PM Hard Stop Active.")
            st.session_state.current_signals = []
        elif not in_golden_window and not bypass_time: 
            st.warning("⏳ Outside Golden Window. Market may be choppy.")
            st.session_state.current_signals = []
        else:
            with st.spinner("Analyzing VWAP, ADX & Fetching Live Premiums..."):
                fresh_signals = scan_options_market(risk_amt, dynamic_expiries, d_client, d_token)
                merged_signals = []
                for f_sig in fresh_signals:
                    for old_sig in st.session_state.current_signals:
                        if old_sig['Index'] == f_sig['Index'] and old_sig['Opt Type'] == f_sig['Opt Type']:
                            f_sig['Signal Time'] = old_sig['Signal Time']
                            break
                    merged_signals.append(f_sig)
                st.session_state.current_signals = merged_signals
                st.session_state.last_scan_time = now

    if st.session_state.current_signals:
         st.success(f"🚨 {len(st.session_state.current_signals)} Smart Setup(s) Active!")
         for i, sig in enumerate(list(st.session_state.current_signals)):
             st.markdown(f"#### 🎯 Signal: {sig['Index']} - {sig['Action']} {sig['Strike']}")
             st.info(f"Filters: {sig['Filters']} | Sizing: {sig['Lots']} Lots | Source: {sig['Data Source']}")
             
             c1, c2, c3 = st.columns([2, 1, 1])
             user_entry = c1.number_input(f"Live Premium (₹)", min_value=5.0, value=float(sig['Est Premium']), step=1.0, key=f"entry_{sig['Index']}_{sig['Opt Type']}")
             
             if c2.button("✅ Trade Liya", key=f"take_{sig['Index']}_{sig['Opt Type']}", use_container_width=True):
                 signal_time = pytz.timezone('Asia/Kolkata').localize(datetime.datetime.strptime(f"{now.strftime('%Y-%m-%d')} {sig['Signal Time']}", "%Y-%m-%d %H:%M:%S"))
                 
                 # FIX 1: Double verification of active/limit logic AT THE EXACT MOMENT of button click
                 current_df = load_portfolio()
                 active_now = current_df[(current_df['Date'] == now.strftime("%Y-%m-%d")) & (current_df['Status'].isin(["Active ⏳", "Pending Exit Price ⏳"]))]
                 daily_count = len(current_df[(current_df['Date'] == now.strftime("%Y-%m-%d")) & (current_df['Status'] != "Skipped ❌")])

                 if not active_now.empty:
                     st.error("⚠️ Trade blocked: You already have an active or pending trade.")
                 elif daily_count >= 3:
                     st.error("⚠️ Trade blocked: Max 3 trades limit reached for today.")
                 elif (get_ist_time() - signal_time).total_seconds() > 180:
                     st.error(f"⏳ Signal Expired! 3 minutes passed since generation. Do not chase.")
                 else:
                     record_trade_action(sig, user_entry, "TAKEN")
                     st.success(f"Trade Recorded! Tracking SL/Target for {sig['Index']}.")
                     st.session_state.current_signals.remove(sig)
                     st.rerun()
                     
             if c3.button("❌ Skip Kiya", key=f"skip_{sig['Index']}_{sig['Opt Type']}", use_container_width=True):
                 record_trade_action(sig, user_entry, "SKIPPED")
                 st.session_state.current_signals.remove(sig)
                 st.rerun()
    elif not manual_scan and not auto_mode: pass
    else: st.info("🧘 No institutional breakout matching core filters right now.")

with tab2:
    st.subheader("🏆 Auto-Tracked Options Journal")
    
    df_current = load_portfolio()
    active_trades = df_current[df_current['Status'].isin(["Active ⏳", "Pending Exit Price ⏳"])]
    if not active_trades.empty:
        st.markdown("### 🛠️ Manage Trades (Manual Close)")
        for i, row in active_trades.iterrows():
            mc1, mc2, mc3 = st.columns([3, 1, 1])
            mc1.write(f"**{row['Index']} {row['Opt Type']} {row['Strike']}** (Entry: ₹{row['Entry Premium']}) - {row['Status']}")
            exit_val = mc2.number_input("Exit Price (₹)", min_value=1.0, value=float(row['Entry Premium']), step=1.0, key=f"manual_exit_{row['Trade ID']}")
            if mc3.button("Close Trade", key=f"close_btn_{row['Trade ID']}"):
                one_r_booked, qty, entry = row.get('1R Booked', False), int(row['Qty']), float(row['Entry Premium'])
                one_r_fill = float(row.get('1R Fill', 0.0))
                if one_r_booked:
                    pnl = ((one_r_fill - entry) * (qty * 0.5)) + ((exit_val - entry) * (qty * 0.5)) - FIXED_COST_PER_TRADE
                else:
                    pnl = (exit_val - entry) * qty - FIXED_COST_PER_TRADE
                
                df_current.loc[df_current['Trade ID'] == row['Trade ID'], ['Status', 'Net P&L', 'Exit Time', 'Algo Remarks']] = ["Manual Close ✋", round(pnl, 2), get_ist_time().strftime("%H:%M:%S"), str(row['Algo Remarks']) + " | Manually Closed"]
                df_current.to_csv(PORTFOLIO_FILE, index=False)
                st.success("Trade Closed!")
                st.rerun()
    st.markdown("---")

    if st.button("🔄 Refresh Live Positions & P&L", type="primary"):
        with st.spinner("Auditing Positions..."):
            updated_df = update_scorecard(d_client, d_token)
    else:
        updated_df = load_portfolio()

    if not updated_df.empty:
        verified_closed = updated_df[(updated_df['Verified'] == True) | (updated_df['Verified'] == "True")]
        verified_closed = verified_closed[verified_closed['Status'].isin(["Target Hit 🎯", "SL Hit 🛑", "Trailed SL Hit 🛡️", "Manual Close ✋", "Time Exit ⏰"])]
        st.markdown("*(Note: Estimated/Unverified trades excluded from Win-Rate and Realized P&L)*")
        
        if not verified_closed.empty:
            total_net_pnl = verified_closed['Net P&L'].sum()
            wins, total_closed = len(verified_closed[verified_closed['Net P&L'] > 0]), len(verified_closed)
            win_rate = round((wins / total_closed * 100), 2) if total_closed > 0 else 0
            
            targets = len(verified_closed[verified_closed['Status'] == "Target Hit 🎯"])
            
            # FIX 2: Exact matching strings for the SLs/Exits metric
            sls = len(verified_closed[verified_closed['Status'].isin(["SL Hit 🛑", "Trailed SL Hit 🛡️", "Manual Close ✋", "Time Exit ⏰"])])
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Verified Win Rate 📊", f"{win_rate}%")
            c2.metric("Targets Hit 🎯", targets)
            c3.metric("SLs/Exits Hit 🛑", sls)
            c4.metric("Realized Net P&L (₹) 💵", round(total_net_pnl, 2), delta=total_net_pnl)
        
        display_cols = [c for c in updated_df.columns if c not in ["Trade ID", "Signal Time", "Exit Time"]]
        try: 
            # FIX 2: Exact matching strings in style map
            st.dataframe(updated_df[display_cols].style.map(lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x in ['SL Hit 🛑', 'Pending Exit Price ⏳', 'Trailed SL Hit 🛡️', 'Manual Close ✋', 'Time Exit ⏰'] else ''), subset=['Status']), use_container_width=True)
        except:
            st.dataframe(updated_df[display_cols], use_container_width=True)
        st.download_button("💾 Download Journal CSV", data=updated_df.to_csv(index=False).encode('utf-8'), file_name="Options_Journal.csv", mime="text/csv")

if auto_mode:
    update_scorecard(d_client, d_token)
    st_autorefresh(interval=60000, key="global_tracking_refresh")
