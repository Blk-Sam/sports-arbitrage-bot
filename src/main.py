from dotenv import load_dotenv
import os
import sys
import csv
import random
import time
import logging
import requests
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Optional

from profit_tracker import log_bet
from reporting import run_report
from arbitrage_detector import ArbitrageDetector
from data_collector import OddsDataCollector

load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SIM_LOG_FILE = os.getenv("SIM_LOG_FILE", "simulation_log.csv")
BET_HISTORY_FILE = os.getenv("BET_HISTORY_FILE", "bet_history.csv")
START_BANKROLL = Decimal(os.getenv("START_BANKROLL", "100"))
MAX_API_CALLS = int(os.getenv("MAX_API_CALLS", 500))
SPORTS_TO_SCAN = [s.strip() for s in os.getenv("SPORTS_TO_SCAN", "basketball_nba").split(",")]
MARKETS_TO_SCAN = [m.strip() for m in os.getenv("MARKETS", "h2h").split(",") if m.strip()]
SLIPPAGE = Decimal(os.getenv("SLIPPAGE", "0.001"))
MIN_MARGIN = Decimal(os.getenv("MIN_MARGIN", "0.01"))     # Updated for 1% minimum margin
MAX_STAKE_PER_ARB = Decimal(os.getenv("MAX_STAKE_PER_ARB", "0.5"))   # Updated for higher risk per arb
SIMULATE_BET_PLACEMENT = bool(int(os.getenv("SIMULATE_BET_PLACEMENT", "1")))
API_RETRIES = int(os.getenv("API_RETRIES", 3))
API_RETRY_BACKOFF = int(os.getenv("API_RETRY_BACKOFF", 8))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ALBERTA_BOOKS = set([b.strip() for b in os.getenv("BOOKMAKERS", "").split(",") if b.strip()])

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbitrage_bot.log', mode='a'),
        logging.StreamHandler()
    ]
)

