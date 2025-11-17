import csv
import os
from datetime import datetime

BET_HISTORY_FILE = "bet_history.csv"
FIELDNAMES = [
    "timestamp", "match", "sport", "market", "region", "bookmaker_1", "odds_1", "stake_1",
    "bookmaker_2", "odds_2", "stake_2", "profit", "result",
    "bankroll_after", "margin_percent", "start_time"
]

def log_bet(bet_info):
    entry = {field: bet_info.get(field, "") for field in FIELDNAMES}
    entry["timestamp"] = entry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(BET_HISTORY_FILE)
    with open(BET_HISTORY_FILE, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)

def calculate_profit_loss():
    total = 0
    if not os.path.exists(BET_HISTORY_FILE):
        return 0
    with open(BET_HISTORY_FILE, "r", newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for bet in reader:
            try:
                if bet.get("profit"):
                    total += float(bet["profit"])
            except ValueError:
                continue
    return total
