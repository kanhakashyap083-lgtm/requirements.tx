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

# --- DHAN API INTEGRATION (PLACEHOLDER FOR PAPER TRADING) ---
def place_dhan_options_order(client_id, token, index_name, action, qty, is_auto):
    if not is_auto:
        return "Manual Alert / Paper Trade"
    return "LIVE ORDER SIGNALED 🚀"

def get_live_premium_dhan(d_client, d_token, index_name, strike, opt_type):
    # Currently returning None for Paper Trading Mode
    # Will be replaced with actual Dhan API logic in Stage 2
    return None

# --- SMART BROWSER SESSION (FOR NON-CACHED FUNCTIONS ONLY) ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# --- APP SETUP & UI ---
st.set_page_config(page_title="Institutional F&O Sniper", page_icon="🎯", layout="wide")
st.title("🎯 Institutional F&O Sniper (Stage-1 Paper Trade Mode)")
st.markdown("**(Sensex Active 🦅 | VWAP + ADX ⚡ | 3:15 Hard Stop ⏰ | Correlated Block 🛡️)**")

PORTFOLIO_FILE = "options_journal.csv"
MAX_TRADES_PER_DAY = 3

# --- INDICES SPECIFICATIONS ---
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
    if days_ahead < 0:
        days_ahead += 7
    next_date = today + datetime.timedelta(days=days_ahead)
    return next_date.strftime("%d %b %Y")

# 🚨 BUG FIXED: Removed session=session to prevent Streamlit cache hashing conflicts
@st.cache_data(ttl=300)
def get_vix_status():
    try:
        vix_data = yf.Ticker("^INDIAVIX").history(period="2d")
        if len(vix_data) >= 2:
            prev_vix = vix_data['Close'].iloc[-2]
            curr_vix = vix_data['Close'].iloc[-1]
            drop_pct = ((prev_vix - curr_vix) / prev_vix) * 100
            is_extreme = curr_vix > 24.0
            is_crashing = drop_pct >= 6.0
            return round(curr_vix, 2), is_crashing, is_extreme
    except Exception:
        pass
    return 15.0, False, False

# 🚨 BUG FIXED: Removed session=session from cached function
@st.cache_data(ttl=300)
def check_15m_trend(ticker):
    try:
        data = yf.Ticker(ticker).history(period="5d", interval="15m")
        if not data.empty and len(data) >= 21:
            ema9 = data['Close'].ewm(span=9).mean().iloc[-1]
            ema21 = data['Close'].ewm(span=21).mean().iloc[-1]
            return "BULLISH" if ema9 > ema21 else "BEARISH"
    except Exception:
        pass
    return "NEUTRAL"

# --- MATHEMATICAL INDICATORS ---
def calculate_vwap(df):
    v = df['Volume'].values
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    return (tp * v).cumsum() / (v.cumsum() + 1e-9)

