import sys
from pathlib import Path

# Add project root to Python path for Streamlit
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


import sys
from pathlib import Path

# Add project root to Python path for Streamlit
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
import numpy as np
import os
import time
import datetime
import hashlib
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Import new Telegram notifications module
from src.notifications.telegram_notifications import send_error_alert # type: ignore

# Import backup panel
from src.dashboard.backup_panel import render_backup_panel # type: ignore

# === CONFIGURATION ===
PASSWORD = os.getenv("DASHBOARD_PASSWORD", "arbitrage2024")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin2024")
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR", "data")
BET_LOG_FILE = os.getenv("BET_HISTORY_FILE", os.path.join(DATA_DIR, "bet_history.csv"))
PNL_FILE = os.getenv("PNL_LOG_PATH", os.path.join(DATA_DIR, "daily_pnl.csv"))
MARKET_EDGE_FILE = os.getenv("MARKET_EDGE_FILE", os.path.join(DATA_DIR, "market_edge_summary.csv"))
ERROR_LOG_FILE = os.getenv("ERROR_LOG_PATH", "logs/error.log")
SCHEDULER_LOG_FILE = os.getenv("SCHEDULER_LOG_FILE", "scheduling/scheduler_log.csv")
MANUAL_PNL_FILE = os.path.join(DATA_DIR, "manual_pnl.csv")
DB_URL = os.getenv("SCHEDULER_DB_URL", "sqlite:///scheduling/scheduler.db")
AUTO_REFRESH = int(os.getenv("DASHBOARD_REFRESH_INTERVAL", "0"))
DASHBOARD_VERSION = os.getenv("DASHBOARD_VERSION", "2.0.0")
BOT_VERSION = os.getenv("BOT_VERSION", "2.0.0")
ML_MODEL_PATH = os.getenv("PREDICTION_MODEL")
STATIC_DIR = "dashboard/static"

# === PAGE CONFIG ===
st.set_page_config(
    page_title="Arbitrage Bot Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === AUTHENTICATION SYSTEM ===
def hash_password(password: str) -> str:
    """Hash password for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()

def check_password():
    """Multi-tier authentication system with admin override."""
    
    # Initialize session state
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        st.session_state["is_admin"] = False
        st.session_state["username"] = None
    
    # If already authenticated, return True
    if st.session_state["authenticated"]:
        return True
    
    # Login form
    st.markdown("""
    <style>
    .login-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 40px;
        background: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("# 🔐 Login")
        st.markdown("---")
        
        username = st.text_input("👤 Username", key="login_username")
        password = st.text_input("🔑 Password", type="password", key="login_password")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            if st.button("🚀 Login", use_container_width=True):
                if password == ADMIN_PASSWORD:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = True
                    st.session_state["username"] = username or "Admin"
                    st.success("✅ Admin access granted!")
                    time.sleep(1)
                    st.rerun()
                elif password == PASSWORD:
                    st.session_state["authenticated"] = True
                    st.session_state["is_admin"] = False
                    st.session_state["username"] = username or "User"
                    st.success("✅ Login successful!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Invalid credentials")
                    send_error_alert("Dashboard Login", f"Failed login attempt for user: {username}", "warning")
        
        with col_b:
            if st.button("🔄 Reset", use_container_width=True):
                st.session_state.clear()
                st.rerun()
        
        st.markdown("---")
        st.caption("💡 Contact admin for access")
        st.caption(f"Dashboard v{DASHBOARD_VERSION}")
    
    return False

if not check_password():
    st.stop()

# === LOGOUT FUNCTION ===
def logout():
    """Clear session and logout."""
    st.session_state.clear()
    st.rerun()

# === UTILITY FUNCTIONS ===
@st.cache_data(ttl=300)
def load_db_table(table_name: str, db_url: str = DB_URL, limit: int = 100) -> Optional[pd.DataFrame]:
    """Load data from database table."""
    try:
        engine = create_engine(db_url)
        query = f"SELECT * FROM {table_name} ORDER BY timestamp DESC LIMIT {limit}"
        return pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"❌ Error loading {table_name} from DB: {e}")
        send_error_alert("Dashboard DB Load", str(e), "error")
        return None

