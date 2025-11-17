import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from threading import Lock

BET_HISTORY_FILE = os.getenv("BET_HISTORY_FILE", "bet_history.csv")
FIELDNAMES = [
    "timestamp", "match", "sport", "market", "region", "bookmaker_1", "odds_1", "stake_1",
    "bookmaker_2", "odds_2", "stake_2", "profit", "result",
    "bankroll_after", "margin_percent", "start_time"
]

_log_lock = Lock()  # Ensures safe concurrent logging if multithreaded

def log_bet(bet_info):
    entry = {field: bet_info.get(field, "") for field in FIELDNAMES}
    entry["timestamp"] = entry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(BET_HISTORY_FILE)
    try:
        with _log_lock, open(BET_HISTORY_FILE, "a", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
    except Exception as e:
        logging.error(f"Error writing bet entry: {e}")

def calculate_profit_loss():
    total = Decimal("0")
    if not os.path.exists(BET_HISTORY_FILE):
        return total
    try:
        with open(BET_HISTORY_FILE, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for bet in reader:
                profit = bet.get("profit", "")
                if profit:
                    try:
                        total += Decimal(profit)
                    except InvalidOperation:
                        logging.warning(f"Invalid profit entry: {profit}")
    except Exception as e:
        logging.error(f"Error reading bet history: {e}")
    return float(total)
