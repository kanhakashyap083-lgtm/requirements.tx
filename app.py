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

# --- TELEGRAM SETUP ---
TELEGRAM_TOKEN = "8657774899:AAGKqx2_TgaoYAbUljSAXt5l9BzL_cnyCPE"
TELEGRAM_CHAT_ID = "8900320752"

def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, json=payload, timeout=5)
    except: pass

# --- SMART BROWSER SESSION (Fast IO Bypass) ---
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'})

# --- APP SETUP ---
st.set_page_config(page_title="Institutional Mega Algo", page_icon="🚀", layout="wide")
st.title("🚀 Institutional Mega Algo & Scorecard")
st.markdown("**(Fast Engine ⚡ | Multi-Horizon | AI Score | Smart Margin | Auto-Pilot | Telegram)**")

PORTFOLIO_FILE = "live_portfolio.csv"

# --- HELPER FUNCTIONS ---
def get_ist_time():
    return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_vix():
    try:
        vix_data = yf.Ticker("^INDIAVIX", session=session).history(period="1d")
        if not vix_data.empty:
            return round(vix_data['Close'].iloc[-1], 2)
    except: pass
    return 15.0 

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- LOAD NSE STOCKS ---
@st.cache_data
def load_symbols():
    symbols = []
    try:
        if os.path.exists("C_VAR1_29092026_2.DAT"):
            with open("C_VAR1_29092026_2.DAT", "r") as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) > 3 and parts[2] == 'EQ': 
                        symbols.append(parts[1] + ".NS")
            symbols = list(set(symbols))
        elif os.path.exists("PE_290926.csv"):
            df = pd.read_csv("PE_290926.csv")
            symbols = [str(s).strip() + ".NS" for s in df['SYMBOL'].dropna()]
    except Exception as e:
        st.error(f"❌ File Load Error: {e}")
    return symbols

# --- PORTFOLIO & TELEGRAM ALERTS ---
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    else:
        return pd.DataFrame(columns=["Date", "Horizon", "Stock", "Score", "Action", "Qty", "Entry", "Target", "SL", "Status", "Net P&L"])

