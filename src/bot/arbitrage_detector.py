import logging
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Any, Set, Optional
import os


# Import new Telegram notifications module
from src.notifications.telegram_notifications import send_arbitrage_alert


try:
    import aiohttp
except ImportError:
    aiohttp = None


class ArbitrageDetector:
    """
    Detects arbitrage opportunities across sports/markets and alerts via Telegram.
    Logs detected arbitrage events for reporting and dashboard analytics.
    """
    def __init__(
        self,
        outcome_count: int = 2,
        min_margin: float = 0.002,
        markets_to_scan: Optional[List[str]] = None,
        csv_log_file: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.outcome_count = outcome_count
        self.min_margin = min_margin
        self.markets_to_scan = markets_to_scan or ["h2h"]
        
        # Default CSV log file to data directory
        if csv_log_file is None:
            data_dir = os.getenv("DASHBOARD_DATA_DIR", "data")
            csv_log_file = os.path.join(data_dir, "arbitrage_log.csv")
        self.csv_log_file = csv_log_file
        
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._seen_opportunities: Set[Any] = set()
        self.logger = logger or logging.getLogger(__name__)


    def log_opportunity(self, opportunity: Dict[str, Any]) -> None:
        """Logs arbitrage opportunities to CSV."""
        if not self.csv_log_file:
            return
        import csv
        
        # Ensure data directory exists
        os.makedirs(os.path.dirname(self.csv_log_file), exist_ok=True)
        
        keys = list(opportunity.keys())
        try:
            file_exists = os.path.isfile(self.csv_log_file)
            with open(self.csv_log_file, "a", newline='') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(opportunity)
        except Exception as e:
            self.logger.error(f"Could not write to CSV log: {e}")


    def detect_arbitrage(self, games: List[Dict]) -> List[Dict]:
        """
        Core routine: Calculates inverse odds for arbitrage detection,
        logs and alerts if profitable opportunities are found.
        """
        arbitrage_opportunities = []
        for game in games:
            for market_key in self.markets_to_scan:
                best_odds = {}
                outcome_sources = {}
                # Find best odds across all bookmakers for this market
                for bookmaker in game.get("bookmakers", []):
                    for market in bookmaker.get("markets", []):
                        if market.get("key") != market_key:
                            continue
                        for outcome in market.get("outcomes", []):
                            name = outcome.get("name")
                            price = outcome.get("price")
                            if price is None or name is None:
                                continue
                            try:
                                odds = Decimal(str(price))
                                if (name not in best_odds) or (odds > best_odds[name]):
                                    best_odds[name] = odds
                                    outcome_sources[name] = bookmaker["key"]
                            except (InvalidOperation, KeyError):
                                continue


                if len(best_odds) != self.outcome_count:
                    continue  # Only proceed if all outcomes are present


                inv_sum = sum(1 / o for o in best_odds.values())
                if inv_sum < 1:
                    percent_profit = float(round((1 - inv_sum) * 100, 2))
                    if percent_profit < self.min_margin * 100:
                        continue
                    dedupe_key = (
                        game.get("id"),
                        market_key,
                        tuple(sorted((name, float(odds), outcome_sources[name]) for name, odds in best_odds.items()))
                    )
                    if dedupe_key in self._seen_opportunities:
                        continue
                    self._seen_opportunities.add(dedupe_key)


                    opportunity = {
                        "game_id": game.get("id"),
                        "home_team": game.get("home_team"),
                        "away_team": game.get("away_team"),
                        "market": market_key,
                        "outcomes": {name: float(odd) for name, odd in best_odds.items()},
                        "bookmakers": outcome_sources,
                        "percent_profit": percent_profit,
                        "commence_time": game.get("commence_time"),
                        "sport": game.get("sport_key", "Unknown")
                    }
                    arbitrage_opportunities.append(opportunity)
                    self.log_opportunity(opportunity)
                    self.logger.info("Arbitrage found: %s", opportunity)


                    # Calculate stakes and odds for beautiful notification
                    odds_list = list(best_odds.values())
                    stakes_list = self._calculate_stakes(odds_list)
                    profit = self._calculate_profit(stakes_list, odds_list)
                    
                    # Send beautiful step-by-step Telegram notification using new module
                    try:
                        send_arbitrage_alert(
                            opportunity,
                            [float(s) for s in stakes_list],
                            [float(o) for o in odds_list],
                            profit
                        )
                        self.logger.info("✅ Telegram notification sent successfully")
                    except Exception as e:
                        self.logger.error(f"❌ Failed to send Telegram notification: {e}")
                        # Fallback to simple notification
                        self._send_simple_alert(opportunity, percent_profit)
        
        return arbitrage_opportunities
    
    def _calculate_stakes(self, odds: List[Decimal], total_stake: float = 100.0) -> List[Decimal]:
        """
        Calculate optimal stakes for arbitrage opportunity.
        
        Args:
            odds: List of odds for each outcome
            total_stake: Total amount to stake
            
        Returns:
            List of stake amounts
        """
        inv_sum = sum(1 / o for o in odds)
        stakes = [Decimal(str(total_stake)) / (o * inv_sum) for o in odds]
        return stakes
    
    def _calculate_profit(self, stakes: List[Decimal], odds: List[Decimal]) -> float:
        """
        Calculate guaranteed profit from arbitrage.
        
        Args:
            stakes: List of stake amounts
            odds: List of odds
            
        Returns:
            Guaranteed profit amount
        """
        payouts = [stake * odd for stake, odd in zip(stakes, odds)]
        total_stake = sum(stakes)
        guaranteed_profit = min(payouts) - total_stake
        return float(guaranteed_profit)
    
    def _send_simple_alert(self, opportunity: Dict[str, Any], percent_profit: float) -> None:
        """
        Fallback simple alert if beautiful notification fails.
        
        Args:
            opportunity: Arbitrage opportunity details
            percent_profit: Profit percentage
        """
        from src.notifications.telegram_notifications import send_telegram_message as send_telegram_msg
        
        best_odds = opportunity.get("outcomes", {})
        outcome_sources = opportunity.get("bookmakers", {})
        
        outcome_lines = ""
        for name in best_odds:
            outcome_lines += f"- {outcome_sources.get(name, 'Unknown')}: *{name}* @ {best_odds[name]:.3f}\n"
        
        msg = (
            f"💰 *Arbitrage Opportunity!*\n"
            f"🏟️ Match: *{opportunity.get('home_team')}* vs *{opportunity.get('away_team')}*\n"
            f"📊 Market: *{opportunity.get('market')}*\n"
            f"{outcome_lines}"
            f"💸 Expected Profit: *{percent_profit:.2f}%*\n"
            f"🕒 Event Time: {opportunity.get('commence_time') or 'N/A'}"
        )
        
        try:
            send_telegram_msg(msg)
            self.logger.info("✅ Fallback Telegram notification sent")
        except Exception as e:
            self.logger.error(f"❌ Fallback notification also failed: {e}")
