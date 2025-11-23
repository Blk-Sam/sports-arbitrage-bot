from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from src/config/.env BEFORE importing anything
config_dir = Path(__file__).parent.parent / 'config'
env_path = config_dir / '.env'
load_dotenv(env_path)

# Now import everything
from src.bot.main import main
from src.bot.arbitrage_detector import ArbitrageDetector
from src.bot.api_key_manager import APIKeyManager
from src.bot.data_collector import OddsDataCollector
from src.bot.profit_tracker import log_bet
from src.bot.adaptive_poller import AdaptivePoller, RateLimiter

__all__ = [
    'main',
    'ArbitrageDetector',
    'APIKeyManager',
    'OddsDataCollector',
    'log_bet',
    'AdaptivePoller',
    'RateLimiter',
]