def save_to_portfolio(new_trades):
    df = load_portfolio()
    today = get_ist_time().strftime("%Y-%m-%d")
    new_rows = []
    
    active_trades = len(df[(df['Status'] == "Active ⏳") & (df['Date'] == today)])
    max_allowed = st.session_state.get('max_trades', 5)
    
    for t in new_trades:
        if active_trades >= max_allowed:
            st.warning("⚠️ Max Trades limit reached! Ignoring new signals to prevent over-trading.")
            break
            
        if not ((df['Stock'] == t['Stock']) & (df['Date'] == today) & (df['Horizon'] == t['Horizon'])).any():
            new_rows.append({
                "Date": today, "Horizon": t['Horizon'], "Stock": t['Stock'], "Score": t['AI Score'], 
                "Action": t['Action'], "Qty": t['Qty'], "Entry": t['Entry'], "Target": t['Target'], 
                "SL": t['SL'], "Status": "Active ⏳", "Net P&L": 0.0
            })
            active_trades += 1
            
            msg = f"🚨 NEW {t['Horizon'].upper()} CALL!\n📈 Stock: {t['Stock']}\n🤖 AI Score: {t['AI Score']}\n🎯 Action: {t['Action']}\n💰 Entry: ₹{t['Entry']}\n🏆 Target: ₹{t['Target']}\n🛑 SL: ₹{t['SL']}\n📦 Qty: {t['Qty']}"
            send_telegram_alert(msg)
            
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df.to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard():
    df = load_portfolio()
    if df.empty: return df
    today = get_ist_time().strftime("%Y-%m-%d")
    
    for index, row in df.iterrows():
        if row['Status'] == "Active ⏳":
            try:
                check_interval = "5m" if "Intraday" in row['Horizon'] else "1d"
                data = yf.Ticker(f"{row['Stock']}.NS", session=session).history(period="5d", interval=check_interval)
                if data.empty: continue
                
                high_today = data['High'].max()
                low_today = data['Low'].min()
                
                qty = float(row['Qty'])
                entry = float(row['Entry'])
                tgt = float(row['Target'])
                sl = float(row['SL'])
                turnover_buy = qty * entry
                
                if "BUY" in row['Action']:
                    if high_today >= tgt: 
                        turnover_sell = qty * tgt
                        brokerage = (turnover_buy + turnover_sell) * 0.0005
                        gross_profit = (tgt - entry) * qty
                        net_profit = round(gross_profit - brokerage, 2)
                        
                        df.at[index, 'Net P&L'] = net_profit
                        df.at[index, 'Status'] = "Target Hit 🎯"
                        
                        msg = f"🎯 {row['Horizon']} TARGET HIT! 🥳\n📈 Stock: {row['Stock']}\n💰 Net Profit: ₹{net_profit}\n🚀 Level: ₹{tgt}\n✅ Safely Booked!"
                        send_telegram_alert(msg)
                        
                    elif low_today <= sl: 
                        turnover_sell = qty * sl
                        brokerage = (turnover_buy + turnover_sell) * 0.0005
                        gross_loss = (entry - sl) * qty
                        net_loss = round(-gross_loss - brokerage, 2)
                        
                        df.at[index, 'Net P&L'] = net_loss
                        df.at[index, 'Status'] = "SL Hit 🛑"
                        
                        msg = f"🛑 {row['Horizon']} STOPLOSS HIT\n📈 Stock: {row['Stock']}\n💔 Net Loss: ₹{net_loss}\n📉 Level: ₹{sl}"
                        send_telegram_alert(msg)
            except: pass
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- FAST WORKER ROBOT (Early Exit Logic) ---
def worker_robot(tickers, risk_amt, capital_amt, is_nifty_bullish, horizon_choice):
    found_trades = []
    
    for idx, ticker in enumerate(tickers):
        if idx % 50 == 0: gc.collect()
        
        try:
            time.sleep(0.01) # Ultra-fast scanning minimal delay
            
            # Setup Timeframes
            if "Intraday" in horizon_choice:
                ltf_p, ltf_i = "5d", "15m"  # Reduced data size for fast fetch
                htf_p, htf_i = "1mo", "1d"
                tgt_m, sl_m = 3.5, 1.5
            elif "Short-Term" in horizon_choice:
                ltf_p, ltf_i = "6mo", "1d"
                htf_p, htf_i = "1y", "1wk"
                tgt_m, sl_m = 4.0, 2.0
            elif "Mid-Term" in horizon_choice:
                ltf_p, ltf_i = "2y", "1wk"
                htf_p, htf_i = "5y", "1mo"
                tgt_m, sl_m = 5.0, 2.0
            else: 
                ltf_p, ltf_i = "5y", "1mo"
                htf_p, htf_i = None, None
                tgt_m, sl_m = 8.0, 2.0

            tkr = yf.Ticker(ticker, session=session)

            # 1. SMART EARLY EXIT (Check Higher Timeframe First to save 70% downloading time)
            htf_trend_up = True
            gap_pct = 0.0
            avg_daily_vol = 0
            
            if htf_p:
                data_htf = tkr.history(period=htf_p, interval=htf_i)
                if len(data_htf) < 22: continue
                
                htf_ema_9 = data_htf['Close'].ewm(span=9).mean().iloc[-2]
                htf_ema_21 = data_htf['Close'].ewm(span=21).mean().iloc[-2]
                htf_trend_up = htf_ema_9 > htf_ema_21
                
                # Agar Nifty Bearish hai aur HTF bhi Bearish hai, toh lower chart download hi mat karo!
                if not is_nifty_bullish and not htf_trend_up: continue
                
                # Check Daily Volume for Intraday BEFORE downloading 15m data
                if "Intraday" in horizon_choice:
                    avg_daily_vol = data_htf['Volume'].rolling(10).mean().iloc[-2]
                    if avg_daily_vol < 500000: continue
                
                # Gap Check
                prev_close = data_htf['Close'].iloc[-2]
                curr_open = data_htf['Open'].iloc[-1]
                if prev_close > 0:
                    gap_pct = abs((curr_open - prev_close) / prev_close) * 100
                    if gap_pct > 3.0: continue

            # 2. FETCH LOWER TIMEFRAME (Only for passing stocks)
            data = tkr.history(period=ltf_p, interval=ltf_i)
            if len(data) < 30: continue
            data.dropna(inplace=True)
            
            live_close = data['Close'].iloc[-1]
            if live_close < 50: continue 

            closed_close = data['Close'].iloc[-2]
            closed_vol = data['Volume'].iloc[-2]

            ema_9 = data['Close'].ewm(span=9).mean().iloc[-2]
            ema_21 = data['Close'].ewm(span=21).mean().iloc[-2]
            rsi_14 = calculate_rsi(data).iloc[-2]

            avg_vol_20 = data['Volume'].rolling(20).mean().iloc[-3]
            if pd.isna(avg_vol_20) or avg_vol_20 <= 0: avg_vol_20 = 1 
            whale_spike = closed_vol > (avg_vol_20 * 1.5)
            
            avg_range = (data['High'] - data['Low']).rolling(14).mean().iloc[-2]
            atr = avg_range if avg_range > 0.5 else 1.0 

            bullish = False
            if ("Long-Term" in horizon_choice or "Mid-Term" in horizon_choice) or is_nifty_bullish:
                bullish = htf_trend_up and (closed_close > ema_9) and (ema_9 > ema_21) and (rsi_14 > 60) and whale_spike
            
            if bullish:
                stock_name = ticker.replace(".NS", "")
                
                tgt = live_close + (atr * tgt_m) 
                sl = live_close - (atr * sl_m)
                
                sl_points = live_close - sl
                ideal_qty = int(risk_amt / sl_points) if sl_points > 0 else 1
                
                leverage = 5 if "Intraday" in horizon_choice else 1
                required_margin = (ideal_qty * live_close) / leverage 
                
                if required_margin > capital_amt:
                    ideal_qty = int((capital_amt * leverage) / live_close) 
                if ideal_qty <= 0: continue 

                score = 60 
                if closed_vol > (avg_vol_20 * 3): score += 20 
                if rsi_14 > 70: score += 10 
                if gap_pct < 1.0: score += 10 

                found_trades.append({
                    "Stock": stock_name,
                    "Horizon": horizon_choice,
                    "AI Score": f"{score}/100",
                    "Action": "🟢 BUY",
                    "Qty": ideal_qty,
                    "Entry": round(live_close, 2),
                    "Target": round(tgt, 2),
                    "SL": round(sl, 2)
                })
        except: pass
    return found_trades

