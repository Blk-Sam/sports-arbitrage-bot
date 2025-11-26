"""
Bet Settlement Job - Checks pending bets and settles with real results
"""
import os
import sys
import logging
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.bot.pending_bet_tracker import PendingBetTracker
from src.bot.game_result_checker import GameResultChecker
from src.bot.api_key_manager import APIKeyManager
from src.notifications.telegram_notifications import send_telegram_message
from dotenv import load_dotenv

# Load environment
load_dotenv('src/config/.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def settle_pending_bets():
    """Check and settle all pending bets with real game results."""
    logger.info("\n" + "=" * 70)
    logger.info("🎲 CHECKING PENDING BETS FOR SETTLEMENT")
    logger.info("=" * 70)
    
    # Initialize components
    api_key_mgr = APIKeyManager(
        max_calls=int(os.getenv("MAX_API_CALLS", 500)),
        demo_max_calls=int(os.getenv("DEMO_MAX_API_CALLS", 2000)),
        demo_phase_enabled=os.getenv("DEMO_PHASE_ENABLED", "0") == "1"
    )
    
    tracker = PendingBetTracker()
    checker = GameResultChecker(api_key_mgr)
    
    # Get bets ready to settle
    ready_bets = tracker.get_ready_to_settle()
    
    if not ready_bets:
        logger.info("📋 No bets ready to settle")
        logger.info("=" * 70)
        return
    
    logger.info(f"📋 Found {len(ready_bets)} bets ready to settle")
    
    settled_count = 0
    total_profit = 0
    
    for bet in ready_bets:
        arb_id = bet.get('arb_id')
        game_id = bet.get('game_id')
        sport = bet.get('sport', 'unknown')
        
        logger.info(f"\n🔍 Checking result for {bet['home_team']} vs {bet['away_team']}")
        
        # Fetch game result
        result = checker.get_game_result(sport, game_id)
        
        if result and result.get('completed'):
            winner = result.get('winner')
            home_score = result.get('home_score')
            away_score = result.get('away_score')
            
            logger.info(f"📊 Final Score: {result['home_team']} {home_score} - {away_score} {result['away_team']}")
            logger.info(f"🏆 Winner: {winner}")
            
            # Calculate actual profit
            actual_profit = checker.calculate_actual_profit(bet, winner)
            
            # Settle the bet
            tracker.settle_bet(arb_id, winner, actual_profit)
            
            settled_count += 1
            total_profit += actual_profit
            
            # Send Telegram notification
            profit_emoji = "💰" if actual_profit > 0 else "📉"
            msg = f"""{profit_emoji} *BET SETTLED*

🎮 Game: {bet['home_team']} vs {bet['away_team']}
📊 Score: {home_score} - {away_score}
🏆 Winner: {winner}

💵 Profit: ${actual_profit:.2f}
🎯 Expected: ${bet.get('expected_profit', 0):.2f}
"""
            send_telegram_message(msg)
            
        else:
            logger.warning(f"⚠️ Result not yet available for {arb_id}")
    
    # Cleanup old settled bets
    cleaned = tracker.cleanup_old_bets(days=7)
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ SETTLEMENT COMPLETE")
    logger.info(f"Settled: {settled_count} bets")
    logger.info(f"Total Profit: ${total_profit:.2f}")
    logger.info(f"Cleaned: {cleaned} old bets")
    logger.info(f"Still Pending: {tracker.get_pending_count()} bets")
    logger.info("=" * 70)
    
    # Send summary if bets were settled
    if settled_count > 0:
        summary = f"""📊 *Daily Settlement Summary*

✅ Bets Settled: {settled_count}
💰 Total Profit: ${total_profit:.2f}
⏳ Still Pending: {tracker.get_pending_count()}
"""
        send_telegram_message(summary)


if __name__ == "__main__":
    try:
        settle_pending_bets()
    except Exception as e:
        logger.error(f"Error in settlement job: {e}", exc_info=True)
        sys.exit(1)
