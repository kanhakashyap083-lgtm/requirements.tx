import streamlit as st
import yfinance as yf
import pandas as pd
import concurrent.futures
import time
import random
import warnings
import os
import datetime

warnings.filterwarnings("ignore")

# --- APP SETUP ---
st.set_page_config(page_title="Mega Institutional Scanner", page_icon="🚀", layout="wide")
st.title("🚀 Mega Institutional Scanner & Scorecard")
st.write("Scan the NSE and automatically track your Targets and Stoplosses!")

# --- MEMORY DATABASE (PORTFOLIO) ---
PORTFOLIO_FILE = "live_portfolio.csv"

def get_ist_date():
    # Streamlit server UTC par hota hai, isliye +5:30 ghante jode hain (Indian Time)
    ist_time = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    return ist_time.strftime("%Y-%m-%d")

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    else:
        return pd.DataFrame(columns=["Date", "Stock", "Action", "Entry", "Target", "SL", "Status"])

def save_to_portfolio(new_trades):
    df = load_portfolio()
    today = get_ist_date()
    
    new_rows = []
    for t in new_trades:
        # Check karna ki aaj is stock ki entry pehle se to nahi hai
        if not ((df['Stock'] == t['Stock Symbol']) & (df['Date'] == today)).any():
            new_rows.append({
                "Date": today,
                "Stock": t['Stock Symbol'],
                "Action": t['Signal'],
                "Entry": t['Live Price (₹)'],
                "Target": t['Target 🎯 (₹)'],
                "SL": t['Stoploss 🛑 (₹)'],
                "Status": "Active ⏳"
            })
            
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df.to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard():
    df = load_portfolio()
    if df.empty: return df
    
    today = get_ist_date()
    
    for index, row in df.iterrows():
        # Sirf aaj ke 'Active' trades ko check karega
        if row['Status'] == "Active ⏳" and row['Date'] == today:
            try:
                data = yf.Ticker(f"{row['Stock']}.NS").history(period="1d", interval="5m")
                if data.empty: continue
                
                high_today = data['High'].max()
                low_today = data['Low'].min()
                
                if "BUY" in row['Action']:
                    if high_today >= row['Target']: df.at[index, 'Status'] = "Target Hit 🎯"
                    elif low_today <= row['SL']: df.at[index, 'Status'] = "SL Hit 🛑"
                else: # SELL
                    if low_today <= row['Target']: df.at[index, 'Status'] = "Target Hit 🎯"
                    elif high_today >= row['SL']: df.at[index, 'Status'] = "SL Hit 🛑"
            except:
                pass
                
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- INDICATORS & SCANNER ---
def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

@st.cache_data
def load_symbols():
    try:
        df = pd.read_csv("PE_290926.csv")
        symbols = df['SYMBOL'].dropna().astype(str).tolist()
        return [s.strip() + ".NS" for s in symbols if s.strip()]
    except:
        return []

def worker_robot(tickers):
    found_trades = []
    for ticker in tickers:
        try:
            time.sleep(random.uniform(0.1, 0.3)) 
            data = yf.Ticker(ticker).history(period="10d", interval="15m")
            data.dropna(inplace=True)
            if len(data) < 30: continue

            closed_close = data['Close'].iloc[-2]
            closed_vol = data['Volume'].iloc[-2]
            live_close = data['Close'].iloc[-1] 
            
            if live_close < 20 or closed_vol < 10000: continue

            ema_9 = data['Close'].ewm(span=9).mean().iloc[-2]
            ema_21 = data['Close'].ewm(span=21).mean().iloc[-2]
            rsi_14 = calculate_rsi(data).iloc[-2]

            avg_vol_20 = data['Volume'].rolling(window=20).mean().iloc[-3]
            if pd.isna(avg_vol_20) or avg_vol_20 <= 0: avg_vol_20 = 1 
            whale_spike = closed_vol > (avg_vol_20 * 1.5)
            
            avg_range = (data['High'] - data['Low']).rolling(window=14).mean().iloc[-2]
            atr = avg_range if avg_range > 0.5 else 1.0 

            bullish = (closed_close > ema_9) and (ema_9 > ema_21) and (rsi_14 > 60) and whale_spike
            bearish = (closed_close < ema_9) and (ema_9 < ema_21) and (rsi_14 < 40) and whale_spike

            if bullish or bearish:
                stock_name = ticker.replace(".NS", "")
                action = "🟢 BUY (Up)" if bullish else "🔴 SELL (Down)"
                tgt = live_close + (atr * 3) if bullish else live_close - (atr * 3)
                sl = live_close - (atr * 1.5) if bullish else live_close + (atr * 1.5)
                
                found_trades.append({
                    "Stock Symbol": stock_name,
                    "Signal": action,
                    "Live Price (₹)": round(live_close, 2),
                    "Target 🎯 (₹)": round(tgt, 2),
                    "Stoploss 🛑 (₹)": round(sl, 2)
                })
        except: pass
    return found_trades

# --- UI DESIGN (TABS) ---
tab1, tab2 = st.tabs(["🚀 Live Scanner", "📊 My Scorecard (Live P&L)"])

all_tickers = load_symbols()

# TAB 1: SCANNER
with tab1:
    st.info("💡 Click below to scan 2200+ stocks. Any new signals will be automatically saved to your Scorecard.")
    if st.button("🔥 FIRE MEGA SCANNER", use_container_width=True):
        if not all_tickers:
            st.error("CSV file missing!")
        else:
            my_bar = st.progress(0, text="Deploying 15 Squads... Please wait.")
            num_workers = 15
            chunk_size = len(all_tickers) // num_workers + 1
            squads = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futures = [executor.submit(worker_robot, squads[i]) for i in range(len(squads))]
                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res: all_results.extend(res)
                    completed += 1
                    my_bar.progress(int((completed / num_workers) * 100), text=f"Scanning... {int((completed / num_workers) * 100)}% completed")

            my_bar.empty()
            if all_results:
                st.success(f"🎉 Found {len(all_results)} Breakouts! Saved to Scorecard.")
                st.dataframe(pd.DataFrame(all_results), use_container_width=True)
                save_to_portfolio(all_results) # Database me save karega
            else:
                st.warning("No Operator Breakouts found right now. Market is quiet.")

# TAB 2: SCORECARD
with tab2:
    st.subheader("🏆 Today's Trade Performance")
    
    if st.button("🔄 Refresh Live Status", type="primary"):
        with st.spinner("Checking Market Prices..."):
            updated_df = update_scorecard()
        
        if updated_df.empty:
            st.info("No trades taken today. Run the Scanner first!")
        else:
            today_trades = updated_df[updated_df['Date'] == get_ist_date()]
            
            # SCORE COUNT CALCULATION
            total = len(today_trades)
            targets = len(today_trades[today_trades['Status'] == "Target Hit 🎯"])
            sls = len(today_trades[today_trades['Status'] == "SL Hit 🛑"])
            active = len(today_trades[today_trades['Status'] == "Active ⏳"])
            
            # DASHBOARD METRICS
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Signals 📡", total)
            col2.metric("Target Achieved 🎯", targets, delta_color="normal")
            col3.metric("Stoploss Hit 🛑", sls, delta="-", delta_color="inverse")
            col4.metric("Pending/Active ⏳", active)
            
            # FULL TABLE
            st.write("### 📝 Trade Journal")
            st.dataframe(
                today_trades.style.applymap(
                    lambda x: 'background-color: lightgreen' if x == 'Target Hit 🎯' else ('background-color: lightcoral' if x == 'SL Hit 🛑' else ''),
                    subset=['Status']
                ), 
                use_container_width=True
            )