# --- UI DASHBOARD ---
tab1, tab2 = st.tabs(["🚀 Control Center & Scanner", "📈 Real Net Scorecard"])

all_tickers = load_symbols()
vix_val = get_vix()

st.sidebar.markdown("### ⚙️ Pro-Trader Risk Manager")
horizon_mode = st.sidebar.selectbox("🎯 Select Trading Horizon", 
    ["Intraday (15 Min)", "Short-Term (Daily)", "Mid-Term (Weekly)", "Long-Term (Monthly)"])
    
capital = st.sidebar.number_input("Total Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk = st.sidebar.number_input("Risk Per Trade (₹)", min_value=500, value=1000, step=500)
st.session_state['max_trades'] = st.sidebar.number_input("Max Calls allowed per scan", min_value=1, value=5)

st.sidebar.markdown("---")
st.sidebar.info(f"📊 **India VIX:** {vix_val}")
if vix_val > 24: st.sidebar.error("⚠️ VIX is too High! Extreme Panic Market.")
elif vix_val < 10: st.sidebar.warning("⚠️ VIX is too Low! Dead Market.")
else: st.sidebar.success("🟢 VIX is Optimal. Safe to Trade.")

st.sidebar.success(f"✅ Master Database: {len(all_tickers)} Stocks Loaded.")

with tab1:
    st.subheader(f"Multi-Horizon Engine: {horizon_mode}")
    
    is_nifty_bullish = True 
    try:
        nifty_int = "1d" if "Intraday" in horizon_mode else "1wk"
        nifty_data = yf.Ticker("^NSEI", session=session).history(period="6mo", interval=nifty_int)
        if not nifty_data.empty and len(nifty_data) > 20:
            n_ema9 = nifty_data['Close'].ewm(span=9).mean().iloc[-1]
            n_ema21 = nifty_data['Close'].ewm(span=21).mean().iloc[-1]
            is_nifty_bullish = n_ema9 > n_ema21
    except Exception: pass
        
    if is_nifty_bullish: st.success("📈 NIFTY 50 Trend: BULLISH (Safe to BUY)")
    else: st.error("📉 NIFTY 50 Trend: BEARISH (Strict MTFA Active)")
    
    st.markdown("---")
    auto_mode = st.checkbox("🤖 ENABLE AUTO-PILOT MODE (Scans & P&L Check every 5 Mins)", value=False)
    bypass_time = st.checkbox("Bypass Time-Lock (For Testing only)", value=False)
    manual_scan = st.button("🔥 GENERATE LIVE CALLS (Manual Once)", use_container_width=True)

    if auto_mode or manual_scan:
        now = get_ist_time().time()
        market_open, market_close = datetime.time(9, 30), datetime.time(14, 45)
        
        if vix_val > 24 or vix_val < 10:
            st.error("Market VIX is not safe for trading today. Scanner aborted.")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
            
        elif "Intraday" in horizon_mode and not bypass_time and not (market_open <= now <= market_close):
            st.warning("⏳ Market Time-Lock Active! (Intraday Scan only allowed between 09:30 AM and 02:45 PM).")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
                
        elif not all_tickers:
            st.error("No Database Found! Please upload C_VAR1_29092026_2.DAT")
            if auto_mode: 
                time.sleep(60)
                st.rerun()
            
        else:
            st.info("⚡ Fast Engine Activated (Early Exit Enabled). Running 12 Squads...")
            my_bar = st.progress(0, text=f"Deploying AI Squads for {horizon_mode}... Please wait.")
            
            num_workers = 12 # INCREASED FOR FAST SCANNING WITHOUT CRASH
            chunk_size = len(all_tickers) // num_workers + 1
            squads = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker_robot, squads[i], risk, capital, is_nifty_bullish, horizon_mode) for i in range(len(squads))]
                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res: all_results.extend(res)
                    completed += 1
                    my_bar.progress(int((completed / num_workers) * 100), text=f"AI Deep Scanning... {int((completed / num_workers) * 100)}% completed")

            my_bar.empty()
            if all_results:
                all_results = sorted(all_results, key=lambda x: x['AI Score'], reverse=True)
                st.success(f"🎉 BOOM! Found {len(all_results)} {horizon_mode} Calls.")
                st.dataframe(pd.DataFrame(all_results), use_container_width=True)
                save_to_portfolio(all_results)
            else:
                st.warning(f"No high-quality {horizon_mode} Breakouts found right now.")
                
            if auto_mode:
                st.info("🔄 Checking Live P&L and Sending Telegram Alerts if Target Hit...")
                update_scorecard() 
                st.info("⏳ Auto-Pilot Active: Sleeping for 5 minutes before next scan...")
                time.sleep(300)
                st.rerun()

with tab2:
    st.subheader("🏆 Trade Journal & Live P&L Tracker")
    if st.button("🔄 Refresh Live Net P&L", type="primary"):
        with st.spinner("Calculating Brokerage & Market Prices..."):
            updated_df = update_scorecard()
        
        if updated_df.empty:
            st.info("No trades recorded yet!")
        else:
            active_trades = updated_df[updated_df['Status'] == "Active ⏳"]
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
            
            st.write("### 📝 Full Audit Journal (Brokerage Deducted)")
            st.dataframe(
                updated_df.style.applymap(
                    lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x == 'SL Hit 🛑' else ''),
                    subset=['Status']
                ), use_container_width=True
            )
            
            csv = updated_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download Full Journal Backup", data=csv, file_name="My_Algo_Journal.csv", mime="text/csv")
