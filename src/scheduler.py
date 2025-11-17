import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from data_collector import OddsDataCollector  # Use your upgraded class
import subprocess
import sys

load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")
ADVANCE_MINUTES = int(os.getenv("ADVANCE_MINUTES", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SPORTS_TO_SCAN = os.getenv("SPORTS_TO_SCAN", "basketball_nba").split(",")

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

def get_next_event_time(api_key, sports_to_scan):
    collector = OddsDataCollector(api_key)
    soonest = None
    for sport in sports_to_scan:
        games = collector.fetch_odds(sport)
        for game in games:
            start_str = game.get("commence_time")
            if not start_str:
                continue
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except Exception as e:
                logging.warning(f"Could not parse start time: {start_str}")
                continue
            if soonest is None or start_dt < soonest:
                soonest = start_dt
    return soonest

def run_bot():
    now_utc = datetime.now(timezone.utc)
    logging.info("Running arbitrage bot at %s", now_utc.isoformat())
    result = subprocess.run([sys.executable, 'main.py'], capture_output=True, text=True)
    logging.info(result.stdout)
    if result.stderr:
        logging.error("Bot error: %s", result.stderr)

def dynamic_scheduler():
    logging.info("Starting dynamic event-driven scheduler.")
    while True:
        next_event = get_next_event_time(API_KEY, SPORTS_TO_SCAN)
        now_utc = datetime.now(timezone.utc)
        if not next_event or next_event < now_utc:
            logging.info("No upcoming events found. Sleeping 60 minutes.")
            time.sleep(3600)
            continue
        run_time = next_event - timedelta(minutes=ADVANCE_MINUTES)
        delay = (run_time - now_utc).total_seconds()
        if delay <= 0:
            logging.info(f"Optimal window is now (event at {next_event}). Running bot now.")
            run_bot()
            time.sleep(600)
        else:
            logging.info(f"Next event at {next_event}. Bot will run in {delay/60:.1f} minutes.")
            time.sleep(delay)
            run_bot()
            time.sleep(600)

if __name__ == "__main__":
    try:
        dynamic_scheduler()
    except KeyboardInterrupt:
        logging.info("Scheduler stopped by user.")
