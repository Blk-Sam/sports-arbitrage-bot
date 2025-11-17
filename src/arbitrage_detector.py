import logging
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any

class ArbitrageDetector:
    def __init__(self, outcome_count: int = 2):
        self.outcome_count = outcome_count  # allows for 2-way, 3-way, or n-way arbitrage

    def detect_arbitrage(self, games: List[Dict]) -> List[Dict]:
        """
        Scans parsed games and returns a list of arbitrage opportunities.
        Works for 2-way (default, H2H) or multi-way markets if outcome_count is set accordingly.
        """
        arbitrage_opportunities = []
        for game in games:
            # Extract all relevant markets from each bookmaker
            outcomes_by_bookmaker = []
            for bookmaker in game.get('bookmakers', []):
                for market in bookmaker.get('markets', []):
                    if market.get('key') == 'h2h' and isinstance(market.get('outcomes'), list):
                        # Optional: parametrize for total outcome count
                        outcomes = [o for o in market['outcomes'] if 'price' in o and 'name' in o]
                        if len(outcomes) == self.outcome_count:
                            outcomes_by_bookmaker.append({
                                'bookmaker': bookmaker['key'],
                                'outcomes': outcomes
                            })
            if len(outcomes_by_bookmaker) < 2:
                continue

            # Check all pairs across all outcomes
            for i in range(len(outcomes_by_bookmaker)):
                for j in range(i+1, len(outcomes_by_bookmaker)):
                    bm1 = outcomes_by_bookmaker[i]
                    bm2 = outcomes_by_bookmaker[j]
                    if len(bm1['outcomes']) != self.outcome_count or len(bm2['outcomes']) != self.outcome_count:
                        continue

                    for out1 in bm1['outcomes']:
                        for out2 in bm2['outcomes']:
                            # Only compare opposite outcomes (ensure team names differ)
                            if out1['name'] == out2['name']:
                                continue
                            try:
                                odds_1 = Decimal(str(out1['price']))
                                odds_2 = Decimal(str(out2['price']))
                            except (KeyError, InvalidOperation):
                                logging.warning("Invalid odds for arbitrage calc: %s, %s", out1, out2)
                                continue
                            inv_sum = (1 / odds_1) + (1 / odds_2)
                            if inv_sum < 1:
                                percent_profit = float(round((1-inv_sum)*100, 2))
                                opportunity = {
                                    'game_id': game.get('id'),
                                    'home_team': game.get('home_team'),
                                    'away_team': game.get('away_team'),
                                    'bookmaker_1': bm1['bookmaker'],
                                    'bookmaker_2': bm2['bookmaker'],
                                    'odds_1': float(odds_1),
                                    'odds_2': float(odds_2),
                                    'percent_profit': percent_profit
                                }
                                arbitrage_opportunities.append(opportunity)
                                logging.info("Arbitrage found: %s", opportunity)
        return arbitrage_opportunities
