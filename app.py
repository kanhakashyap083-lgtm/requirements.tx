import streamlit as st
import yfinance as yf
import pandas as pd
import concurrent.futures
import time
import random
import warnings
import os
import datetime
import pytz
import gc
import requests

warnings.filterwarnings("ignore")

# --- TELEGRAM & DHAN API SETUP ---
TELEGRAM_TOKEN = "8657774899:AAGKqx2_TgaoYAbUljSAXt5l9BzL_cnyCPE"
TELEGRAM_CHAT_ID = "8900320752"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload, timeout=5)
    except: pass

def place_dhan_order(client_id, token, symbol, qty, action, price, is_auto):
    if not is_auto: return "Paper Trade"
    try:
        url = "https://api.dhan.co/orders"
        headers = {"access-token": token, "client-id": client_id, "Content-Type": "application/json"}
        txn_type = "BUY" if "BUY" in action else "SELL"
        payload = {
            "dhanClientId": client_id,
            "correlationId": f"Algo_{int(time.time())}",
            "transactionType": txn_type,
            "exchangeSegment": "NSE_EQ",
            "productType": "INTRADAY",
            "orderType": "MARKET",
            "validity": "DAY",
            "securityId": DHAN_STOCKS.get(symbol+".NS", {}).get("id", ""),
            "quantity": int(qty),
            "price": 0
        }
        res = requests.post(url, json=payload, headers=headers, timeout=5).json()
        if res.get("orderStatus") == "PENDING" or res.get("orderStatus") == "TRADED":
            return f"LIVE ORDER FIRED 🚀 (ID: {res.get('orderId', 'Success')})"
        return f"Order Failed: {res}"
    except Exception as e:
        return f"API Error: {e}"

# --- SMART BROWSER SESSION ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

# --- APP SETUP ---
st.set_page_config(page_title="Institutional Mega Algo", page_icon="🚀", layout="wide")
st.title("🚀 Institutional Mega Algo & Scorecard")
st.markdown("**(Dual Engine ⚡ | Smart Money Block | Trailing SL | Auto-Execution)**")

PORTFOLIO_FILE = "live_portfolio.csv"

# --- TOP F&O STOCKS FOR INTRADAY ---
DHAN_STOCKS = {
    "RELIANCE.NS": {"id": "2885", "exch": "NSE_EQ"},
    "HDFCBANK.NS": {"id": "1333", "exch": "NSE_EQ"},
    "INFY.NS": {"id": "1594", "exch": "NSE_EQ"},
    "ICICIBANK.NS": {"id": "4963", "exch": "NSE_EQ"},
    "SBIN.NS": {"id": "4329", "exch": "NSE_EQ"},
    "TCS.NS": {"id": "11536", "exch": "NSE_EQ"},
    "ITC.NS": {"id": "1660", "exch": "NSE_EQ"},
    "LT.NS": {"id": "11483", "exch": "NSE_EQ"},
    "AXISBANK.NS": {"id": "5900", "exch": "NSE_EQ"},
    "KOTAKBANK.NS": {"id": "1922", "exch": "NSE_EQ"},
    "TATAMOTORS.NS": {"id": "3456", "exch": "NSE_EQ"},
    "BHARTIARTL.NS": {"id": "10604", "exch": "NSE_EQ"}
}

def get_ist_time(): return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_vix():
    try:
        vix = yf.Ticker("^INDIAVIX", session=session).history(period="1d")
        if not vix.empty: return round(vix['Close'].iloc[-1], 2)
    except: pass
    return 15.0 

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    rs = up.ewm(com=period-1, adjust=False).mean() / down.ewm(com=period-1, adjust=False).mean()
    return 100 - (100 / (1 + rs))

def check_index_trend(ticker, interval):
    try:
        data = yf.Ticker(ticker, session=session).history(period="6mo", interval=interval)
        if not data.empty and len(data) > 20:
            return data['Close'].ewm(span=9).mean().iloc[-1] > data['Close'].ewm(span=21).mean().iloc[-1]
    except: pass
    return True 

def fetch_dhan_ltf(ticker, client_id, token, interval_mins):
    info = DHAN_STOCKS.get(ticker)
    if not info: return pd.DataFrame()
    try:
        url = "https://api.dhan.co/v2/charts/intraday"
        now = get_ist_time()
        payload = {
            "securityId": info["id"], "exchangeSegment": info["exch"],
            "instrument": "EQUITY", "interval": str(interval_mins).replace("m", ""),
            "fromDate": (now - datetime.timedelta(days=5)).strftime("%Y-%m-%d"),
            "toDate": now.strftime("%Y-%m-%d")
        }
        headers = {"access-token": token, "client-id": client_id, "Content-Type": "application/json"}
        resp = requests.post(url, json=payload, headers=headers, timeout=5).json()
        if resp.get("status") == "success":
            d = resp["data"]
            return pd.DataFrame({"Open": d.get("open", []), "High": d.get("high", []), "Low": d.get("low", []), "Close": d.get("close", []), "Volume": d.get("volume", [])})
    except: pass
    return pd.DataFrame()

