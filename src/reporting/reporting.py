import pandas as pd
import matplotlib.pyplot as plt
import os
import logging
import json
import sys
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime, timedelta


# Import new Telegram notifications module
from src.notifications.telegram_notifications import (
    send_telegram_file,
    send_daily_report,
    send_telegram_message as send_telegram_msg
)


logging.basicConfig(level=logging.INFO)


# Default directories
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR", "data")
STATIC_DIR = os.getenv("STATIC_DIR", "dashboard/static")


# Ensure required directories exist
def _ensure_directories():
    """Create required directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)


_ensure_directories()


# === ADVANCED ANALYTICS ===
def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate annualized Sharpe ratio."""
    if returns.std() == 0:
        return 0.0
    excess_returns = returns - risk_free_rate
    sharpe = excess_returns.mean() / returns.std() * np.sqrt(252)  # Annualized
    return sharpe


def calculate_advanced_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate comprehensive risk and performance metrics."""
    df = df.copy()
    df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
    df = df.dropna(subset=["profit"])
    
    if df.empty:
        return {}
    
    # Cumulative metrics
    df["cum_profit"] = df["profit"].cumsum()
    df["peak"] = df["cum_profit"].cummax()
    df["drawdown"] = df["peak"] - df["cum_profit"]
    
    # Basic stats
    total_profit = df["profit"].sum()
    avg_profit = df["profit"].mean()
    median_profit = df["profit"].median()
    volatility = df["profit"].std()
    max_drawdown = df["drawdown"].max()
    
    # Win rate
    wins = (df["profit"] > 0).sum()
    losses = (df["profit"] <= 0).sum()
    total_bets = len(df)
    win_rate = wins / total_bets if total_bets > 0 else 0
    
    # Sharpe ratio
    sharpe = calculate_sharpe_ratio(df["profit"])
    
    # Profit factor
    gross_profit = df[df["profit"] > 0]["profit"].sum()
    gross_loss = abs(df[df["profit"] <= 0]["profit"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Longest win/loss streaks
    df["win"] = df["profit"] > 0
    df["streak_id"] = (df["win"] != df["win"].shift()).cumsum()
    streaks = df.groupby(["streak_id", "win"]).size()
    longest_win_streak = streaks[streaks.index.get_level_values(1) == True].max() if True in streaks.index.get_level_values(1) else 0
    longest_loss_streak = streaks[streaks.index.get_level_values(1) == False].max() if False in streaks.index.get_level_values(1) else 0
    
    # Best and worst bets
    best_bet = df["profit"].max()
    worst_bet = df["profit"].min()
    
    # Calculate ROI
    start_bankroll = float(os.getenv("START_BANKROLL", 100))
    roi = (total_profit / start_bankroll * 100) if start_bankroll > 0 else 0
    
    return {
        "total_profit": total_profit,
        "avg_profit": avg_profit,
        "median_profit": median_profit,
        "volatility": volatility,
        "max_drawdown": max_drawdown,
        "win_rate": win_rate,
        "sharpe_ratio": sharpe,
        "profit_factor": profit_factor,
        "total_bets": total_bets,
        "wins": wins,
        "losses": losses,
        "longest_win_streak": longest_win_streak,
        "longest_loss_streak": longest_loss_streak,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "best_bet": best_bet,
        "worst_bet": worst_bet,
        "start_bankroll": start_bankroll,
        "current_bankroll": start_bankroll + total_profit,
        "roi": roi
    }


def win_rate_breakdown(df: pd.DataFrame, groupby_fields: list = ["market", "sport"]) -> Dict[str, pd.DataFrame]:
    """Calculate win rate breakdown by multiple dimensions."""
    breakdowns = {}
    df = df.copy()
    df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
    df = df.dropna(subset=["profit"])
    
    for field in groupby_fields:
        if field in df.columns:
            try:
                breakdown = df.groupby(field).agg(
                    total_profit=pd.NamedAgg(column="profit", aggfunc="sum"),
                    avg_profit=pd.NamedAgg(column="profit", aggfunc="mean"),
                    win_rate=pd.NamedAgg(column="profit", aggfunc=lambda x: (x > 0).mean()),
                    num_bets=pd.NamedAgg(column="profit", aggfunc="count")
                ).sort_values("total_profit", ascending=False)
                breakdowns[field] = breakdown
                logging.info(f"Win rate breakdown by {field}:\n{breakdown}")
            except Exception as e:
                logging.error(f"Error calculating breakdown for {field}: {e}")
    
    return breakdowns


def market_edge_analytics(bet_log_file: str, groupby_field: str = "market") -> Optional[pd.DataFrame]:
    """Analyze edge by market: total/average profit, win rate, bet count."""
    if not os.path.exists(bet_log_file):
        logging.warning("No bet log found for market analytics.")
        return None
    try:
        df = pd.read_csv(bet_log_file, parse_dates=["timestamp"])
        df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
        df = df.dropna(subset=["profit"])
        market_summary = df.groupby(groupby_field).agg(
            total_profit=pd.NamedAgg(column="profit", aggfunc="sum"),
            avg_profit=pd.NamedAgg(column="profit", aggfunc="mean"),
            win_rate=pd.NamedAgg(column="result", aggfunc=lambda x: (x == "win").mean()),
            num_bets=pd.NamedAgg(column="profit", aggfunc="count")
        ).sort_values("total_profit", ascending=False)
        
        # Save to data directory
        csv_path = os.path.join(DATA_DIR, "market_edge_summary.csv")
        json_path = os.path.join(DATA_DIR, "market_edge_summary.json")
        market_summary.to_csv(csv_path)
        market_summary.to_json(json_path, orient="index")
        
        logging.info("Market-by-market analytics:\n%s", market_summary)
        logging.info(f"Saved to {csv_path} and {json_path}")
        return market_summary
    except Exception as e:
        logging.error(f"Error in market analytics: {e}")
        return None


# === VISUALIZATION ===
def create_dashboard_charts(df: pd.DataFrame, output_dir: str = None) -> list:
    """Create comprehensive multi-chart dashboard."""
    if output_dir is None:
        output_dir = STATIC_DIR
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    df = df.copy()
    df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
    df = df.dropna(subset=["profit"])
    
    if df.empty:
        logging.warning("No data for visualization.")
        return []
    
    charts = []
    
    # 1. Daily PnL with Moving Average
    try:
        daily = df.groupby(df["timestamp"].dt.date)["profit"].sum()
        plt.figure(figsize=(14, 6))
        plt.plot(daily.index, daily.values, marker='o', linestyle='-', color='b', label='Daily PnL', linewidth=2)
        plt.plot(daily.index, daily.rolling(window=7, min_periods=1).mean(), linestyle='--', color='orange', label='7D MA', linewidth=2)
        plt.axhline(y=0, color='red', linestyle=':', alpha=0.5)
        plt.title("Daily Profit/Loss Over Time", fontsize=16, fontweight='bold')
        plt.xlabel("Date", fontsize=12)
        plt.ylabel("PnL ($)", fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=10)
        plt.tight_layout()
        chart_path = os.path.join(output_dir, "daily_pnl_chart.png")
        plt.savefig(chart_path, dpi=150)
        plt.close()
        charts.append(chart_path)
        logging.info(f"Daily PnL chart saved to {chart_path}")
    except Exception as e:
        logging.error(f"Error creating daily PnL chart: {e}")
    
    # 2. Cumulative Profit
    try:
        df_sorted = df.sort_values("timestamp")
        df_sorted["cum_profit"] = df_sorted["profit"].cumsum()
        plt.figure(figsize=(14, 6))
        plt.plot(df_sorted["timestamp"], df_sorted["cum_profit"], linewidth=2, color='green')
        plt.axhline(y=0, color='red', linestyle=':', alpha=0.5)
        plt.title("Cumulative Profit Over Time", fontsize=16, fontweight='bold')
        plt.xlabel("Date", fontsize=12)
        plt.ylabel("Cumulative Profit ($)", fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        chart_path = os.path.join(output_dir, "cumulative_profit.png")
        plt.savefig(chart_path, dpi=150)
        plt.close()
        charts.append(chart_path)
        logging.info(f"Cumulative profit chart saved to {chart_path}")
    except Exception as e:
        logging.error(f"Error creating cumulative profit chart: {e}")
    
    # 3. Drawdown Chart
    try:
        df_sorted = df.sort_values("timestamp")
        df_sorted["cum_profit"] = df_sorted["profit"].cumsum()
        df_sorted["peak"] = df_sorted["cum_profit"].cummax()
        df_sorted["drawdown"] = df_sorted["peak"] - df_sorted["cum_profit"]
        plt.figure(figsize=(14, 6))
        plt.fill_between(df_sorted["timestamp"], 0, -df_sorted["drawdown"], color='red', alpha=0.3, label='Drawdown')
        plt.plot(df_sorted["timestamp"], -df_sorted["drawdown"], color='darkred', linewidth=2)
        plt.title("Drawdown Over Time", fontsize=16, fontweight='bold')
        plt.xlabel("Date", fontsize=12)
        plt.ylabel("Drawdown ($)", fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=10)
        plt.tight_layout()
        chart_path = os.path.join(output_dir, "drawdown_chart.png")
        plt.savefig(chart_path, dpi=150)
        plt.close()
        charts.append(chart_path)
        logging.info(f"Drawdown chart saved to {chart_path}")
    except Exception as e:
        logging.error(f"Error creating drawdown chart: {e}")
    
    # 4. Win Rate by Market
    try:
        if "market" in df.columns:
            market_win_rate = df.groupby("market").agg(
                win_rate=pd.NamedAgg(column="profit", aggfunc=lambda x: (x > 0).mean()),
                num_bets=pd.NamedAgg(column="profit", aggfunc="count")
            ).sort_values("win_rate", ascending=False)
            
            plt.figure(figsize=(12, 6))
            plt.bar(market_win_rate.index, market_win_rate["win_rate"] * 100, color='skyblue', edgecolor='black')
            plt.title("Win Rate by Market", fontsize=16, fontweight='bold')
            plt.xlabel("Market", fontsize=12)
            plt.ylabel("Win Rate (%)", fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.grid(True, alpha=0.3, axis='y')
            plt.tight_layout()
            chart_path = os.path.join(output_dir, "win_rate_by_market.png")
            plt.savefig(chart_path, dpi=150)
            plt.close()
            charts.append(chart_path)
            logging.info(f"Win rate by market chart saved to {chart_path}")
    except Exception as e:
        logging.error(f"Error creating win rate by market chart: {e}")
    
    # 5. Profit Distribution Histogram
    try:
        plt.figure(figsize=(12, 6))
        plt.hist(df["profit"], bins=50, color='purple', alpha=0.7, edgecolor='black')
        plt.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Break-even')
        plt.axvline(x=df["profit"].mean(), color='green', linestyle='--', linewidth=2, label=f'Mean: ${df["profit"].mean():.2f}')
        plt.title("Profit Distribution", fontsize=16, fontweight='bold')
        plt.xlabel("Profit ($)", fontsize=12)
        plt.ylabel("Frequency", fontsize=12)
        plt.legend(fontsize=10)
        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        chart_path = os.path.join(output_dir, "profit_distribution.png")
        plt.savefig(chart_path, dpi=150)
        plt.close()
        charts.append(chart_path)
        logging.info(f"Profit distribution chart saved to {chart_path}")
    except Exception as e:
        logging.error(f"Error creating profit distribution chart: {e}")
    
    return charts


def export_html_report(metrics: Dict[str, Any], breakdowns: Dict[str, pd.DataFrame], output_file: str = None) -> None:
    """Export comprehensive HTML report."""
    if output_file is None:
        output_file = os.path.join(DATA_DIR, "report.html")
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    try:
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Arbitrage Bot Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                h1 {{ color: #333; }}
                h2 {{ color: #555; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; background: white; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .metric {{ background: white; padding: 15px; margin: 10px 0; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #4CAF50; }}
                .metric-label {{ font-size: 14px; color: #666; }}
            </style>
        </head>
        <body>
            <h1>Arbitrage Bot Performance Report</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <h2>Key Metrics</h2>
            <div class="metric">
                <div class="metric-label">Total Profit</div>
                <div class="metric-value">${metrics.get('total_profit', 0):.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Win Rate</div>
                <div class="metric-value">{metrics.get('win_rate', 0)*100:.1f}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">Sharpe Ratio</div>
                <div class="metric-value">{metrics.get('sharpe_ratio', 0):.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Max Drawdown</div>
                <div class="metric-value">${metrics.get('max_drawdown', 0):.2f}</div>
            </div>
            <div class="metric">
                <div class="metric-label">Profit Factor</div>
                <div class="metric-value">{metrics.get('profit_factor', 0):.2f}</div>
            </div>
        """
        
        for field, breakdown_df in breakdowns.items():
            html += f"<h2>Breakdown by {field.title()}</h2>"
            html += breakdown_df.to_html()
        
        html += """
        </body>
        </html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html)
        logging.info(f"HTML report saved to {output_file}")
    except Exception as e:
        logging.error(f"Error creating HTML report: {e}")


# === MAIN REPORTING FUNCTION ===
def run_report(
    bet_log_file: str = None,
    daily_pnl_file: str = None,
    pnl_chart_file: str = None,
    telegram_bot_token: str = None,
    telegram_chat_id: str = None,
    top_n_bets: int = 5
) -> None:
    """Generates comprehensive report with advanced analytics, multi-chart dashboard, and Telegram notifications."""
    # Default file paths
    if bet_log_file is None:
        bet_log_file = os.path.join(DATA_DIR, "bet_history.csv")
    if daily_pnl_file is None:
        daily_pnl_file = os.path.join(DATA_DIR, "daily_pnl.csv")
    if pnl_chart_file is None:
        pnl_chart_file = os.path.join(STATIC_DIR, "daily_pnl_chart.png")
    
    if not os.path.exists(bet_log_file):
        logging.warning(f"No bet log found for reporting: {bet_log_file}")
        print(f"No bet log found: {bet_log_file}")
        return

    try:
        df = pd.read_csv(bet_log_file, parse_dates=["timestamp"])
    except Exception as e:
        logging.error(f"Error loading bet log: {e}")
        print("Could not load log due to error:", e)
        return

    # Parse fields encoded as JSON if present
    def parse_json_field(x):
        try:
            return json.loads(x.replace("'", "\"")) if isinstance(x, str) else x
        except Exception:
            return x

    for col in ("outcomes", "bookmakers"):
        if col in df.columns:
            df[col + "_parsed"] = df[col].apply(parse_json_field)

    df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
    df = df.dropna(subset=["profit"])
    if df.empty:
        logging.warning("No valid profit data in log.")
        print("No valid profit data in log.")
        return

    # Calculate advanced metrics
    metrics = calculate_advanced_metrics(df)
    
    # Win rate breakdowns
    breakdowns = win_rate_breakdown(df, groupby_fields=["market", "sport"])
    
    # Save breakdowns to data directory
    for field, breakdown_df in breakdowns.items():
        breakdown_path = os.path.join(DATA_DIR, f"breakdown_{field}.csv")
        breakdown_df.to_csv(breakdown_path)
        logging.info(f"Breakdown by {field} saved to {breakdown_path}")

    # Daily report/visualization
    daily = df.groupby(df["timestamp"].dt.date)["profit"].sum()
    daily.to_csv(daily_pnl_file)
    logging.info(f"Daily PnL saved to {daily_pnl_file}.")

    # Create comprehensive dashboard
    charts = create_dashboard_charts(df)

    # Top bets (multiway)
    if "outcomes_parsed" in df.columns:
        top_outcome_bets = df.sort_values("profit", ascending=False).head(top_n_bets)[["timestamp", "match", "outcomes_parsed", "profit"]]
        top_bets_path = os.path.join(DATA_DIR, "top_multiway_outcomes.csv")
        top_outcome_bets.to_csv(top_bets_path, index=False)
        logging.info(f"Top multi-way bets saved to {top_bets_path}")

    # Export HTML report
    export_html_report(metrics, breakdowns)

    # Save summary stats (JSON) - Convert numpy/pandas types to native Python types
    def convert_to_native(obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(item) for item in obj]
        else:
            return obj

    metrics_clean = convert_to_native(metrics)

    summary_path = os.path.join(DATA_DIR, "pnl_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(metrics_clean, f, indent=2)
    logging.info(f"Summary metrics saved to {summary_path}")

    # Telegram notifications using new module
    if telegram_bot_token and telegram_chat_id:
        # Send beautiful daily report
        send_daily_report(metrics)
        
        # Send all charts
        for chart in charts:
            if os.path.exists(chart):
                send_telegram_file(chart, caption=os.path.basename(chart))

    # Console output
    print("\n" + "="*60)
    print("ARBITRAGE BOT PERFORMANCE REPORT")
    print("="*60)
    print(f"\n💰 Total Profit: ${metrics['total_profit']:.2f}")
    print(f"📈 Average Profit: ${metrics['avg_profit']:.2f}")
    print(f"📊 Median Profit: ${metrics['median_profit']:.2f}")
    print(f"📉 Max Drawdown: ${metrics['max_drawdown']:.2f}")
    print(f"📊 Volatility: ${metrics['volatility']:.2f}")
    print(f"🎯 Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"🔢 Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"✅ Win Rate: {metrics['win_rate']*100:.1f}%")
    print(f"🎲 Total Bets: {metrics['total_bets']} (Wins: {metrics['wins']}, Losses: {metrics['losses']})")
    print(f"🔥 Longest Win Streak: {metrics['longest_win_streak']}")
    print(f"❄️ Longest Loss Streak: {metrics['longest_loss_streak']}")
    print("\n" + "="*60)

    # Market edge analytics
    market_edge_analytics(bet_log_file=bet_log_file)


if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA_DIR, "bet_history.csv")
    tg_bot = os.getenv("TELEGRAM_BOT_TOKEN")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID")
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    run_report(log_file, telegram_bot_token=tg_bot, telegram_chat_id=tg_chat, top_n_bets=top_n)