@st.cache_data(ttl=300)
def load_csv_safely(file_path: str, expected_cols: Optional[List[str]] = None) -> Optional[pd.DataFrame]:
    """Load CSV file with validation."""
    if not os.path.isfile(file_path):
        return None
    try:
        df = pd.read_csv(file_path)
        if expected_cols and not set(expected_cols).issubset(df.columns):
            st.warning(f"⚠️ {os.path.basename(file_path)} missing columns: {expected_cols}")
            return None
        return df
    except Exception as e:
        st.error(f"❌ Error loading {os.path.basename(file_path)}: {e}")
        send_error_alert("Dashboard CSV Load", str(e), "error")
        return None

def filter_for_date_range(df: pd.DataFrame, date_col: str, start_date, end_date) -> pd.DataFrame:
    """Filter DataFrame by date range."""
    if df is not None and date_col in df.columns:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        if start_date and end_date:
            return df[(df[date_col] >= pd.Timestamp(start_date)) & (df[date_col] <= pd.Timestamp(end_date))]
        elif start_date:
            return df[df[date_col] >= pd.Timestamp(start_date)]
        elif end_date:
            return df[df[date_col] <= pd.Timestamp(end_date)]
    return df

def calculate_sharpe_ratio(series: pd.Series, risk_free: float = 0) -> float:
    """Calculate annualized Sharpe ratio."""
    returns = series.diff().dropna()
    if returns.std() == 0 or len(returns) == 0:
        return 0
    return (returns.mean() - risk_free) / returns.std() * np.sqrt(252)

def calculate_max_drawdown(series: pd.Series) -> float:
    """Calculate maximum drawdown."""
    if series is None or series.empty:
        return 0
    cumsum = series.cumsum()
    rolling_max = cumsum.cummax()
    drawdown = cumsum - rolling_max
    return abs(drawdown.min()) if not drawdown.empty else 0

def download_link(df: pd.DataFrame, filename: str = "export.csv"):
    """Create download button for DataFrame."""
    csv = df.to_csv(index=False).encode()
    st.download_button(
        label="📥 Export to CSV",
        data=csv,
        file_name=filename,
        mime='text/csv'
    )

# === MANUAL P&L FUNCTIONS ===
def load_manual_pnl():
    """Load manual P&L data from CSV file."""
    if os.path.exists(MANUAL_PNL_FILE):
        try:
            df = pd.read_csv(MANUAL_PNL_FILE)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            st.error(f"Error loading manual P&L data: {e}")
            return pd.DataFrame()
    return pd.DataFrame(columns=[
        'timestamp', 'sport', 'match', 'market', 'bookmaker', 
        'selection', 'stake', 'odds', 'result', 'profit_loss', 
        'bankroll', 'notes'
    ])

def save_manual_pnl(df):
    """Save manual P&L data to CSV file."""
    try:
        df.to_csv(MANUAL_PNL_FILE, index=False)
        return True
    except Exception as e:
        st.error(f"Error saving manual P&L data: {e}")
        return False

def calculate_manual_stats(df, starting_bankroll):
    """Calculate comprehensive P&L statistics."""
    if df.empty:
        return {
            'current_bankroll': starting_bankroll,
            'total_profit': 0,
            'total_stake': 0,
            'roi': 0,
            'win_rate': 0,
            'total_bets': 0,
            'wins': 0,
            'losses': 0,
            'max_drawdown': 0,
            'peak_bankroll': starting_bankroll
        }
    
    total_profit = df['profit_loss'].sum()
    total_stake = df['stake'].sum()
    current_bankroll = starting_bankroll + total_profit
    roi = (total_profit / starting_bankroll * 100) if starting_bankroll > 0 else 0
    
    wins = len(df[df['result'] == 'Win'])
    losses = len(df[df['result'] == 'Loss'])
    total_bets = len(df)
    win_rate = (wins / total_bets * 100) if total_bets > 0 else 0
    
    cumulative_profits = df['profit_loss'].cumsum()
    rolling_max = cumulative_profits.cummax()
    drawdowns = rolling_max - cumulative_profits
    max_drawdown = drawdowns.max() if not drawdowns.empty else 0
    peak_bankroll = starting_bankroll + rolling_max.max() if not rolling_max.empty else starting_bankroll
    
    return {
        'current_bankroll': current_bankroll,
        'total_profit': total_profit,
        'total_stake': total_stake,
        'roi': roi,
        'win_rate': win_rate,
        'total_bets': total_bets,
        'wins': wins,
        'losses': losses,
        'max_drawdown': max_drawdown,
        'peak_bankroll': peak_bankroll
    }