@st.cache_data
def load_symbols():
    symbols = []
    try:
        if os.path.exists("C_VAR1_29092026_2.DAT"):
            with open("C_VAR1_29092026_2.DAT", "r") as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) > 3 and parts[2] == 'EQ': symbols.append(parts[1] + ".NS")
            symbols = list(set(symbols))
        elif os.path.exists("PE_290926.csv"):
            symbols = [str(s).strip() + ".NS" for s in pd.read_csv("PE_290926.csv")['SYMBOL'].dropna()]
    except Exception as e: st.error(f"❌ File Load Error: {e}")
    return symbols

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE): return pd.read_csv(PORTFOLIO_FILE)
    return pd.DataFrame(columns=["Date", "Horizon", "Stock", "Score", "Action", "Qty", "Entry", "Target", "SL", "Trailing SL", "Status", "Net P&L", "Algo Remarks"])

def save_to_portfolio(new_trades, auto_trade, d_client, d_token):
    df = load_portfolio()
    today = get_ist_time().strftime("%Y-%m-%d")
    new_rows = []
    active_trades = len(df[(df['Status'] == "Active ⏳") & (df['Date'] == today)])
    max_allowed = st.session_state.get('max_trades', 5)
    
    for t in new_trades:
        if active_trades >= max_allowed: break
        if not ((df['Stock'] == t['Stock']) & (df['Date'] == today) & (df['Horizon'] == t['Horizon'])).any():
            
            # Auto Execution Trigger
            exec_status = place_dhan_order(d_client, d_token, t['Stock'], t['Qty'], t['Action'], t['Entry'], auto_trade)
            
            new_rows.append({
                "Date": today, "Horizon": t['Horizon'], "Stock": t['Stock'], "Score": t['AI Score'], 
                "Action": t['Action'], "Qty": t['Qty'], "Entry": t['Entry'], "Target": t['Target'], 
                "SL": t['SL'], "Trailing SL": t['Trailing SL'], "Status": "Active ⏳", "Net P&L": 0.0, "Algo Remarks": exec_status
            })
            active_trades += 1
            
            msg = f"🚨 NEW {t['Horizon'].upper()} CALL!\n📈 Stock: {t['Stock']}\n🤖 AI Score: {t['AI Score']}\n🎯 Action: {t['Action']}\n💰 Entry: ₹{t['Entry']}\n🏆 Target: ₹{t['Target']}\n🛑 SL: ₹{t['SL']}\n🔒 TSL: ₹{t['Trailing SL']}\n📦 Qty: {t['Qty']}\n⚙️ Exec: {exec_status}"
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
                data = yf.Ticker(f"{row['Stock']}.NS", session=session).history(period="5d", interval="5m" if "Intraday" in row['Horizon'] else "1d")
                if data.empty: continue
                high_today, low_today, live_price = data['High'].max(), data['Low'].min(), data['Close'].iloc[-1]
                qty, entry, tgt, sl, tsl = float(row['Qty']), float(row['Entry']), float(row['Target']), float(row['SL']), float(row['Trailing SL'])
                
                # Buy Logic Update
                if "BUY" in row['Action']:
                    new_tsl = live_price - (live_price * 0.01) # 1% trailing
                    if new_tsl > tsl and live_price > entry: df.at[index, 'Trailing SL'] = round(new_tsl, 2)
                    
                    if high_today >= tgt or low_today <= sl:
                        exit_price = tgt if high_today >= tgt else sl
                        status = "Target Hit 🎯" if high_today >= tgt else "SL Hit 🛑"
                        net_profit = round(((exit_price - entry) * qty) - ((qty * entry + qty * exit_price) * 0.0005), 2)
                        df.at[index, 'Net P&L'] = net_profit
                        df.at[index, 'Status'] = status
                        send_telegram_alert(f"{status}\n📈 {row['Stock']}\n💰 P&L: ₹{net_profit}")
                
                # Short Sell Logic Update (For Falling Markets)
                elif "SHORT" in row['Action']:
                    new_tsl = live_price + (live_price * 0.01)
                    if new_tsl < tsl and live_price < entry: df.at[index, 'Trailing SL'] = round(new_tsl, 2)
                    
                    if low_today <= tgt or high_today >= sl:
                        exit_price = tgt if low_today <= tgt else sl
                        status = "Target Hit 🎯" if low_today <= tgt else "SL Hit 🛑"
                        net_profit = round(((entry - exit_price) * qty) - ((qty * entry + qty * exit_price) * 0.0005), 2)
                        df.at[index, 'Net P&L'] = net_profit
                        df.at[index, 'Status'] = status
                        send_telegram_alert(f"{status}\n📉 {row['Stock']} (SHORT)\n💰 P&L: ₹{net_profit}")
            except: pass
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- DUAL ENGINE & SMART MONEY LOGIC ---
def worker_robot(tickers, risk_amt, cap_amt, is_bullish, horizon, d_client=None, d_token=None):
    found = []
    for idx, ticker in enumerate(tickers):
        if idx % 50 == 0: gc.collect()
        try:
            time.sleep(0.01) 
            ltf_p, ltf_i, htf_p, htf_i, tgt_m, sl_m = ("5d", "15m", "1mo", "1d", 3.5, 1.5) if "Intraday" in horizon else ("6mo", "1d", "1y", "1wk", 4.0, 2.0) if "Short-Term" in horizon else ("2y", "1wk", "5y", "1mo", 5.0, 2.0)
            
            tkr = yf.Ticker(ticker, session=session)
            htf_trend_up, gap_pct, avg_daily_vol = True, 0.0, 0
            
            if htf_p:
                d_htf = tkr.history(period=htf_p, interval=htf_i)
                if len(d_htf) < 22: continue
                ema9, ema21 = d_htf['Close'].ewm(span=9).mean().iloc[-2], d_htf['Close'].ewm(span=21).mean().iloc[-2]
                htf_trend_up = ema9 > ema21
                
                # Gap Tracking
                prev_c, curr_o = d_htf['Close'].iloc[-2], d_htf['Open'].iloc[-1]
                if prev_c > 0: gap_pct = abs((curr_o - prev_c) / prev_c) * 100
            
            feed = "Yahoo 📡"
            if "Intraday" in horizon and d_client and d_token:
                data = fetch_dhan_ltf(ticker, d_client, d_token, ltf_i)
                if not data.empty: feed = "DhanHQ ⚡"
                else: data = tkr.history(period=ltf_p, interval=ltf_i)
            else: data = tkr.history(period=ltf_p, interval=ltf_i)

            if len(data) < 30: continue
            data.dropna(inplace=True)
            
            live_c, closed_c, closed_v = data['Close'].iloc[-1], data['Close'].iloc[-2], data['Volume'].iloc[-2]
            if live_c < 50: continue 

            e9, e21, rsi = data['Close'].ewm(span=9).mean().iloc[-2], data['Close'].ewm(span=21).mean().iloc[-2], calculate_rsi(data).iloc[-2]
            avg_v20 = max(data['Volume'].rolling(20).mean().iloc[-3], 1)
            whale_spike = closed_v > (avg_v20 * 1.8) # Institutional Order Block
            atr = max((data['High'] - data['Low']).rolling(14).mean().iloc[-2], 1.0)

            # SMART MONEY DECISION ENGINE (Buy or Short)
            bullish = htf_trend_up and (closed_c > e9) and (e9 > e21) and (rsi > 60) and whale_spike
            bearish = (not htf_trend_up) and (closed_c < e9) and (e9 < e21) and (rsi < 40) and whale_spike and "Intraday" in horizon
            
            if not is_bullish: bullish = False # Market down hai to Buy ko ignore karo

            if bullish or bearish:
                stock_name = ticker.replace(".NS", "")
                action = "🟢 BUY" if bullish else "🔴 SHORT SELL"
                tgt = live_c + (atr * tgt_m) if bullish else live_c - (atr * tgt_m)
                sl = live_c - (atr * sl_m) if bullish else live_c + (atr * sl_m)
                tsl = live_c - (atr * 0.5) if bullish else live_c + (atr * 0.5) # Initial Trailing SL
                
                sl_pts = abs(live_c - sl)
                qty = int(risk_amt / sl_pts) if sl_pts > 0 else 1
                lev = 5 if "Intraday" in horizon else 1
                if (qty * live_c) / lev > cap_amt: qty = int((cap_amt * lev) / live_c)
                if qty <= 0: continue 

                score = 60 + (20 if closed_v > (avg_v20*3) else 0) + (10 if rsi > 70 or rsi < 30 else 0) + (10 if gap_pct < 1.0 else 0)
                found.append({
                    "Stock": stock_name, "Horizon": horizon, "AI Score": f"{score}/100", "Action": action,
                    "Qty": qty, "Entry": round(live_c, 2), "Target": round(tgt, 2), "SL": round(sl, 2), "Trailing SL": round(tsl, 2)
                })
        except: pass
    return found

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🚀 Control Center & Scanner", "📈 Real Net Scorecard"])
raw_tickers, vix_val = load_symbols(), get_vix()

