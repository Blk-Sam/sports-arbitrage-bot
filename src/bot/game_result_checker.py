"""
Game Result Checker - Fetches actual game results from Odds API
"""
import logging
import requests
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class GameResultChecker:
    """Fetch real game results to settle bets accurately."""
    
    def __init__(self, api_key_manager):
        self.api_key_manager = api_key_manager
        self.base_url = "https://api.the-odds-api.com/v4"
    
    def get_game_result(self, sport: str, game_id: str) -> Optional[Dict]:
        """
        Fetch game result from Odds API.
        
        Args:
            sport: Sport key (e.g., 'basketball_nba')
            game_id: Game identifier
            
        Returns:
            Dictionary with game result or None if not found
        """
        try:
            api_key = self.api_key_manager.get_next_key()
            
            # Fetch scores endpoint
            url = f"{self.base_url}/sports/{sport}/scores/"
            params = {
                'apiKey': api_key,
                'daysFrom': 3  # Look back 3 days for completed games
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                games = response.json()
                
                # Find matching game by ID
                for game in games:
                    if game.get('id') == game_id:
                        return self._parse_game_result(game)
                
                logger.warning(f"Game {game_id} not found in results")
                return None
            else:
                logger.error(f"API error fetching results: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching game result: {e}")
            return None
    
    def _parse_game_result(self, game_data: Dict) -> Optional[Dict]:
        """
        Parse game data to determine winner.
        
        Args:
            game_data: Raw game data from API
            
        Returns:
            Dictionary with winner info or None
        """
        try:
            if not game_data.get('completed'):
                return None
            
            scores = game_data.get('scores')
            if not scores or len(scores) < 2:
                return None
            
            home_score = scores[0].get('score')
            away_score = scores[1].get('score')
            
            if home_score is None or away_score is None:
                return None
            
            home_team = game_data.get('home_team')
            away_team = game_data.get('away_team')
            
            # Determine winner
            if home_score > away_score:
                winner = home_team
            elif away_score > home_score:
                winner = away_team
            else:
                winner = 'tie'
            
            return {
                'game_id': game_data.get('id'),
                'home_team': home_team,
                'away_team': away_team,
                'home_score': home_score,
                'away_score': away_score,
                'winner': winner,
                'completed': True,
                'commence_time': game_data.get('commence_time')
            }
            
        except Exception as e:
            logger.error(f"Error parsing game result: {e}")
            return None
    
    def calculate_actual_profit(self, bet_data: Dict, winner: str) -> float:
        """
        Calculate actual profit based on game winner.
        
        Args:
            bet_data: Pending bet data with bets list
            winner: Name of winning team
            
        Returns:
            Actual profit (positive or negative)
        """
        total_stake = 0
        winning_payout = 0
        
        for bet in bet_data.get('bets', []):
            stake = bet.get('stake', 0)
            odds = bet.get('odds', 0)
            team = bet.get('team', '')
            
            total_stake += stake
            
            # Check if this bet won
            if team == winner:
                winning_payout = stake * odds
        
        # Profit = winning payout - total stakes
        actual_profit = winning_payout - total_stake
        
        return round(actual_profit, 2)