if not API_KEY:
    logging.critical("ODDS_API_KEY not found in environment variables")
    sys.exit(1)

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("No Telegram bot token or chat ID set; not sending notifications.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        logging.error(f"Telegram message failed: {e}")

class BankrollManager:
    def __init__(self, starting_bankroll):
        self.bankroll = Decimal(starting_bankroll)
        self.start_bankroll = Decimal(starting_bankroll)
        self.bets_placed = 0
        self.total_profit = Decimal("0")
        self.max_stake_per_arb = MAX_STAKE_PER_ARB

    def calculate_kelly_stake(self, margin, max_fraction=None):
        if max_fraction is None:
            max_fraction = self.max_stake_per_arb
        stake_fraction = min(margin * Decimal("10"), max_fraction)
        return self.bankroll * stake_fraction

    def update(self, profit):
        self.bankroll += Decimal(profit)
        self.total_profit += Decimal(profit)
        self.bets_placed += 1

    def get_stats(self):
        roi = ((self.bankroll - self.start_bankroll) / self.start_bankroll * 100) if self.start_bankroll else Decimal("0")
        return {
            'current': float(self.bankroll),
            'start': float(self.start_bankroll),
            'profit': float(self.total_profit),
            'roi': float(roi),
            'bets': self.bets_placed
        }

def calculate_arbitrage_stakes(odds1, odds2, bankroll, max_stake):
    try:
        odds1 = Decimal(str(odds1))
        odds2 = Decimal(str(odds2))
        bankroll = Decimal(str(bankroll))
        max_stake = Decimal(str(max_stake))
    except InvalidOperation:
        logging.error("Non-decimal input for calculate_arbitrage_stakes.")
        return None, None, None, None
    implied_prob = (1 / odds1) + (1 / odds2)
    if implied_prob >= 1:
        return None, None, None, None
    margin = (1 - implied_prob)
    total_stake = min(bankroll, max_stake)
    stake1 = total_stake / (1 + (odds1 / odds2))
    stake2 = total_stake - stake1
    payout1 = stake1 * odds1
    payout2 = stake2 * odds2
    guaranteed_profit = min(payout1, payout2) - total_stake
    return float(stake1), float(stake2), float(guaranteed_profit), float(margin)

def simulate_bet_execution(stake1, stake2, odds1, odds2, slippage):
    odds1 = Decimal(str(odds1))
    odds2 = Decimal(str(odds2))
    slippage_factor = Decimal(str(slippage))
    actual_odds1 = odds1 * (1 - Decimal(str(random.uniform(0, float(slippage_factor)))))
    actual_odds2 = odds2 * (1 - Decimal(str(random.uniform(0, float(slippage_factor)))))
    payout1 = Decimal(str(stake1)) * actual_odds1
    payout2 = Decimal(str(stake2)) * actual_odds2
    guaranteed_payout = min(payout1, payout2)
    total_stake = Decimal(str(stake1)) + Decimal(str(stake2))
    profit = guaranteed_payout - total_stake
    return float(profit), float(actual_odds1), float(actual_odds2)

def filter_valid_bookmakers(bookmakers, valid_set):
    def normalize(name):
        return name.replace("_", "").replace(" ", "").lower()
    normalized_valid = {normalize(book) for book in valid_set}
    return [
        bm for bm in bookmakers
        if normalize(bm.get('key', '')) in normalized_valid
    ]

def get_best_arbitrage(arbs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not arbs:
        return None
    return max(arbs, key=lambda x: x.get('percent_profit', 0))

def main():
    logging.info("="*60)
    logging.info("Starting Arbitrage Bot Simulation")
    logging.info("="*60)
    collector = OddsDataCollector(API_KEY, MAX_API_CALLS)
    bankroll_mgr = BankrollManager(START_BANKROLL)
    arb_detector = ArbitrageDetector()
    simulation_log = []
    arbitrage_found = 0

    bookmakers_str = ",".join(ALBERTA_BOOKS)
    markets_str = ",".join(MARKETS_TO_SCAN)

    notified_arbs = set()  # Deduplication set

    for sport in SPORTS_TO_SCAN:
        logging.info(f"\n{'='*60}")
        logging.info(f"Scanning: {sport} | {markets_str} | {bookmakers_str}")
        logging.info(f"{'='*60}")
        odds_data = collector.fetch_odds(
            sport,
            bookmakers=bookmakers_str,
            markets=markets_str,
            retries=API_RETRIES,
            backoff=API_RETRY_BACKOFF
        )
        if not odds_data:
            logging.warning(f"No data received for {sport}/{markets_str}/{bookmakers_str}")
            continue
        for game in odds_data:
            if not all(k in game for k in ['id', 'home_team', 'away_team', 'bookmakers']):
                logging.warning(f"Game missing fields: {game}")
                continue
            valid_bookmakers = filter_valid_bookmakers(game.get('bookmakers', []), ALBERTA_BOOKS)
            if len(valid_bookmakers) < 2:
                continue
            game_data = {
                'id': game.get('id'),
                'home_team': game.get('home_team'),
                'away_team': game.get('away_team'),
                'commence_time': game.get('commence_time'),
                'bookmakers': valid_bookmakers
            }
            arb_opportunities = arb_detector.detect_arbitrage([game_data])
            best_arb = get_best_arbitrage(arb_opportunities)
            if not best_arb:
                continue

            # Deduplication - notify only once per unique arb
            arb_id = (
                best_arb['game_id'],
                best_arb['home_team'],
                best_arb['away_team'],
                best_arb['bookmaker_1'],
                best_arb['odds_1'],
                best_arb['bookmaker_2'],
                best_arb['odds_2']
            )
            if arb_id in notified_arbs:
                continue
            notified_arbs.add(arb_id)

            arbitrage_found += 1
            max_stake = bankroll_mgr.calculate_kelly_stake(
                Decimal(str(best_arb['percent_profit'])) / Decimal("100"),
                MAX_STAKE_PER_ARB
            )
            stake1, stake2, profit, margin = calculate_arbitrage_stakes(
                best_arb['odds_1'], best_arb['odds_2'], bankroll_mgr.bankroll, max_stake
            )
            if stake1 is None or profit is None or profit <= 0:
                continue
            if margin < float(MIN_MARGIN):
                logging.debug(f"Margin too low: {margin:.4f} < {float(MIN_MARGIN)}")
                continue

            logging.info(f"\n💰 ARBITRAGE FOUND!")
            logging.info(f"Match: {best_arb['home_team']} vs {best_arb['away_team']}")
            logging.info(f"Place bets as follows:")
            logging.info(f"- {best_arb['bookmaker_1']}: Bet on {best_arb['home_team']} at odds {best_arb['odds_1']:.3f} — Stake: ${stake1:.2f}")
            logging.info(f"- {best_arb['bookmaker_2']}: Bet on {best_arb['away_team']} at odds {best_arb['odds_2']:.3f} — Stake: ${stake2:.2f}")
            logging.info(f"Expected Profit: ${profit:.2f} ({margin*100:.2f}%)")

            # Prepare win/loss indicator after simulation
            result_str = "Win ✅" if profit > 0 else "Loss ❌"

            telegram_msg = (
                f"💰 *Arbitrage Found!*\n"
                f"Match: {best_arb['home_team']} vs {best_arb['away_team']}\n"
                f"Place bets on:\n"
                f"- {best_arb['bookmaker_1']}: Bet on *{best_arb['home_team']}* at odds {best_arb['odds_1']:.3f} — Stake ${stake1:.2f}\n"
                f"- {best_arb['bookmaker_2']}: Bet on *{best_arb['away_team']}* at odds {best_arb['odds_2']:.3f} — Stake ${stake2:.2f}\n"
                f"Expected Profit: ${profit:.2f} ({margin*100:.2f}%)\n"
                f"Result: {result_str}"
            )
            send_telegram_message(telegram_msg)

            if SIMULATE_BET_PLACEMENT:
                actual_profit, actual_odds1, actual_odds2 = simulate_bet_execution(
                    stake1, stake2, best_arb['odds_1'], best_arb['odds_2'], SLIPPAGE
                )
                bankroll_mgr.update(actual_profit)
                bet_entry = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'match': f"{best_arb['home_team']} vs {best_arb['away_team']}",
                    'sport': sport,
                    'market': markets_str,
                    'bookmakers': bookmakers_str,
                    'bookmaker_1': best_arb['bookmaker_1'],
                    'stake_1': stake1,
                    'odds_1': actual_odds1,
                    'bookmaker_2': best_arb['bookmaker_2'],
                    'stake_2': stake2,
                    'odds_2': actual_odds2,
                    'profit': round(actual_profit, 2),
                    'result': 'win' if actual_profit > 0 else 'loss',
                    'bankroll_after': round(bankroll_mgr.bankroll, 2),
                    'margin_percent': round(margin * 100, 2),
                    'start_time': game.get('commence_time', '')
                }
                simulation_log.append(bet_entry)
                log_bet(bet_entry)
                logging.info(f"Actual Profit: ${actual_profit:.2f} | Bankroll: ${bankroll_mgr.bankroll:.2f} | Result: {bet_entry['result']}")
            time.sleep(random.uniform(0.5, 1.5))
    stats = bankroll_mgr.get_stats()
    logging.info("\n" + "="*60)
    logging.info("SIMULATION COMPLETE")
    logging.info("="*60)
    logging.info(f"Arbitrage opportunities found: {arbitrage_found}")
    logging.info(f"Bets placed: {stats['bets']}")
    logging.info(f"Starting bankroll: ${stats['start']:.2f}")
    logging.info(f"Final bankroll: ${stats['current']:.2f}")
    logging.info(f"Total profit: ${stats['profit']:.2f}")
    logging.info(f"ROI: {stats['roi']:.2f}%")
    logging.info(f"API calls used: {collector.calls_made}/{collector.max_calls}")
    logging.info("="*60)
    if simulation_log:
        with open(SIM_LOG_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=simulation_log[0].keys())
            writer.writeheader()
            writer.writerows(simulation_log)
        logging.info(f"Simulation log saved to {SIM_LOG_FILE}")
    try:
        run_report(BET_HISTORY_FILE)
    except Exception as e:
        logging.warning(f"Could not generate report: {e}")

if __name__ == "__main__":
    main()