st.sidebar.markdown("### ⚙️ Pro-Trader Risk Manager")
horizon_mode = st.sidebar.selectbox("🎯 Select Trading Horizon", ["Intraday (15 Min)", "Short-Term (Daily)", "Mid-Term (Weekly)", "Long-Term (Monthly)"])

if "Intraday" in horizon_mode:
    all_tickers = list(DHAN_STOCKS.keys())
    d_client = st.sidebar.text_input("Dhan Client ID", type="password")
    d_token = st.sidebar.text_input("Access Token", type="password")
else:
    all_tickers, d_client, d_token = raw_tickers, None, None
    
capital = st.sidebar.number_input("Trading Capital (₹)", 10000, 50000, step=5000)
risk = st.sidebar.number_input("Risk Per Trade (₹)", 500, 1000, step=500)
st.session_state['max_trades'] = st.sidebar.number_input("Max Calls allowed per scan", 1, 5)

st.sidebar.markdown("---")
auto_trade_live = st.sidebar.toggle("🚨 ENABLE LIVE AUTO-EXECUTION (Real Money)", value=False)
if auto_trade_live: st.sidebar.error("⚠️ WARNING: Bot will fire Real Orders in Dhan!")

st.sidebar.info(f"📊 **India VIX:** {vix_val}")