# === SIDEBAR ===
st.sidebar.title("⚙️ Dashboard Controls")

st.sidebar.markdown("---")
user_badge = "🔑 Admin" if st.session_state.get("is_admin") else "👤 User"
st.sidebar.markdown(f"**{user_badge}:** {st.session_state.get('username', 'Unknown')}")
if st.sidebar.button("🚪 Logout", use_container_width=True):
    logout()

st.sidebar.markdown("---")

data_source = st.sidebar.radio(
    "📊 Data Source",
    ["Live Bot Feed", "Upload CSV", "Live DB"]
)

today = datetime.date.today()
date_range = st.sidebar.date_input(
    "📅 Date Range",
    [today - datetime.timedelta(days=7), today]
)

refresh = st.sidebar.button("🔄 Refresh Data")

if st.session_state.get("is_admin"):
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔧 Admin Controls")
    
    if st.sidebar.button("🗑️ Clear Cache"):
        st.cache_data.clear()
        st.sidebar.success("✅ Cache cleared")
    
    if st.sidebar.button("📊 Regenerate Reports"):
        st.sidebar.info("🔄 Regenerating reports...")
        try:
            from src.reporting.reporting import run_report # type: ignore
            run_report(BET_LOG_FILE)
            st.sidebar.success("✅ Reports regenerated")
        except Exception as e:
            st.sidebar.error(f"❌ Error: {e}")
            send_error_alert("Report Regeneration", str(e), "error")
    
    show_debug = st.sidebar.checkbox("🐛 Debug Mode")
else:
    show_debug = False

# === DATA LOADING ===
df = None
status_msg = ""

if data_source == "Upload CSV":
    uploaded = st.sidebar.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        df = pd.read_csv(uploaded)
        status_msg = "✅ File uploaded successfully"
elif data_source == "Live DB":
    df = load_db_table("bets", limit=200)
    status_msg = "✅ Loaded from database"
elif os.path.isfile(BET_LOG_FILE):
    df = load_csv_safely(BET_LOG_FILE, expected_cols=["profit", "timestamp"])
    status_msg = f"✅ Loaded {os.path.basename(BET_LOG_FILE)}"
else:
    st.warning("⚠️ No data found. Connect bot, upload CSV, or choose database.")

if df is not None and not df.empty:
    unique_markets = sorted(df['market'].unique()) if 'market' in df.columns else []
    unique_sports = sorted(df['sport'].unique()) if 'sport' in df.columns else []
else:
    unique_markets, unique_sports = [], []

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filters")
market_filter = st.sidebar.multiselect("Markets", unique_markets, default=None)
sport_filter = st.sidebar.multiselect("Sports", unique_sports, default=None)

if status_msg:
    st.success(status_msg)

if show_debug and st.session_state.get("is_admin"):
    with st.expander("🐛 Debug Information"):
        st.json({
            "user": st.session_state.get("username"),
            "is_admin": st.session_state.get("is_admin"),
            "data_source": data_source,
            "df_shape": df.shape if df is not None else None,
            "date_range": str(date_range),
            "filters": {
                "markets": market_filter,
                "sports": sport_filter
            },
            "file_paths": {
                "DATA_DIR": DATA_DIR,
                "BET_LOG": BET_LOG_FILE,
                "MANUAL_PNL": MANUAL_PNL_FILE,
                "ERROR_LOG": ERROR_LOG_FILE,
                "SCHEDULER_LOG": SCHEDULER_LOG_FILE
            }
        })

if AUTO_REFRESH > 0:
    time.sleep(AUTO_REFRESH)
    st.rerun()

if refresh:
    st.cache_data.clear()
    st.rerun()

# === MAIN DASHBOARD ===
st.title("📊 Arbitrage Bot - Professional Dashboard")
st.markdown("---")

# === EXECUTIVE SUMMARY ===
df_filtered = None
profit_col = None

