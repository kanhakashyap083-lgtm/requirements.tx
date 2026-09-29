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

warnings.filterwarnings("ignore")

# --- APP SETUP ---
st.set_page_config(page_title="Institutional Mega Algo", page_icon="🚀", layout="wide")
st.title("🚀 Institutional Mega Algo & Scorecard")
st.markdown("**(VIX Filter | MTFA | AI Signal Score | Smart Margin | Auto-Quantity | No-Repaint)**")

PORTFOLIO_FILE = "live_portfolio.csv"

# --- HELPER FUNCTIONS ---
def get_ist_time():
    return datetime.datetime.now(pytz.timezone('Asia/Kolkata'))

def get_vix():
    try:
        vix_data = yf.Ticker("^INDIAVIX").history(period="1d")
        if not vix_data.empty:
            return round(vix_data['Close'].iloc[-1], 2)
    except:
        pass
    return 15.0 # Default safe VIX agar Yahoo fail ho jaye

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period-1, adjust=False).mean()
    ema_down = down.ewm(com=period-1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- LOAD NSE STOCKS (CSV or DAT File) ---
@st.cache_data
def load_symbols():
    symbols = []
    try:
        # Pura NSE scan karne ke liye DAT file check karega
        if os.path.exists("C_VAR1_29092026_2.DAT"):
            with open("C_VAR1_29092026_2.DAT", "r") as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) > 3 and parts[2] == 'EQ': # Sirf Equity (EQ) stocks
                        symbols.append(parts[1] + ".NS")
            symbols = list(set(symbols))
        elif os.path.exists("PE_290926.csv"):
            df = pd.read_csv("PE_290926.csv")
            symbols = [str(s).strip() + ".NS" for s in df['SYMBOL'].dropna()]
    except Exception as e:
        st.error(f"❌ File Load Error: {e}")
    return symbols

# --- PORTFOLIO & SCORECARD DATABASE ---
def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    else:
        return pd.DataFrame(columns=["Date", "Stock", "Score", "Action", "Qty", "Entry", "Target", "SL", "Status", "Net P&L"])

def save_to_portfolio(new_trades):
    df = load_portfolio()
    today = get_ist_time().strftime("%Y-%m-%d")
    new_rows = []
    
    # Check max open trades limit
    active_trades = len(df[(df['Status'] == "Active ⏳") & (df['Date'] == today)])
    max_allowed = st.session_state.get('max_trades', 5)
    
    for t in new_trades:
        if active_trades >= max_allowed:
            st.warning("⚠️ Max Trades limit reached for today! Ignoring new signals to prevent over-trading.")
            break
            
        if not ((df['Stock'] == t['Stock']) & (df['Date'] == today)).any():
            new_rows.append({
                "Date": today, "Stock": t['Stock'], "Score": t['AI Score'], "Action": t['Action'],
                "Qty": t['Qty'], "Entry": t['Entry'], "Target": t['Target'], "SL": t['SL'],
                "Status": "Active ⏳", "Net P&L": 0.0
            })
            active_trades += 1
            
    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
        df.to_csv(PORTFOLIO_FILE, index=False)

def update_scorecard():
    df = load_portfolio()
    if df.empty: return df
    today = get_ist_time().strftime("%Y-%m-%d")
    
    for index, row in df.iterrows():
        if row['Status'] == "Active ⏳" and row['Date'] == today:
            try:
                data = yf.Ticker(f"{row['Stock']}.NS").history(period="1d", interval="5m")
                if data.empty: continue
                high_today = data['High'].max()
                low_today = data['Low'].min()
                
                qty = float(row['Qty'])
                entry = float(row['Entry'])
                tgt = float(row['Target'])
                sl = float(row['SL'])
                
                # Brokerage + STT Approx (0.05% of turnover)
                turnover_buy = qty * entry
                
                if "BUY" in row['Action']:
                    if high_today >= tgt: 
                        turnover_sell = qty * tgt
                        brokerage = (turnover_buy + turnover_sell) * 0.0005
                        gross_profit = (tgt - entry) * qty
                        df.at[index, 'Net P&L'] = round(gross_profit - brokerage, 2)
                        df.at[index, 'Status'] = "Target Hit 🎯"
                    elif low_today <= sl: 
                        turnover_sell = qty * sl
                        brokerage = (turnover_buy + turnover_sell) * 0.0005
                        gross_loss = (entry - sl) * qty
                        df.at[index, 'Net P&L'] = round(-gross_loss - brokerage, 2)
                        df.at[index, 'Status'] = "SL Hit 🛑"
            except: pass
    df.to_csv(PORTFOLIO_FILE, index=False)
    return df

