"""
Pending Bet Tracker - Manages bets waiting for game results
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)

PENDING_BETS_FILE = "data/pending_bets.json"


class PendingBetTracker:
    """Track bets that are pending game results."""
    
    def __init__(self):
        self.pending_bets = self.load_pending_bets()
    
    def load_pending_bets(self) -> List[Dict]:
        """Load pending bets from file."""
        if not os.path.exists(PENDING_BETS_FILE):
            return []
        
        try:
            with open(PENDING_BETS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading pending bets: {e}")
            return []
    
    def save_pending_bets(self) -> None:
        """Save pending bets to file."""
        try:
            with open(PENDING_BETS_FILE, 'w') as f:
                json.dump(self.pending_bets, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving pending bets: {e}")
    
    def add_pending_bet(self, bet_data: Dict) -> None:
        """
        Add a bet to pending tracker.
        
        Args:
            bet_data: Dictionary with bet details including:
                - arb_id: Unique arbitrage ID
                - game_id: Game identifier
                - sport: Sport key
                - home_team: Home team name
                - away_team: Away team name
                - commence_time: Game start time (ISO format)
                - bets: List of individual bets with team, stake, odds
                - expected_profit: Expected guaranteed profit
        """
        bet_data['status'] = 'pending'
        bet_data['created_at'] = datetime.now().isoformat()
        self.pending_bets.append(bet_data)
        self.save_pending_bets()
        logger.info(f"📋 Added pending bet: {bet_data['arb_id']} for {bet_data['home_team']} vs {bet_data['away_team']}")
    
    def get_ready_to_settle(self) -> List[Dict]:
        """
        Get bets that are ready to be settled (game finished).
        Returns bets where game ended at least 3 hours ago.
        """
        now = datetime.now()
        ready = []
        
        for bet in self.pending_bets:
            if bet.get('status') != 'pending':
                continue
            
            try:
                commence_time = datetime.fromisoformat(bet['commence_time'].replace('Z', '+00:00'))
                # Assume game duration + buffer (3 hours for most sports)
                end_time = commence_time + timedelta(hours=3)
                
                if now >= end_time:
                    ready.append(bet)
            except Exception as e:
                logger.error(f"Error parsing time for bet {bet.get('arb_id')}: {e}")
        
        return ready
    
    def settle_bet(self, arb_id: str, winning_team: str, actual_profit: float) -> None:
        """
        Settle a pending bet with actual result.
        
        Args:
            arb_id: Arbitrage ID
            winning_team: Name of winning team
            actual_profit: Actual profit from the bet
        """
        for bet in self.pending_bets:
            if bet.get('arb_id') == arb_id:
                bet['status'] = 'settled'
                bet['winning_team'] = winning_team
                bet['actual_profit'] = actual_profit
                bet['settled_at'] = datetime.now().isoformat()
                
                logger.info(f"✅ Settled bet {arb_id}: Winner={winning_team}, Profit=${actual_profit:.2f}")
                self.save_pending_bets()
                return
        
        logger.warning(f"⚠️ Bet {arb_id} not found in pending bets")
    
    def get_pending_count(self) -> int:
        """Get count of pending bets."""
        return sum(1 for bet in self.pending_bets if bet.get('status') == 'pending')
    
    def cleanup_old_bets(self, days: int = 7) -> int:
        """
        Remove settled bets older than specified days.
        
        Args:
            days: Number of days to keep settled bets
            
        Returns:
            Number of bets removed
        """
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(self.pending_bets)
        
        self.pending_bets = [
            bet for bet in self.pending_bets
            if bet.get('status') == 'pending' or 
            (bet.get('settled_at') and datetime.fromisoformat(bet['settled_at']) > cutoff)
        ]
        
        removed = original_count - len(self.pending_bets)
        if removed > 0:
            self.save_pending_bets()
            logger.info(f"🧹 Cleaned up {removed} old settled bets")
        
        return removed