if df is not None and not df.empty:
    date_col = "timestamp" if "timestamp" in df.columns else ("date" if "date" in df.columns else None)
    start_date, end_date = date_range if isinstance(date_range, list) and len(date_range) == 2 else (None, None)
    df_filtered = filter_for_date_range(df, date_col, start_date, end_date) if date_col else df.copy()
    
    if market_filter:
        df_filtered = df_filtered[df_filtered["market"].isin(market_filter)]
    if sport_filter:
        df_filtered = df_filtered[df_filtered["sport"].isin(sport_filter)]
    
    total_bets = len(df_filtered)
    profit_col = "profit" if "profit" in df_filtered.columns else "PnL" if "PnL" in df_filtered.columns else None
    
    if profit_col:
        total_pnl = df_filtered[profit_col].sum()
        avg_profit = df_filtered[profit_col].mean()
        win_count = (df_filtered[profit_col] > 0).sum()
        loss_count = (df_filtered[profit_col] <= 0).sum()
        win_rate = (win_count / total_bets * 100) if total_bets > 0 else 0
        max_dd = calculate_max_drawdown(df_filtered[profit_col])
        sharpe = calculate_sharpe_ratio(df_filtered[profit_col])
    else:
        total_pnl = avg_profit = win_count = loss_count = win_rate = max_dd = sharpe = 0
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    emoji = "🟢" if total_pnl > 0 else ("🔴" if total_pnl < 0 else "⚪")
    col1.metric("💰 Total P&L", f"{emoji} ${total_pnl:,.2f}")
    col2.metric("🎲 Total Bets", f"{total_bets:,}")
    col3.metric("✅ Win Rate", f"{win_rate:.1f}%")
    col4.metric("📉 Max Drawdown", f"${max_dd:,.2f}")
    col5.metric("📊 Sharpe Ratio", f"{sharpe:.2f}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📈 Avg Profit", f"${avg_profit:,.2f}")
    col2.metric("✅ Wins", f"{win_count:,}")
    col3.metric("❌ Losses", f"{loss_count:,}")
else:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💰 Total P&L", "$0.00")
    col2.metric("🎲 Total Bets", "0")
    col3.metric("✅ Win Rate", "0%")
    col4.metric("📉 Max Drawdown", "$0.00")
    col5.metric("📊 Sharpe Ratio", "0.00")

st.markdown("---")

# === TABS ===
tabs = st.tabs([
    "📈 P&L Analysis",
    "💼 Manual P&L",
    "🏆 Leaderboard",
    "🎯 Market Edges",
    "⚠️ Risk & Exposure",
    "📋 Bet Log",
    "🚨 Errors",
    "💾 Backups",
    "🤖 ML Predictions",
    "❓ Help & About"
])

# === TAB 1: P&L ANALYSIS ===
with tabs[0]:
    st.header("📈 P&L & Drawdown Analysis")
    
    if df_filtered is not None and not df_filtered.empty and profit_col:
        df_plot = df_filtered.copy()
        date_col = "timestamp" if "timestamp" in df_plot.columns else ("date" if "date" in df_plot.columns else None)
        df_plot = df_plot.sort_values(date_col if date_col else df_plot.index)
        df_plot['cumulative_pnl'] = df_plot[profit_col].cumsum()
        
        fig = px.line(
            df_plot,
            x=date_col if date_col else df_plot.index,
            y='cumulative_pnl',
            title="Cumulative Profit & Loss",
            labels={'cumulative_pnl': 'Cumulative P&L ($)', date_col: 'Date'}
        )
        fig.update_traces(line_color='#32B897')
        st.plotly_chart(fig, use_container_width=True)
        
        df_plot['peak'] = df_plot['cumulative_pnl'].cummax()
        df_plot['drawdown'] = df_plot['cumulative_pnl'] - df_plot['peak']
        
        fig_dd = px.area(
            df_plot,
            x=date_col if date_col else df_plot.index,
            y='drawdown',
            title="Drawdown Over Time",
            labels={'drawdown': 'Drawdown ($)', date_col: 'Date'}
        )
        fig_dd.update_traces(fillcolor='rgba(255,84,89,0.3)', line_color='#C0152F')
        st.plotly_chart(fig_dd, use_container_width=True)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Latest P&L", f"${df_plot[profit_col].iloc[-1]:,.2f}")
        col2.metric("Peak P&L", f"${df_plot['cumulative_pnl'].max():,.2f}")
        col3.metric("Total Drawdown", f"${df_plot['drawdown'].min():,.2f}")
    else:
        st.info("ℹ️ No P&L data available")

