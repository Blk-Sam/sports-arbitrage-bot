import pandas as pd
import matplotlib.pyplot as plt
import os

def run_report(bet_log_file="bet_history.csv"):
    if not os.path.exists(bet_log_file):
        print("No bet log found for reporting.")
        return

    df = pd.read_csv(bet_log_file, parse_dates=["timestamp"])
    df["profit"] = pd.to_numeric(df["profit"], errors="coerce")
    df = df.dropna(subset=["profit"])
    # Daily PnL Report
    daily = df.groupby(df["timestamp"].dt.date)["profit"].sum()
    daily.to_csv("daily_pnl.csv")
    print("Daily PnL saved to daily_pnl.csv.")

    plt.figure(figsize=(10, 6))
    plt.plot(daily.index, daily.values, marker='o', linestyle='-', color='b')
    plt.title("Daily Profit/Loss Over Time")
    plt.xlabel("Date")
    plt.ylabel("PnL ($)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("daily_pnl_chart.png")
    print("Visualization saved to daily_pnl_chart.png.")

    print("PnL summary:", df["profit"].describe())
