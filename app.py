import streamlit as st
import yfinance as yf
import pandas as pd
import concurrent.futures
import time
import random
import warnings

warnings.filterwarnings("ignore")

# --- APP SETUP ---
st.set_page_config(page_title="Mega Institutional Scanner", page_icon="🚀", layout="wide")
st.title("🚀 Mega Institutional Scanner (2200+ Stocks)")
st.write("Scanning the entire NSE using Pro-RSI, Operator Volume, & No-Repaint logic.")

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
        yahoo_tickers = [s.strip() + ".NS" for s in symbols if s.strip()]
        return yahoo_tickers
    except Exception as e:
        st.error(f"❌ CSV File Error: {e}")
        return []

def worker_robot(tickers):
    found_trades = []
    for ticker in tickers:
        try:
            time.sleep(random.uniform(0.1, 0.4)) 
            
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
                action = "🟢 BUY" if bullish else "🔴 SELL"
                tgt = live_close + (atr * 3) if bullish else live_close - (atr * 3)
                sl = live_close - (atr * 1.5) if bullish else live_close + (atr * 1.5)
                
                found_trades.append({
                    "Stock": stock_name,
                    "Action": action,
                    "Live Entry": round(live_close, 2),
                    "Target 🎯": round(tgt, 2),
                    "Stoploss 🛑": round(sl, 2)
                })
        except Exception as e:
            pass
    return found_trades

all_tickers = load_symbols()
st.sidebar.success(f"✅ Master Database Loaded: {len(all_tickers)} Stocks")

if st.button("🔥 FIRE MEGA SCANNER", use_container_width=True):
    if not all_tickers:
        st.error("CSV file missing! Please upload PE_290926.csv to your GitHub repository.")
    else:
        progress_text = "Deploying 15 Squads to scan 2200+ stocks... Please wait."
        my_bar = st.progress(0, text=progress_text)
        
        num_workers = 15
        chunk_size = len(all_tickers) // num_workers + 1
        squads = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
        
        all_results = []
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(worker_robot, squads[i]) for i in range(len(squads))]
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res:
                    all_results.extend(res)
                completed += 1
                progress = int((completed / num_workers) * 100)
                my_bar.progress(progress, text=f"Scanning in progress... {progress}% completed")

        end_time = time.time()
        my_bar.empty()
        
        if all_results:
            st.success(f"🎉 Scan Complete in {round(end_time - start_time, 1)} seconds!")
            st.dataframe(pd.DataFrame(all_results), use_container_width=True)
        else:
            st.warning("Scan Complete. No strict operator breakouts found right now.")
