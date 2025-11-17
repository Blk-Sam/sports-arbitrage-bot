import sys
import csv
import requests
import random
import time
from profit_tracker import log_bet, calculate_profit_loss
from reporting import run_report
import os

BOOKMAKER_COMMISSION = {
    "bet365": 0.05,
    "pinnacle": 0.02,
    "bodog": 0.055,
    "sportinteraction": 0.048
}
ALBERTA_BOOKS = set(BOOKMAKER_COMMISSION.keys())
MIN_MARGIN = 0.01
START_BANKROLL = 100
BANKROLL = START_BANKROLL
SIMULATION_LOG = []

API_KEY = "ff0e6bbe7f620236dc018e7c4a212e95"   # Your API key
MAX_API_CALLS = 500
api_calls_made = 0

def fetch_bulk_odds(sport_key, api_key, market="h2h", region="eu"):
    global api_calls_made
    if api_calls_made >= MAX_API_CALLS:
        print("API call limit reached.")
        return None
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": api_key,
        "markets": market,
        "regions": region
    }
    response = requests.get(url, params=params)
    api_calls_made += 1
    if response.status_code == 200:
        return response.json()
    else:
        print(f"API Error: {response.status_code} - {response.text}")
        return None

def calculate_arbitrage_with_commission(odds1, odds2, commission1, commission2, bankroll):
    payout1 = odds1 * (1 - commission1)
    payout2 = odds2 * (1 - commission2)
    stake1 = bankroll / (payout1 + payout2)
    stake2 = bankroll - stake1
    profit1 = (stake1 * odds1 * (1 - commission1)) - bankroll
    profit2 = (stake2 * odds2 * (1 - commission2)) - bankroll
    guaranteed_profit = min(profit1, profit2)
    margin = guaranteed_profit / bankroll
    return stake1, stake2, guaranteed_profit, margin

def get_random_stake(base_stake):
    noise = random.uniform(0.85, 1.15)  # +/-15% noise to bet amount
    return round(base_stake * noise, 2)

def simulate_weighted_bets(arbitrage_list):
    global BANKROLL, SIMULATION_LOG
    total_margin = sum(arb['margin'] for arb in arbitrage_list)
    if total_margin == 0:
        return

    for arb_info in arbitrage_list:
        weight = arb_info['margin'] / total_margin
        base_stake = BANKROLL * weight
        stake1 = get_random_stake(base_stake)
        stake2 = get_random_stake(base_stake)

        comm1 = arb_info['comm_1']
        comm2 = arb_info['comm_2']
        profit1 = (stake1 * arb_info['odds_1'] * (1 - comm1)) - (stake1 + stake2)
        profit2 = (stake2 * arb_info['odds_2'] * (1 - comm2)) - (stake1 + stake2)
        profit = min(profit1, profit2)

        BANKROLL += profit

        bet_log_entry = {
            "match": arb_info['teams'],
            "sport": arb_info['sport'],
            "market": arb_info['market'],
            "region": arb_info['region'],
            "bookmaker_1": arb_info['bookmaker_1'],
            "odds_1": arb_info['odds_1'],
            "stake_1": stake1,
            "bookmaker_2": arb_info['bookmaker_2'],
            "odds_2": arb_info['odds_2'],
            "stake_2": stake2,
            "profit": round(profit, 2),
            "result": "win" if profit > 0 else "lose",
            "bankroll_after": round(BANKROLL, 2),
            "margin_percent": round(arb_info['margin'], 2),
            "start_time": arb_info['start_time']
        }

        SIMULATION_LOG.append(bet_log_entry)
        log_bet(bet_log_entry)

        time.sleep(random.uniform(1, 5))  # Random delay 1-5s

def find_spread_totals_middles(valid_bms, market):
    middles = []
    outcomes = []
    for bm in valid_bms:
        for market_obj in bm['markets']:
            if market_obj['key'] == market:
                for outcome in market_obj['outcomes']:
                    name = outcome['name']
                    price = outcome['price']
                    point = outcome.get('point')
                    if name in ('Over', 'Under') and point is not None:
                        outcomes.append({
                            'bookmaker': bm['key'],
                            'name': name,
                            'price': price,
                            'point': point
                        })

    overs = [o for o in outcomes if o['name'] == 'Over']
    unders = [o for o in outcomes if o['name'] == 'Under']

    for over in overs:
        for under in unders:
            if under['point'] > over['point'] and under['bookmaker'] != over['bookmaker']:
                middles.append((over, under))

    return middles

def save_simulation_log(filename="simulation_log.csv"):
    if not SIMULATION_LOG:
        return
    keys = SIMULATION_LOG[0].keys()
    with open(filename, "w", newline="") as file:
        writer = csv.DictWriter(file, keys)
        writer.writeheader()
        writer.writerows(SIMULATION_LOG)

def main():
    SPORTS_TO_SCAN = ["basketball_nba"]
    REGIONS = ["us", "eu"]
    MARKETS = ["spreads", "totals"]

    total_tests = 0
    for sport in SPORTS_TO_SCAN:
        for region in REGIONS:
            for market in MARKETS:
                print(f"Scanning {sport} / {market} / {region}")
                odds_data = fetch_bulk_odds(sport, API_KEY, market, region)
                if not odds_data:
                    continue
                arbitrage_batch = []
                for game in odds_data:
                    valid_bms = [b for b in game["bookmakers"] if b["key"].lower() in ALBERTA_BOOKS]
                    if len(valid_bms) < 2:
                        continue
                    # No "h2h" logic needed, spreads/totals only
                    for bm in valid_bms:
                        for market_obj in bm["markets"]:
                            if market_obj["key"] == market:
                                # Middling logic for spreads/totals
                                middles = find_spread_totals_middles(valid_bms, market)
                                for over, under in middles:
                                    comm_over = BOOKMAKER_COMMISSION[over['bookmaker'].lower()]
                                    comm_under = BOOKMAKER_COMMISSION[under['bookmaker'].lower()]
                                    stake_over, stake_under, profit, margin = calculate_arbitrage_with_commission(
                                        over['price'], under['price'], comm_over, comm_under, BANKROLL
                                    )
                                    if profit > 0 and margin >= MIN_MARGIN:
                                        total_tests += 1
                                        arb_info = {
                                            'sport': sport,
                                            'region': region,
                                            'market': market,
                                            'teams': f"{game['home_team']} vs {game['away_team']}",
                                            'start_time': game['commence_time'],
                                            'bookmaker_1': over['bookmaker'],
                                            'odds_1': over['price'],
                                            'stake_1': stake_over,
                                            'comm_1': comm_over,
                                            'bookmaker_2': under['bookmaker'],
                                            'odds_2': under['price'],
                                            'stake_2': stake_under,
                                            'comm_2': comm_under,
                                            'profit': round(profit, 2),
                                            'margin': round(margin * 100, 2)
                                        }
                                        arbitrage_batch.append(arb_info)
                simulate_weighted_bets(arbitrage_batch)

    print(f"\nSimulation complete! Final bankroll: ${BANKROLL:.2f}. Bets placed: {total_tests}. Total profit: ${BANKROLL-START_BANKROLL:.2f}")
    save_simulation_log()
    print("Full simulation log saved to simulation_log.csv")
    print(f"Logged Profit/Loss (from bets): ${calculate_profit_loss():.2f}")
    print(f"Total API calls made: {api_calls_made} of {MAX_API_CALLS}")
    run_report("bet_history.csv")

if __name__ == "__main__":
    main()