# --- THE MEGA WORKER ROBOT (Deep Logic) ---
def worker_robot(tickers, risk_amt, capital_amt, is_nifty_bullish):
    found_trades = []
    
    for idx, ticker in enumerate(tickers):
        # RAM Protection: Har 50 stock ke baad garbage collect
        if idx % 50 == 0: gc.collect()
        
        try:
            time.sleep(random.uniform(0.1, 0.4)) # Smart Anti-Ban Jitter
            
            # Fetch 10-day 15m data for Intraday & 1-mo Daily data for MTFA
            data_15m = yf.Ticker(ticker).history(period="10d", interval="15m")
            data_1d = yf.Ticker(ticker).history(period="1mo", interval="1d")
            
            if len(data_15m) < 30 or len(data_1d) < 22: continue
            data_15m.dropna(inplace=True)

            # 1. MTFA (Multi-Timeframe Analysis)
            daily_ema_9 = data_1d['Close'].ewm(span=9).mean().iloc[-2]
            daily_ema_21 = data_1d['Close'].ewm(span=21).mean().iloc[-2]
            daily_trend_up = daily_ema_9 > daily_ema_21
            
            # Nifty Boss Filter
            if not is_nifty_bullish and daily_trend_up: continue 
            
            # 2. Institutional Liquidity & Penny Stock Filter
            live_close = data_15m['Close'].iloc[-1]
            avg_daily_vol = data_1d['Volume'].rolling(20).mean().iloc[-2]
            if live_close < 100 or avg_daily_vol < 500000: continue

            # 3. Gap-Up/Down Trap Rejector (Max 3% allowed)
            prev_day_close = data_1d['Close'].iloc[-2]
            today_open = data_1d['Open'].iloc[-1]
            gap_pct = abs((today_open - prev_day_close) / prev_day_close) * 100
            if gap_pct > 3.0: continue

            # 4. No-Repaint 15m Logic (Use last closed candle)
            closed_close = data_15m['Close'].iloc[-2]
            closed_vol = data_15m['Volume'].iloc[-2]

            ema_9 = data_15m['Close'].ewm(span=9).mean().iloc[-2]
            ema_21 = data_15m['Close'].ewm(span=21).mean().iloc[-2]
            rsi_14 = calculate_rsi(data_15m).iloc[-2]

            avg_vol_20 = data_15m['Volume'].rolling(window=20).mean().iloc[-3]
            if pd.isna(avg_vol_20) or avg_vol_20 <= 0: avg_vol_20 = 1 
            whale_spike = closed_vol > (avg_vol_20 * 1.5)
            
            # 5. Volatility (ATR) Risk Management
            avg_range = (data_15m['High'] - data_15m['Low']).rolling(window=14).mean().iloc[-2]
            atr = avg_range if avg_range > 0.5 else 1.0 

            bullish = daily_trend_up and (closed_close > ema_9) and (ema_9 > ema_21) and (rsi_14 > 60) and whale_spike
            
            if bullish:
                stock_name = ticker.replace(".NS", "")
                
                # Entry, Target (1:2+), SL
                tgt = live_close + (atr * 3.5) 
                sl = live_close - (atr * 1.5)
                
                # 6. Smart Margin & Quantity Calculator
                sl_points = live_close - sl
                ideal_qty = int(risk_amt / sl_points) if sl_points > 0 else 1
                required_margin = (ideal_qty * live_close) / 5 # Assuming 5x leverage
                
                if required_margin > capital_amt:
                    ideal_qty = int((capital_amt * 5) / live_close) # Fallback to max capital
                if ideal_qty <= 0: continue # Insufficient capital

                # 7. AI Signal Scoring (Max 100)
                score = 60 # Base
                if closed_vol > (avg_vol_20 * 3): score += 20 # Mega Volume
                if rsi_14 > 70: score += 10 # High Momentum
                if gap_pct < 1.0: score += 10 # Flat Opening (Safe)

                found_trades.append({
                    "Stock": stock_name,
                    "AI Score": f"{score}/100 🔥",
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
capital = st.sidebar.number_input("Total Trading Capital (₹)", min_value=10000, value=50000, step=5000)
risk = st.sidebar.number_input("Risk Per Trade (₹)", min_value=500, value=1000, step=500)
st.session_state['max_trades'] = st.sidebar.number_input("Max Trades per Day", min_value=1, value=5)

st.sidebar.markdown("---")
st.sidebar.info(f"📊 **India VIX:** {vix_val}")
if vix_val > 24: st.sidebar.error("⚠️ VIX is too High! Extreme Panic Market. Trading Blocked.")
elif vix_val < 10: st.sidebar.warning("⚠️ VIX is too Low! Dead Market. Fake breakouts possible.")
else: st.sidebar.success("🟢 VIX is Optimal. Safe to Trade.")

st.sidebar.success(f"✅ Master Database: {len(all_tickers)} Stocks Loaded.")

with tab1:
    st.subheader("Market Mood & Scanner")
    
    # Nifty Trend Check
    nifty_data = yf.Ticker("^NSEI").history(period="1mo", interval="1d")
    is_nifty_bullish = True
    if len(nifty_data) > 20:
        n_ema9 = nifty_data['Close'].ewm(span=9).mean().iloc[-1]
        n_ema21 = nifty_data['Close'].ewm(span=21).mean().iloc[-1]
        is_nifty_bullish = n_ema9 > n_ema21
        
    if is_nifty_bullish: st.success("📈 NIFTY 50 Trend: BULLISH (Safe to BUY)")
    else: st.error("📉 NIFTY 50 Trend: BEARISH (Strict MTFA Active - Avoiding Traps)")
    
    bypass_time = st.checkbox("Bypass Time-Lock (For Testing only)")

    if st.button("🔥 FIRE MEGA SCANNER", use_container_width=True):
        now = get_ist_time().time()
        market_open, market_close = datetime.time(9, 30), datetime.time(14, 45)
        
        if vix_val > 24 or vix_val < 10:
            st.error("Market VIX is not safe for trading today. Scanner aborted by Risk Manager.")
        elif not bypass_time and not (market_open <= now <= market_close):
            st.warning("⏳ Market Time-Lock Active! (Scan only allowed between 09:30 AM and 02:45 PM to avoid traps).")
        elif not all_tickers:
            st.error("No Database Found! Please upload C_VAR1_29092026_2.DAT or PE_290926.csv")
        else:
            my_bar = st.progress(0, text="Deploying 15 AI Squads across NSE... Please wait.")
            num_workers = 15
            chunk_size = len(all_tickers) // num_workers + 1
            squads = [all_tickers[i:i + chunk_size] for i in range(0, len(all_tickers), chunk_size)]
            
            all_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker_robot, squads[i], risk, capital, is_nifty_bullish) for i in range(len(squads))]
                completed = 0
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res: all_results.extend(res)
                    completed += 1
                    my_bar.progress(int((completed / num_workers) * 100), text=f"AI Deep Scanning... {int((completed / num_workers) * 100)}% completed")

            my_bar.empty()
            if all_results:
                # Sort by AI Score (Top signals first)
                all_results = sorted(all_results, key=lambda x: x['AI Score'], reverse=True)
                st.success(f"🎉 BOOM! Found {len(all_results)} Institutional Breakouts.")
                st.dataframe(pd.DataFrame(all_results), use_container_width=True)
                save_to_portfolio(all_results)
            else:
                st.warning("No high-quality Operator Breakouts found right now. Wait for the perfect setup!")

