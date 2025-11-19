import os
import time
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from data_collector import OddsDataCollector  # Use your upgraded class
import subprocess
import sys

# === CONFIGURATION ===
load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")
ADVANCE_MINUTES = int(os.getenv("ADVANCE_MINUTES", "20"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MARKETS_TO_SCAN = [m.strip() for m in os.getenv("MARKETS", "h2h").split(",") if m.strip()]
MIN_API_INTERVAL = float(os.getenv("MIN_API_INTERVAL", "2"))  # seconds between API calls

BOOKMAKERS_STR = ",".join([b.strip() for b in os.getenv("BOOKMAKERS", "").split(",") if b.strip()])

SPORT_WHITELIST = set([
    "basketball_nba",
    "icehockey_nhl",
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_ncaab"
])

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))

def get_dynamic_sleep_interval():
    now = datetime.now(timezone.utc)
    hour = now.hour
    if 4 <= hour < 10:      # Early morning downtime (few new odds)
        return 60 * 60      # 60 min
    elif 10 <= hour < 22:   # Active lines posted during day/evening
        return 15 * 60      # 15 min
    else:                   # Night/late night
        return 30 * 60      # 30 min

def get_active_sports(api_key):
    """Load only 'active' in-season sports from the Odds API, filtered by your whitelist."""
    collector = OddsDataCollector(api_key)
    try:
        active_keys = collector.fetch_sports()
        filtered = [s for s in active_keys if s in SPORT_WHITELIST]
        logging.info(f"Active in-season sports: {filtered}")
        return filtered
    except Exception as e:
        logging.error(f"Could not fetch active sports: {e}")
        return list(SPORT_WHITELIST)

def get_next_event_time(api_key, sports_to_scan, bookmakers_str, markets_to_scan, min_interval=2.0):
    """Fetch the soonest upcoming event start time across all sports with bookmaker/market batching and per-call throttling."""
    collector = OddsDataCollector(api_key)
    soonest = None
    markets_str = ",".join(markets_to_scan)
    last_call = 0
    for sport in sports_to_scan:
        now = time.time()
        elapsed = now - last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        last_call = time.time()

        games = collector.fetch_odds(sport, bookmakers=bookmakers_str, markets=markets_str)
        for game in games:
            start_str = game.get("commence_time")
            if not start_str:
                continue
            try:
                start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            except Exception:
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
        SPORTS_TO_SCAN = get_active_sports(API_KEY)
        next_event = get_next_event_time(API_KEY, SPORTS_TO_SCAN, BOOKMAKERS_STR, MARKETS_TO_SCAN, min_interval=MIN_API_INTERVAL)
        now_utc = datetime.now(timezone.utc)
        if not next_event or next_event < now_utc:
            sleep_interval = get_dynamic_sleep_interval()
            logging.info(f"No upcoming events found. Sleeping {sleep_interval//60} minutes.")
            time.sleep(sleep_interval)
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