# === TAB 2: MANUAL P&L ===
with tabs[1]:
    st.header("💼 Manual P&L Tracker")
    st.markdown("Track your real arbitrage betting performance manually")
    
    manual_df = load_manual_pnl()
    
    col_settings1, col_settings2 = st.columns([1, 3])
    
    with col_settings1:
        starting_bankroll = st.number_input(
            "Starting Bankroll ($)", 
            min_value=0.0, 
            value=100.0, 
            step=10.0,
            help="Your initial bankroll amount"
        )
    
    with col_settings2:
        st.markdown("")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("➕ Add New Bet")
        
        with st.form("add_bet_form", clear_on_submit=True):
            form_col1, form_col2 = st.columns(2)
            
            with form_col1:
                sport = st.selectbox("Sport", [
                    "Basketball (NBA)", 
                    "Ice Hockey (NHL)", 
                    "American Football (NFL)", 
                    "Baseball (MLB)",
                    "Soccer",
                    "Other"
                ])
                
                match = st.text_input("Match", placeholder="e.g., Lakers vs Celtics")
                
                market = st.selectbox("Market", [
                    "Moneyline (H2H)",
                    "Spread",
                    "Totals (Over/Under)",
                    "Other"
                ])
                
                bookmaker = st.text_input("Bookmaker", placeholder="e.g., FanDuel")
            
            with form_col2:
                selection = st.text_input("Selection", placeholder="e.g., Lakers ML")
                
                stake = st.number_input("Stake ($)", min_value=0.0, step=1.0)
                
                odds = st.number_input("Odds (Decimal)", min_value=1.0, step=0.01, value=2.0)
                
                result = st.selectbox("Result", ["Win", "Loss", "Push/Void"])
            
            profit_loss = st.number_input(
                "Profit/Loss ($)", 
                step=0.01,
                help="Enter actual profit (positive) or loss (negative)"
            )
            
            notes = st.text_area("Notes (Optional)", placeholder="Any additional notes about this bet")
            
            submitted = st.form_submit_button("Add Bet", type="primary")
            
            if submitted:
                if not match or not bookmaker or not selection:
                    st.error("Please fill in Match, Bookmaker, and Selection")
                elif stake <= 0:
                    st.error("Stake must be greater than 0")
                else:
                    prev_bankroll = manual_df['bankroll'].iloc[-1] if not manual_df.empty else starting_bankroll
                    new_bankroll = prev_bankroll + profit_loss
                    
                    new_bet = pd.DataFrame([{
                        'timestamp': datetime.datetime.now(),
                        'sport': sport,
                        'match': match,
                        'market': market,
                        'bookmaker': bookmaker,
                        'selection': selection,
                        'stake': stake,
                        'odds': odds,
                        'result': result,
                        'profit_loss': profit_loss,
                        'bankroll': new_bankroll,
                        'notes': notes
                    }])
                    
                    manual_df = pd.concat([manual_df, new_bet], ignore_index=True)
                    if save_manual_pnl(manual_df):
                        st.success("✅ Bet added successfully!")
                        st.rerun()
    
    with col2:
        st.subheader("📈 Statistics")
        
        stats = calculate_manual_stats(manual_df, starting_bankroll)
        
        st.metric("Current Bankroll", f"${stats['current_bankroll']:.2f}")
        st.metric("Total Profit", f"${stats['total_profit']:.2f}", 
                 delta=f"{stats['roi']:.2f}% ROI")
        st.metric("Win Rate", f"{stats['win_rate']:.1f}%",
                 delta=f"{stats['wins']}W - {stats['losses']}L")
        
        with st.expander("Advanced Stats"):
            st.write(f"**Total Bets:** {stats['total_bets']}")
            st.write(f"**Total Stake:** ${stats['total_stake']:.2f}")
            st.write(f"**Peak Bankroll:** ${stats['peak_bankroll']:.2f}")
            st.write(f"**Max Drawdown:** ${stats['max_drawdown']:.2f}")
    
    st.markdown("---")
    
    st.subheader("📋 Bet History")
    
    if manual_df.empty:
        st.info("No bets recorded yet. Add your first bet above!")
    else:
        display_col1, display_col2, display_col3 = st.columns([2, 1, 1])
        
        with display_col1:
            search = st.text_input("🔍 Search", placeholder="Search by match, bookmaker, or selection")
        
        with display_col2:
            sort_by = st.selectbox("Sort by", ["Newest First", "Oldest First", "Highest Profit", "Highest Loss"])
        
        with display_col3:
            if st.button("📥 Export CSV"):
                download_link(manual_df, f"manual_pnl_{datetime.datetime.now().strftime('%Y%m%d')}.csv")
        
        filtered_manual = manual_df.copy()
        if search:
            filtered_manual = filtered_manual[
                filtered_manual['match'].str.contains(search, case=False, na=False) |
                filtered_manual['bookmaker'].str.contains(search, case=False, na=False) |
                filtered_manual['selection'].str.contains(search, case=False, na=False)
            ]
        
        if sort_by == "Newest First":
            filtered_manual = filtered_manual.sort_values('timestamp', ascending=False)
        elif sort_by == "Oldest First":
            filtered_manual = filtered_manual.sort_values('timestamp', ascending=True)
        elif sort_by == "Highest Profit":
            filtered_manual = filtered_manual.sort_values('profit_loss', ascending=False)
        elif sort_by == "Highest Loss":
            filtered_manual = filtered_manual.sort_values('profit_loss', ascending=True)
        
        display_manual = filtered_manual[[
            'timestamp', 'sport', 'match', 'bookmaker', 
            'selection', 'stake', 'odds', 'result', 'profit_loss', 'bankroll'
        ]].copy()
        
        display_manual['timestamp'] = display_manual['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
        display_manual['stake'] = display_manual['stake'].apply(lambda x: f"${x:.2f}")
        display_manual['profit_loss'] = display_manual['profit_loss'].apply(lambda x: f"${x:.2f}")
        display_manual['bankroll'] = display_manual['bankroll'].apply(lambda x: f"${x:.2f}")
        
        st.dataframe(
            display_manual,
            use_container_width=True,
            hide_index=True
        )
        
        st.subheader("📊 Performance Visualization")
        
        viz_col1, viz_col2 = st.columns(2)
        
        with viz_col1:
            st.markdown("**Cumulative Profit**")
            cumulative_profit = manual_df['profit_loss'].cumsum()
            st.line_chart(cumulative_profit)
        
        with viz_col2:
            st.markdown("**Bankroll Over Time**")
            st.line_chart(manual_df['bankroll'])

# === TAB 3: LEADERBOARD ===
with tabs[2]:
    st.header("🏆 Performance Leaderboard")
    
    if df_filtered is not None and not df_filtered.empty and profit_col:
        leaderboard = df_filtered.groupby("market").agg(
            total_bets=(profit_col, "count"),
            total_profit=(profit_col, "sum"),
            avg_profit=(profit_col, "mean"),
            win_rate=(profit_col, lambda x: (x > 0).mean() * 100)
        ).sort_values("total_profit", ascending=False).reset_index()
        
        st.dataframe(
            leaderboard.style.format({
                'total_profit': '${:,.2f}',
                'avg_profit': '${:,.2f}',
                'win_rate': '{:.1f}%'
            }),
            use_container_width=True
        )
        
        fig = px.bar(
            leaderboard.head(10),
            x='market',
            y='total_profit',
            title="Top 10 Markets by Profit",
            labels={'total_profit': 'Total Profit ($)', 'market': 'Market'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ No leaderboard data available")

# === TAB 4: MARKET EDGES ===
with tabs[3]:
    st.header("🎯 Market Edge Rankings")
    
    if os.path.isfile(MARKET_EDGE_FILE):
        market_df = load_csv_safely(MARKET_EDGE_FILE)
        if market_df is not None:
            st.dataframe(market_df, use_container_width=True)
            download_link(market_df, "market_edges.csv")
    else:
        st.info("ℹ️ Market edge data not available. Run bot to generate analytics.")

# === TAB 5: RISK & EXPOSURE ===
with tabs[4]:
    st.header("⚠️ Risk & Exposure Panel")
    
    if df_filtered is not None and not df_filtered.empty and profit_col:
        risk_by_market = df_filtered.groupby("market").agg(
            total_exposure=(profit_col, "sum"),
            volatility=(profit_col, "std"),
            max_loss=(profit_col, "min")
        ).reset_index()
        
        st.subheader("Risk by Market")
        st.dataframe(
            risk_by_market.style.format({
                'total_exposure': '${:,.2f}',
                'volatility': '${:,.2f}',
                'max_loss': '${:,.2f}'
            }),
            use_container_width=True
        )
        
        fig = px.bar(
            risk_by_market,
            x='market',
            y='total_exposure',
            title="Exposure by Market",
            labels={'total_exposure': 'Total Exposure ($)', 'market': 'Market'}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ No risk data available")

# === TAB 6: BET LOG ===
with tabs[5]:
    st.header("📋 Bet Log")
    
    if df_filtered is not None and not df_filtered.empty:
        st.dataframe(df_filtered, use_container_width=True)
        download_link(df_filtered, "bet_log_filtered.csv")
    else:
        st.info("ℹ️ No bets to display")

# === TAB 7: ERRORS ===
with tabs[6]:
    st.header("🚨 Error & Exception Notifications")
    
    errors_found = False
    
    if os.path.isfile(ERROR_LOG_FILE):
        with open(ERROR_LOG_FILE) as f:
            err_lines = f.readlines()[-20:]
            if err_lines:
                st.error("\n".join(err_lines))
                errors_found = True
    
    if os.path.isfile(SCHEDULER_LOG_FILE):
        sched_df = load_csv_safely(SCHEDULER_LOG_FILE)
        if sched_df is not None:
            st.subheader("Recent Scheduler Events")
            st.dataframe(sched_df.tail(10), use_container_width=True)
            errors_found = True
    
    if not errors_found:
        st.success("✅ No errors detected")

# === TAB 8: BACKUPS ===
with tabs[7]:
    st.header("💾 Backup Management")
    
    if st.session_state.get("is_admin"):
        render_backup_panel()
    else:
        st.warning("⚠️ Admin access required to manage backups")
        st.info("Contact your administrator for backup management access.")

# === TAB 9: ML PREDICTIONS ===
with tabs[8]:
    st.header("🤖 ML Predictions & Overlays")
    
    if ML_MODEL_PATH and os.path.isfile(ML_MODEL_PATH):
        st.success(f"✅ Loaded ML Model: {ML_MODEL_PATH}")
        st.info("🔮 Coming soon: Expected profit predictions, bet likelihood scores, and risk overlays")
    else:
        st.info("ℹ️ No ML model configured. Set PREDICTION_MODEL environment variable.")

# === TAB 10: HELP & ABOUT ===
with tabs[9]:
    st.header("❓ Help & About")
    
    st.markdown(f"""
    ### Arbitrage Bot Dashboard v{DASHBOARD_VERSION}
    
    **Bot Version:** {BOT_VERSION}  
    **Last Updated:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    
    #### Access Levels
    - 👤 **User**: View-only access to analytics and reports
    - 🔑 **Admin**: Full access including cache management, report regeneration, and backup management
    
    #### Features
    - 📊 Real-time P&L tracking and analytics
    - 💼 Manual P&L input for real-world bet tracking
    - 🏆 Market performance leaderboard
    - 🎯 Edge analysis by market and sport
    - ⚠️ Risk monitoring and exposure tracking
    - 📋 Complete bet log with filtering
    - 🚨 Error and exception monitoring
    - 💾 Automated backup system with retention policies
    - 🤖 ML prediction integration (coming soon)
    
    #### Usage
    1. Select data source from sidebar
    2. Apply date range and market/sport filters
    3. Navigate tabs to view different analytics
    4. Use Manual P&L tab to track real bets
    5. Admin users can manage backups in Backups tab
    6. Export data using download buttons
    
    #### Backup System
    - **Automatic Backups**: Daily at midnight
    - **Manual Backups**: Create on-demand via Backups tab
    - **Retention Policy**: 
      - 7-day: Keep all daily backups
      - 30-day: Keep 1 backup per week
      - 90-day: Keep 1 backup per month
    - **Restore**: One-click restore from any backup
    
    #### File Structure
    - Data files: `{DATA_DIR}/`
    - Backups: `backups/`
    - Error logs: `{ERROR_LOG_FILE}`
    - Scheduler logs: `{SCHEDULER_LOG_FILE}`
    - Manual P&L: `{MANUAL_PNL_FILE}`
    
    #### Support
    Contact development team for support, feature requests, or custom integrations.
    """)
    
    st.markdown("---")
    st.caption("Powered by Streamlit | Built for professional arbitrage trading")

# === SIDEBAR FOOTER ===
st.sidebar.markdown("---")
st.sidebar.caption(f"Dashboard v{DASHBOARD_VERSION} | Bot v{BOT_VERSION}")
st.sidebar.caption("⚡ Professional-grade analytics")