def calculate_adx(df, period=14):
    if len(df) < period * 2: return 0
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    pos_di = 100 * (pd.Series(pos_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    neg_di = 100 * (pd.Series(neg_dm, index=df.index).rolling(period).mean() / (atr + 1e-9))
    
    dx = 100 * ((pos_di - neg_di).abs() / (pos_di + neg_di + 1e-9))
    adx = dx.rolling(period).mean()
    return adx.iloc[-1] if not np.isnan(adx.iloc[-1]) else 0

def theta_shield_active(data):
    if len(data) < 14: return False
    recent_high = data['High'].tail(10).max()
    recent_low = data['Low'].tail(10).min()
    range_pct = ((recent_high - recent_low) / (recent_low + 1e-9)) * 100
    return range_pct < 0.25

# --- PORTFOLIO & AUDIT TRACKING ---
def load_portfolio():
    cols = [
        "Trade ID", "Date", "Time", "Index", "Expiry", "Strike", "Opt Type", 
        "Qty", "Lots", "Entry Premium", "SL Level (30%)", "1R Level (30%)", "Target Level (60%)", 
        "Status", "Net P&L", "Filters Passed", "Algo Remarks"
    ]
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=cols)

def get_daily_trade_count():
    df = load_portfolio()
    if df.empty: return 0
    today = get_ist_time().strftime("%Y-%m-%d")
    return len(df[(df['Date'] == today) & (df['Status'] != "Skipped ❌")])

def is_cooldown_active(index_name):
    df = load_portfolio()
    if df.empty: return False
    today = get_ist_time().strftime("%Y-%m-%d")
    sl_trades = df[(df['Date'] == today) & (df['Index'] == index_name) & (df['Status'] == "SL Hit 🛑")]
    if sl_trades.empty: return False
    
    last_sl_time_str = sl_trades.iloc[-1]['Time']
    last_sl_time = datetime.datetime.strptime(f"{today} {last_sl_time_str}", "%Y-%m-%d %H:%M:%S")
    last_sl_time = pytz.timezone('Asia/Kolkata').localize(last_sl_time)
    
    minutes_passed = (get_ist_time() - last_sl_time).total_seconds() / 60
    return minutes_passed < 30

def record_trade_action(trade_dict, entry_price, action_type, auto_trade, d_client, d_token):
    df = load_portfolio()
    now_ist = get_ist_time()
    today = now_ist.strftime("%Y-%m-%d")
    time_str = now_ist.strftime("%H:%M:%S")
    trade_id = f"{trade_dict['Index'][:3]}_{today}_{time_str.replace(':', '')}"

    if action_type == "TAKEN":
        sl_val = round(entry_price * 0.70, 2)
        r1_val = round(entry_price * 1.30, 2)
        tgt_val = round(entry_price * 1.60, 2)
        exec_status = place_dhan_options_order(d_client, d_token, trade_dict['Index'], trade_dict['Action'], trade_dict['Qty'], auto_trade)
        
        new_row = {
            "Trade ID": trade_id, "Date": today, "Time": time_str,
            "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'],
            "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'],
            "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price,
            "SL Level (30%)": sl_val, "1R Level (30%)": r1_val, "Target Level (60%)": tgt_val,
            "Status": "Active ⏳", "Net P&L": 0.0,
            "Filters Passed": trade_dict.get('Filters', 'Core Stage-1 Passed'),
            "Algo Remarks": exec_status
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(PORTFOLIO_FILE, index=False)

        msg = (f"🎯 TRADE ENTERED & TRACKING\n"
               f"Index: {trade_dict['Index']} ({trade_dict['Opt Type']})\n"
               f"Strike: {trade_dict['Strike']} | Expiry: {trade_dict['Expiry']}\n"
               f"Lots: {trade_dict['Lots']} | Entry Price: ₹{entry_price}\n"
               f"🛑 SL (30% Loss): ₹{sl_val}\n"
               f"💵 1R Target (30% Gain): ₹{r1_val}\n"
               f"🎯 Final Target (60% Gain): ₹{tgt_val}")
        send_telegram_alert(msg)
    else:
        new_row = {
            "Trade ID": trade_id, "Date": today, "Time": time_str,
            "Index": trade_dict['Index'], "Expiry": trade_dict['Expiry'],
            "Strike": trade_dict['Strike'], "Opt Type": trade_dict['Opt Type'],
            "Qty": trade_dict['Qty'], "Lots": trade_dict['Lots'], "Entry Premium": entry_price,
            "SL Level (30%)": 0, "1R Level (30%)": 0, "Target Level (60%)": 0,
            "Status": "Skipped ❌", "Net P&L": 0.0,
            "Filters Passed": trade_dict.get('Filters', 'Core Stage-1 Passed'),
            "Algo Remarks": "User manually skipped trade"
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df.to_csv(PORTFOLIO_FILE, index=False)

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

            live_premium = get_live_premium_dhan(d_client, d_token, row['Index'], row['Strike'], row['Opt Type'])
            
            if live_premium is None:
                df.at[index, 'Algo Remarks'] = "Dhan API Placeholder (Manual Tracking)"
                continue
                
            entry_premium = float(row['Entry Premium'])
            sl_level = float(row['SL Level (30%)'])
            r1_level = float(row['1R Level (30%)'])
            target_level = float(row['Target Level (60%)'])
            qty = int(row['Qty'])
            opt_type = row['Opt Type']

            status = None
            pnl = 0.0

            if live_premium >= target_level:
                status = "Target Hit 🎯"
                pnl = (target_level - entry_premium) * qty
                send_telegram_alert(f"🎯 2R TARGET HIT: Full Exit\n{row['Index']} {opt_type} at actual ₹{live_premium}")
            elif live_premium <= sl_level:
                status = "SL Hit 🛑"
                pnl = (sl_level - entry_premium) * qty
                send_telegram_alert(f"🛑 SL HIT: EXIT NOW\n{row['Index']} {opt_type} at actual ₹{live_premium}")
            elif live_premium >= r1_level and row['Status'] != "1R Hit (Partial) 💵":
                send_telegram_alert(f"💵 1R HIT: BOOK 50% & TRAIL SL TO COST\n{row['Index']} {opt_type} reached ₹{live_premium}")
                df.at[index, 'Algo Remarks'] = "1R Hit Alerted"

            if status:
                df.at[index, 'Status'] = status
                df.at[index, 'Net P&L'] = round(pnl, 2)

    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- SIGNAL GENERATION ENGINE ---
def scan_options_market(risk_amt, is_auto_exec, dynamic_expiries):
    results = []
    
    curr_vix, is_vix_crashing, is_vix_extreme = get_vix_status()
    if is_vix_extreme:
        st.error(f"🚫 Market Locked: India VIX is at Extreme Level ({curr_vix}).")
        return results
    if is_vix_crashing:
        st.error(f"🚫 Market Locked: VIX is crashing (>6% drop). High risk of Premium Melt.")
        return results

    today_trades = get_daily_trade_count()
    if today_trades >= MAX_TRADES_PER_DAY:
        st.error(f"🔒 DAILY KILL-SWITCH ACTIVE: Max trades ({MAX_TRADES_PER_DAY}) reached for today.")
        return results

    df = load_portfolio()
    today = get_ist_time().strftime("%Y-%m-%d")
    active_trades = df[(df['Date'] == today) & (df['Status'] == "Active ⏳")]
    active_indices = active_trades['Index'].unique().tolist() if not active_trades.empty else []

    for name, info in INDICES.items():
        try:
            if active_indices and name not in active_indices:
                continue

            if is_cooldown_active(name):
                st.warning(f"🥶 SL Cooldown Active for {name}. Scanning paused for 30 mins.")
                continue

            tkr = yf.Ticker(info["ticker"], session=session)
            data_5m = tkr.history(period="5d", interval="5m")
            if data_5m.empty or len(data_5m) < 30: continue

            trend_15m = check_15m_trend(info["ticker"])
            vwap = calculate_vwap(data_5m).iloc[-1]
            adx_val = calculate_adx(data_5m)
            live_price = data_5m['Close'].iloc[-1]

            if theta_shield_active(data_5m): continue

            ema9 = data_5m['Close'].ewm(span=9).mean().iloc[-1]
            ema21 = data_5m['Close'].ewm(span=21).mean().iloc[-1]
            delta = data_5m['Close'].diff()
            up = delta.clip(lower=0)
            down = -1 * delta.clip(upper=0)
            rs = up.ewm(com=13, adjust=False).mean() / (down.ewm(com=13, adjust=False).mean() + 1e-9)
            rsi = 100 - (100 / (1 + rs)).iloc[-1]

            is_bullish = (live_price > vwap) and (live_price > ema9 > ema21) and (rsi > 55) and (trend_15m == "BULLISH") and (adx_val > 25)
            is_bearish = (live_price < vwap) and (live_price < ema9 < ema21) and (rsi < 45) and (trend_15m == "BEARISH") and (adx_val > 25)

            if not (is_bullish or is_bearish): continue

            opt_type = "CALL" if is_bullish else "PUT"
            action = f"🟢 BUY {opt_type}" if opt_type == "CALL" else f"🔴 BUY {opt_type}"
            step = info["step"]
            strike_price = int(round(live_price / step) * step)

            base_est_premium = int(live_price * (curr_vix / 100) * 0.035)
            if base_est_premium < 50: base_est_premium = 85

            sl_points = base_est_premium * 0.30
            risk_per_lot = sl_points * info["lot_size"]
            
            if risk_per_lot > risk_amt:
                st.warning(f"⚠️ Trade Skipped for {name}: 1 Lot Risk (₹{round(risk_per_lot,2)}) exceeds Max Risk (₹{risk_amt}).")
                continue
                
            num_lots = max(1, int(risk_amt // risk_per_lot))
            total_qty = num_lots * info["lot_size"]

            results.append({
                "Index": name,
                "Signal": "🔥 BULLISH MOMENTUM" if is_bullish else "🩸 BEARISH BREAKDOWN",
                "Action": action,
                "Expiry": dynamic_expiries.get(name, get_default_expiry(info["default_weekday"])),
                "Strike": strike_price,
                "Opt Type": opt_type,
                "Lots": num_lots,
                "Qty": total_qty,
                "Est Premium": base_est_premium,
                "Filters": f"VWAP: OK | ADX: {round(adx_val, 1)} | 15M: {trend_15m}"
            })
        except Exception:
            pass
    return results

# --- SIDEBAR CONFIGURATION ---
st.sidebar.markdown("### ⚙️ Stage-1 Risk & Operations")
capital = st.sidebar.number_input("Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk = st.sidebar.number_input("Max Risk Per Trade (₹)", min_value=500, value=1500, step=250)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📅 Dynamic Expiry Selectors")
dynamic_expiries = {}
for idx_name, spec in INDICES.items():
    default_date = get_default_expiry(spec["default_weekday"])
    dynamic_expiries[idx_name] = st.sidebar.text_input(f"{idx_name} Expiry", value=default_date)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 DhanHQ Live Connection")
d_client = st.sidebar.text_input("Dhan Client ID", type="password")
d_token = st.sidebar.text_input("Access Token", type="password")
auto_trade_live = st.sidebar.toggle("🚨 Enable Live Auto-Execution", value=False)

curr_vix, is_vix_crashing, is_vix_extreme = get_vix_status()
st.sidebar.info(f"📊 **India VIX:** {curr_vix}")

# --- UI WORKSPACE TABS ---
tab1, tab2 = st.tabs(["🎯 Live Radar & Execution Hub", "📈 Options Journal & Audit Scorecard"])

with tab1:
    st.subheader("Multi-Index Options Radar (Paper Trade Mode)")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("NIFTY 50 (15M)", check_15m_trend("^NSEI"))
    col2.metric("BANKNIFTY (15M)", check_15m_trend("^NSEBANK"))
    col3.metric("SENSEX (15M)", check_15m_trend("^BSESN"))

    st.markdown("---")
    auto_mode = st.checkbox("🤖 Auto-Pilot (Scan every 60s)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock (Testing Mode)", value=False)
    manual_scan = st.button("🔥 Scan Market Signals Now", use_container_width=True)

    now_time = get_ist_time().time()
    in_golden_window = (
        (datetime.time(9, 30) <= now_time <= datetime.time(11, 30)) or 
        (datetime.time(13, 30) <= now_time <= datetime.time(14, 45))
    )
    after_cutoff = (now_time >= datetime.time(15, 0))

    if auto_mode or manual_scan:
        if after_cutoff and not bypass_time:
            st.error("⏰ Scanning Locked: Post 3:00 PM Hard Stop Active.")
        elif not in_golden_window and not bypass_time:
            st.warning("⏳ Outside Golden Window (09:30-11:30 AM & 01:30-02:45 PM). Market may be choppy.")
        else:
            with st.spinner("Analyzing VWAP, ADX, and Multi-Timeframe Alignment..."):
                signals = scan_options_market(risk, auto_trade_live, dynamic_expiries)

            if signals:
                st.success(f"🚨 {len(signals)} Smart Money Setup(s) Found!")
                
                for i, sig in enumerate(signals):
                    st.markdown(f"#### 🎯 Signal: {sig['Index']} - {sig['Action']} {sig['Strike']}")
                    st.info(f"Filters Validated: {sig['Filters']} | Sizing: {sig['Lots']} Lots ({sig['Qty']} Qty)")
                    
                    c1, c2, c3 = st.columns([2, 1, 1])
                    user_entry = c1.number_input(
                        f"Executed Premium Price (₹) - {sig['Index']}", 
                        min_value=5.0, 
                        value=float(sig['Est Premium']), 
                        step=1.0, 
                        key=f"entry_val_{i}"
                    )
                    
                    if c2.button("✅ Trade Liya", key=f"take_btn_{i}", use_container_width=True):
                        record_trade_action(sig, user_entry, "TAKEN", auto_trade_live, d_client, d_token)
                        st.success(f"Trade Recorded at ₹{user_entry} with 30% SL & 60% Target!")
                        
                    if c3.button("❌ Skip Kiya", key=f"skip_btn_{i}", use_container_width=True):
                        record_trade_action(sig, user_entry, "SKIPPED", auto_trade_live, d_client, d_token)
                        st.warning("Trade marked as Skipped in Journal.")
            else:
                st.info("🧘 No institutional breakout matching core filters right now.")

            if auto_mode:
                update_scorecard(d_client, d_token)
                st_autorefresh(interval=60000, key="auto_scan_refresh")

with tab2:
    st.subheader("🏆 Options Trading Journal & Live Scorecard")
    
    st.warning("⚠️ PAPER TRADE MODE: Manually track your live P&L at your broker. Update Scorecard manually or wait for API Phase-2.")
    
    if st.button("🔄 Refresh & Check 3:15 Hard Stop", type="primary"):
        with st.spinner("Auditing Open Positions..."):
            updated_df = update_scorecard(d_client, d_token)
    else:
        updated_df = load_portfolio()

    if not updated_df.empty:
        closed_trades = updated_df[updated_df['Status'].isin(["Target Hit 🎯", "SL Hit 🛑", "Time Exit ⏰"])]
        
        if not closed_trades.empty:
            total_net_pnl = closed_trades['Net P&L'].sum()
            targets = len(closed_trades[closed_trades['Status'] == "Target Hit 🎯"])
            sls = len(closed_trades[closed_trades['Status'] == "SL Hit 🛑"])
            win_rate = round((targets / (targets + sls) * 100), 2) if (targets + sls) > 0 else 0
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Win Rate 📊", f"{win_rate}%")
            c2.metric("2R Target Achieved 🎯", targets)
            c3.metric("30% SL Hit 🛑", sls)
            c4.metric("Realized P&L (₹) 💵", round(total_net_pnl, 2), delta=total_net_pnl)
        
        st.write("### 📝 Trade Execution & Journal Log")
        display_cols = [c for c in updated_df.columns if c not in ["Trade ID"]]
        st.dataframe(
            updated_df[display_cols].style.map(
                lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x in ['SL Hit 🛑', 'Time Exit ⏰'] else ''),
                subset=['Status']
            ), 
            use_container_width=True
        )
        csv_data = updated_df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Download Verified Journal CSV", data=csv_data, file_name="Options_Journal.csv", mime="text/csv")
    else:
        st.info("No recorded trades yet. Run scanner to track setups.")