with tab1:
    st.subheader(f"Multi-Index Weather System: {horizon_mode}")
    n_bull, bn_bull, s_bull = check_index_trend("^NSEI", "1d"), check_index_trend("^NSEBANK", "1d"), check_index_trend("^BSESN", "1d")
    is_market_bullish = n_bull or bn_bull or s_bull
    
    col1, col2, col3 = st.columns(3)
    col1.metric("NIFTY 50", "📈 BULLISH" if n_bull else "📉 BEARISH")
    col2.metric("BANKNIFTY", "📈 BULLISH" if bn_bull else "📉 BEARISH")
    col3.metric("SENSEX", "📈 BULLISH" if s_bull else "📉 BEARISH")
    
    if is_market_bullish: st.success("🟢 Market Mood: BULLISH (Bot will look for BUY breakouts)")
    else: st.error("🔴 Market Mood: BEARISH (Bot will look for SHORT SELL breakdowns in Intraday)")
    
    st.markdown("---")
    auto_mode = st.checkbox("🤖 ENABLE AUTO-PILOT MODE (Scans every 5 Mins)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock (For Testing only)", value=False)
    manual_scan = st.button("🔥 GENERATE LIVE CALLS (Manual Once)", use_container_width=True)

    if auto_mode or manual_scan:
        now = get_ist_time().time()
        if not bypass_time and "Intraday" in horizon_mode and not (datetime.time(9, 15) <= now <= datetime.time(15, 15)):
            st.warning("⏳ Market Offline!")
        else:
            st.info("⚡ Deep Scanning Active...")
            my_bar = st.progress(0)
            
            num_workers = 12 if not "Intraday" in horizon_mode else 4
            chunk_size = len(all_tickers) // num_workers + 1
            squads = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker_robot, squads[i], risk, capital, is_market_bullish, horizon_mode, d_client, d_token) for i in range(len(squads))]
                for idx, future in enumerate(concurrent.futures.as_completed(futures)):
                    if res := future.result(): all_results.extend(res)
                    my_bar.progress(int(((idx + 1) / len(squads)) * 100))

            my_bar.empty()
            if all_results:
                all_results = sorted(all_results, key=lambda x: x['AI Score'], reverse=True)
                st.success(f"🎉 BOOM! Found {len(all_results)} {horizon_mode} Calls.")
                st.dataframe(pd.DataFrame(all_results), use_container_width=True)
                save_to_portfolio(all_results, auto_trade_live, d_client, d_token)
            else:
                st.warning(f"No high-quality setups found right now.")
                
            if auto_mode:
                update_scorecard() 
                time.sleep(300)
                st.rerun()

with tab2:
    st.subheader("🏆 Trade Journal & Live P&L Tracker")
    if st.button("🔄 Refresh Live Net P&L", type="primary"):
        updated_df = update_scorecard()
        if not updated_df.empty:
            closed = updated_df[updated_df['Status'] != "Active ⏳"]
            if not closed.empty:
                net = closed['Net P&L'].sum()
                tgts, sls = len(closed[closed['Status'] == "Target Hit 🎯"]), len(closed[closed['Status'] == "SL Hit 🛑"])
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Win Rate", f"{round((tgts / (tgts + sls) * 100), 2) if (tgts + sls) > 0 else 0}%")
                col2.metric("Target Hit", tgts)
                col3.metric("SL Hit", sls)
                col4.metric("Real Net P&L (₹)", round(net, 2))
            st.dataframe(updated_df, use_container_width=True)
