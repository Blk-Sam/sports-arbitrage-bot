import pandas as pd
import matplotlib.pyplot as plt
import os
import logging

logging.basicConfig(level=logging.INFO)

def run_report(bet_log_file="bet_history.csv", daily_pnl_file="daily_pnl.csv", pnl_chart_file="daily_pnl_chart.png"):
    if not os.path.exists(bet_log_file):
        logging.warning("No bet log found for reporting.")
        return

    try:
        df = pd.read_csv(bet_log_file, parse_dates=["timestamp"])
    except Exception as e:
        logging.error(f"Error loading bet log: {e}")
        return

    df["profit"] = pd.to_numeric(df.get("profit"), errors="coerce")
    df = df.dropna(subset=["profit"])
    if df.empty:
        logging.warning("No valid profit data in log.")
        return

    # Daily PnL Report
    daily = df.groupby(df["timestamp"].dt.date)["profit"].sum()
    daily.to_csv(daily_pnl_file)
    logging.info(f"Daily PnL saved to {daily_pnl_file}.")

    # Risk analytics
    df["cum_profit"] = df["profit"].cumsum()
    df["peak"] = df["cum_profit"].cummax()
    df["drawdown"] = df["peak"] - df["cum_profit"]
    max_drawdown = df["drawdown"].max()
    volatility = df["profit"].std()

    # Visualization
    plt.figure(figsize=(10, 6))
    plt.plot(daily.index, daily.values, marker='o', linestyle='-', color='b', label='Daily PnL')
    plt.title("Daily Profit/Loss Over Time")
    plt.xlabel("Date")
    plt.ylabel("PnL ($)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(pnl_chart_file)
    plt.close()
    logging.info(f"Visualization saved to {pnl_chart_file}.")

    desc = df["profit"].describe()
    logging.info("PnL summary: %s", desc)
    logging.info(f"Max Drawdown: {max_drawdown:.2f}, Volatility: {volatility:.2f}")

    print(f"Daily PnL saved to {daily_pnl_file}")
    print(f"Visualization saved to {pnl_chart_file}")
    print("PnL summary:\n", desc)
    print(f"Max Drawdown: {max_drawdown:.2f}")
    print(f"Volatility: {volatility:.2f}")

