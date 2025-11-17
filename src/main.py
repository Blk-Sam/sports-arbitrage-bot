from dotenv import load_dotenv
import os
import sys
import csv
import requests
import random
import time
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from profit_tracker import log_bet, calculate_profit_loss
from reporting import run_report
from arbitrage_detector import ArbitrageDetector

# Load environment variables
load_dotenv()
API_KEY = os.getenv("ODDS_API_KEY")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SIM_LOG_FILE = os.getenv("SIM_LOG_FILE", "simulation_log.csv")
BET_HISTORY_FILE = os.getenv("BET_HISTORY_FILE", "bet_history.csv")

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbitrage_bot.log'),
        logging.StreamHandler()
    ]
)

if not API_KEY:
    logging.critical("ODDS_API_KEY not found in environment variables")
    sys.exit(1)

class Config:
    ALBERTA_BOOKS = {'bet365', 'pinnacle', 'bodog', 'betway', 'sport_interaction'}
    MIN_MARGIN = Decimal("0.005")
    START_BANKROLL = Decimal(os.getenv("START_BANKROLL", "100"))
    MAX_STAKE_PER_ARB = Decimal("0.25")
    MAX_API_CALLS = int(os.getenv("MAX_API_CALLS", 500))
    SPORTS_TO_SCAN = os.getenv("SPORTS_TO_SCAN", "basketball_nba").split(",")
    REGIONS = os.getenv("REGIONS", "us").split(",")
    MARKETS = os.getenv("MARKETS", "h2h").split(",")
    SLIPPAGE = Decimal(os.getenv("SLIPPAGE", "0.001"))
    SIMULATE_BET_PLACEMENT = bool(int(os.getenv("SIMULATE_BET_PLACEMENT", "1")))
    API_RETRIES = int(os.getenv("API_RETRIES", 3))
    API_RETRY_BACKOFF = int(os.getenv("API_RETRY_BACKOFF", 8))

class BankrollManager:
    def __init__(self, starting_bankroll):
        self.bankroll = Decimal(starting_bankroll)
        self.start_bankroll = Decimal(starting_bankroll)
        self.bets_placed = 0
        self.total_profit = Decimal("0")

    def calculate_kelly_stake(self, margin, max_fraction=Decimal("0.25")):
        stake_fraction = min(margin * Decimal("5"), max_fraction)
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

class OddsAPIClient:
    def __init__(self, api_key, max_calls=500):
        self.api_key = api_key
        self.max_calls = max_calls
        self.calls_made = 0
        self.base_url = "https://api.the-odds-api.com/v4/sports"

    def fetch_odds(self, sport_key, market="h2h", region="us", retries=3, backoff=8):
        for attempt in range(retries):
            if self.calls_made >= self.max_calls:
                logging.warning(f"API call limit reached: {self.calls_made}/{self.max_calls}")
                return None
            url = f"{self.base_url}/{sport_key}/odds"
            params = {
                "apiKey": self.api_key,
                "markets": market,
                "regions": region,
                "oddsFormat": "decimal"
            }
            try:
                response = requests.get(url, params=params, timeout=10)
                self.calls_made += 1
                remaining = response.headers.get('x-requests-remaining')
                if remaining:
                    logging.info(f"API calls remaining: {remaining}")
                response.raise_for_status()
                data = response.json()
                if isinstance(data, list):
                    logging.info(f"Fetched {len(data)} games for {sport_key}/{market}/{region}")
                return data
            except requests.exceptions.RequestException as e:
                logging.error(f"API error (attempt {attempt+1} of {retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(backoff)
        return None

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
    return [
        bm for bm in bookmakers
        if bm.get('key', '').lower().replace('_', '') in {book.lower().replace('_', '') for book in valid_set}
    ]

def main():
    logging.info("="*60)
    logging.info("Starting Arbitrage Bot Simulation")
    logging.info("="*60)
    api_client = OddsAPIClient(API_KEY, Config.MAX_API_CALLS)
    bankroll_mgr = BankrollManager(Config.START_BANKROLL)
    arb_detector = ArbitrageDetector()
    simulation_log = []
    arbitrage_found = 0
    for sport in Config.SPORTS_TO_SCAN:
        for region in Config.REGIONS:
            for market in Config.MARKETS:
                logging.info(f"\n{'='*60}")
                logging.info(f"Scanning: {sport} | {market} | {region}")
                logging.info(f"{'='*60}")
                odds_data = api_client.fetch_odds(
                    sport, market, region, Config.API_RETRIES, Config.API_RETRY_BACKOFF
                )
                if not odds_data:
                    logging.warning(f"No data received for {sport}/{market}/{region}")
                    continue
                for game in odds_data:
                    if not all(k in game for k in ['id', 'home_team', 'away_team', 'bookmakers']):
                        logging.warning(f"Game missing fields: {game}")
                        continue
                    valid_bookmakers = filter_valid_bookmakers(
                        game.get('bookmakers', []),
                        Config.ALBERTA_BOOKS
                    )
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
                    if not arb_opportunities:
                        continue
                    for arb in arb_opportunities:
                        arbitrage_found += 1
                        max_stake = bankroll_mgr.calculate_kelly_stake(
                            Decimal(str(arb['percent_profit'])) / Decimal("100"),
                            Config.MAX_STAKE_PER_ARB
                        )
                        stake1, stake2, profit, margin = calculate_arbitrage_stakes(
                            arb['odds_1'],
                            arb['odds_2'],
                            bankroll_mgr.bankroll,
                            max_stake
                        )
                        if stake1 is None or profit is None or profit <= 0:
                            continue
                        if margin < float(Config.MIN_MARGIN):
                            logging.debug(f"Margin too low: {margin:.4f} < {float(Config.MIN_MARGIN)}")
                            continue
                        logging.info(f"\n💰 ARBITRAGE FOUND!")
                        logging.info(f"Match: {arb['home_team']} vs {arb['away_team']}")
                        logging.info(f"Book 1: {arb['bookmaker_1']} @ {arb['odds_1']:.3f} - Stake: ${stake1:.2f}")
                        logging.info(f"Book 2: {arb['bookmaker_2']} @ {arb['odds_2']:.3f} - Stake: ${stake2:.2f}")
                        logging.info(f"Expected Profit: ${profit:.2f} ({margin*100:.2f}%)")
                        if Config.SIMULATE_BET_PLACEMENT:
                            actual_profit, actual_odds1, actual_odds2 = simulate_bet_execution(
                                stake1, stake2, arb['odds_1'], arb['odds_2'], Config.SLIPPAGE
                            )
                            bankroll_mgr.update(actual_profit)
                            bet_entry = {
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'match': f"{arb['home_team']} vs {arb['away_team']}",
                                'sport': sport,
                                'market': market,
                                'region': region,
                                'bookmaker_1': arb['bookmaker_1'],
                                'odds_1': actual_odds1,
                                'stake_1': stake1,
                                'bookmaker_2': arb['bookmaker_2'],
                                'odds_2': actual_odds2,
                                'stake_2': stake2,
                                'profit': round(actual_profit, 2),
                                'result': 'win' if actual_profit > 0 else 'loss',
                                'bankroll_after': round(bankroll_mgr.bankroll, 2),
                                'margin_percent': round(margin * 100, 2),
                                'start_time': game.get('commence_time', '')
                            }
                            simulation_log.append(bet_entry)
                            log_bet(bet_entry)
                            logging.info(f"Actual Profit: ${actual_profit:.2f} | Bankroll: ${bankroll_mgr.bankroll:.2f}")
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
    logging.info(f"API calls used: {api_client.calls_made}/{api_client.max_calls}")
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