with tab2:
    st.subheader("🏆 Trade Journal (Real Net P&L)")
    if st.button("🔄 Refresh Live Net P&L", type="primary"):
        with st.spinner("Calculating Brokerage & Market Prices..."):
            updated_df = update_scorecard()
        
        if updated_df.empty:
            st.info("No trades taken today. Run the Scanner first!")
        else:
            today = get_ist_time().strftime("%Y-%m-%d")
            today_trades = updated_df[updated_df['Date'] == today]
            
            total_net_pnl = today_trades['Net P&L'].sum()
            targets = len(today_trades[today_trades['Status'] == "Target Hit 🎯"])
            sls = len(today_trades[today_trades['Status'] == "SL Hit 🛑"])
            win_rate = round((targets / (targets + sls) * 100), 2) if (targets + sls) > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Win Rate 📊", f"{win_rate}%")
            col2.metric("Target Achieved 🎯", targets, delta_color="normal")
            col3.metric("Stoploss Hit 🛑", sls, delta="-", delta_color="inverse")
            col4.metric("Real Net P&L (₹) 💵", round(total_net_pnl, 2), delta=total_net_pnl)
            
            st.write("### 📝 Full Audit Journal (Brokerage Deducted)")
            st.dataframe(
                today_trades.style.applymap(
                    lambda x: 'background-color: #c8e6c9' if x == 'Target Hit 🎯' else ('background-color: #ffcdd2' if x == 'SL Hit 🛑' else ''),
                    subset=['Status']
                ), use_container_width=True
            )
            
            # Download Backup Button
            csv = updated_df.to_csv(index=False).encode('utf-8')
            st.download_button("💾 Download Full Journal Backup", data=csv, file_name="My_Algo_Journal.csv", mime="text/csv")
