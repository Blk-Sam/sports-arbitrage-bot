import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from threading import Lock
import sys
from typing import Dict, Any, List, Optional, Tuple
import json


# Default to data directory
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR", "data")
BACKUP_DIR = "backups"

BET_HISTORY_FILE = os.getenv("BET_HISTORY_FILE", os.path.join(DATA_DIR, "bet_history.csv"))
AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", os.path.join(DATA_DIR, "audit_log.csv"))
DAILY_SUMMARY_FILE = os.getenv("DAILY_SUMMARY_FILE", os.path.join(DATA_DIR, "daily_summary.csv"))


DEFAULT_FIELDS = [
    "timestamp", "match", "sport", "market", "region",
    "bookmaker_1", "odds_1", "stake_1",
    "bookmaker_2", "odds_2", "stake_2",
    "profit", "result", "bankroll_after",
    "margin_percent", "start_time"
]


_log_lock = Lock()
logger = logging.getLogger(__name__)


# Ensure required directories exist
def _ensure_directories():
    """Create required directories if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)


_ensure_directories()


def log_bet(
    bet_info: Dict[str, Any],
    fieldnames: Optional[List[str]] = None,
    filename: Optional[str] = None,
    audit: bool = False
) -> bool:
    """
    Logs a bet to history file in a thread-safe manner.
    Optionally logs to audit trail for compliance.
    
    Args:
        bet_info: Dictionary containing bet details
        fieldnames: Custom field names (defaults to DEFAULT_FIELDS)
        filename: Custom output filename
        audit: If True, also log to audit file
        
    Returns:
        True if successful, False otherwise
    """
    fields = fieldnames or DEFAULT_FIELDS
    out_file = filename or BET_HISTORY_FILE
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    
    # Ensure required fields
    entry = {field: bet_info.get(field, "") for field in fields}
    entry["timestamp"] = entry.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    file_exists = os.path.exists(out_file)
    
    try:
        with _log_lock:
            with open(out_file, "a", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fields)
                if not file_exists:
                    writer.writeheader()
                    logger.info(f"Created new bet history file: {out_file}")
                writer.writerow(entry)
            
            # Audit logging
            if audit:
                audit_exists = os.path.exists(AUDIT_LOG_FILE)
                with open(AUDIT_LOG_FILE, "a", newline="") as auditfile:
                    audit_writer = csv.DictWriter(auditfile, fieldnames=fields)
                    if not audit_exists:
                        audit_writer.writeheader()
                        logger.info(f"Created new audit file: {AUDIT_LOG_FILE}")
                    audit_writer.writerow(entry)
        
        logger.debug(f"Bet logged successfully: {entry.get('match', 'Unknown')}")
        return True
    
    except Exception as e:
        logger.error(f"Error writing bet entry: {e}")
        return False


def calculate_profit_loss(filename: Optional[str] = None) -> float:
    """
    Calculate total net profit from bet history.
    
    Args:
        filename: Optional custom bet history file
        
    Returns:
        Total profit as float
    """
    total = Decimal("0")
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return float(total)
    
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for bet in reader:
                profit = bet.get("profit", "")
                if profit:
                    try:
                        total += Decimal(profit)
                    except InvalidOperation:
                        logger.warning(f"Invalid profit entry: {profit}")
    except Exception as e:
        logger.error(f"Error reading bet history: {e}")
    
    return float(round(total, 6))


def get_total_profit(filename: Optional[str] = None) -> float:
    """
    Alias for calculate_profit_loss for backward compatibility.
    
    Args:
        filename: Optional custom bet history file
        
    Returns:
        Total profit as float
    """
    return calculate_profit_loss(filename)


def get_total_stats(filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate comprehensive statistics from bet history.
    
    Args:
        filename: Optional custom bet history file
        
    Returns:
        Dictionary with total bets, wins, losses, profit, ROI, win rate, etc.
    """
    total_bets = 0
    win_count = 0
    loss_count = 0
    net_profit = Decimal("0")
    total_stake = Decimal("0")
    start_bankroll = Decimal(os.getenv("START_BANKROLL", "100"))
    
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return {
            "total": 0,
            "wins": 0,
            "losses": 0,
            "profit": 0.0,
            "roi": 0.0,
            "win_rate": 0.0,
            "avg_profit": 0.0,
            "total_stake": 0.0
        }
    
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for bet in reader:
                total_bets += 1
                
                # Count wins/losses
                result = bet.get("result", "")
                if result == "win":
                    win_count += 1
                elif result == "loss":
                    loss_count += 1
                
                # Sum profit
                profit = bet.get("profit", "")
                try:
                    net_profit += Decimal(profit)
                except (InvalidOperation, TypeError, ValueError):
                    pass
                
                # Sum stakes
                stake_1 = bet.get("stake_1", "0")
                stake_2 = bet.get("stake_2", "0")
                try:
                    total_stake += Decimal(stake_1) + Decimal(stake_2)
                except (InvalidOperation, TypeError, ValueError):
                    pass
        
        # Calculate derived metrics
        roi = (float(net_profit) / float(start_bankroll) * 100) if start_bankroll > 0 else 0.0
        win_rate = (win_count / total_bets * 100) if total_bets > 0 else 0.0
        avg_profit = float(net_profit) / total_bets if total_bets > 0 else 0.0
        
        return {
            "total": total_bets,
            "wins": win_count,
            "losses": loss_count,
            "profit": float(round(net_profit, 6)),
            "roi": float(round(roi, 4)),
            "win_rate": float(round(win_rate, 2)),
            "avg_profit": float(round(avg_profit, 4)),
            "total_stake": float(round(total_stake, 2))
        }
    
    except Exception as e:
        logger.error(f"Error computing stats: {e}")
        return {
            "total": 0,
            "wins": 0,
            "losses": 0,
            "profit": 0.0,
            "roi": 0.0,
            "win_rate": 0.0,
            "avg_profit": 0.0,
            "total_stake": 0.0
        }


def get_stats_by_sport(filename: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Calculate statistics broken down by sport.
    
    Args:
        filename: Optional custom bet history file
        
    Returns:
        Dictionary mapping sport to stats dictionary
    """
    sports_data = {}
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return {}
    
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for bet in reader:
                sport = bet.get("sport", "unknown")
                if sport not in sports_data:
                    sports_data[sport] = {
                        "total": 0,
                        "wins": 0,
                        "losses": 0,
                        "profit": Decimal("0")
                    }
                
                sports_data[sport]["total"] += 1
                
                result = bet.get("result", "")
                if result == "win":
                    sports_data[sport]["wins"] += 1
                elif result == "loss":
                    sports_data[sport]["losses"] += 1
                
                profit = bet.get("profit", "")
                try:
                    sports_data[sport]["profit"] += Decimal(profit)
                except (InvalidOperation, TypeError, ValueError):
                    pass
        
        # Convert Decimal to float and calculate win rates
        for sport in sports_data:
            total = sports_data[sport]["total"]
            wins = sports_data[sport]["wins"]
            sports_data[sport]["profit"] = float(round(sports_data[sport]["profit"], 2))
            sports_data[sport]["win_rate"] = (wins / total * 100) if total > 0 else 0.0
        
        return sports_data
    
    except Exception as e:
        logger.error(f"Error computing stats by sport: {e}")
        return {}


def get_stats_by_market(filename: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Calculate statistics broken down by market type.
    
    Args:
        filename: Optional custom bet history file
        
    Returns:
        Dictionary mapping market to stats dictionary
    """
    markets_data = {}
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return {}
    
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for bet in reader:
                market = bet.get("market", "unknown")
                if market not in markets_data:
                    markets_data[market] = {
                        "total": 0,
                        "wins": 0,
                        "losses": 0,
                        "profit": Decimal("0")
                    }
                
                markets_data[market]["total"] += 1
                
                result = bet.get("result", "")
                if result == "win":
                    markets_data[market]["wins"] += 1
                elif result == "loss":
                    markets_data[market]["losses"] += 1
                
                profit = bet.get("profit", "")
                try:
                    markets_data[market]["profit"] += Decimal(profit)
                except (InvalidOperation, TypeError, ValueError):
                    pass
        
        # Convert Decimal to float and calculate win rates
        for market in markets_data:
            total = markets_data[market]["total"]
            wins = markets_data[market]["wins"]
            markets_data[market]["profit"] = float(round(markets_data[market]["profit"], 2))
            markets_data[market]["win_rate"] = (wins / total * 100) if total > 0 else 0.0
        
        return markets_data
    
    except Exception as e:
        logger.error(f"Error computing stats by market: {e}")
        return {}


def get_recent_bets(limit: int = 10, filename: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get most recent bets from history.
    
    Args:
        limit: Number of recent bets to return
        filename: Optional custom bet history file
        
    Returns:
        List of bet dictionaries
    """
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return []
    
    try:
        with open(path, "r", newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            all_bets = list(reader)
            return all_bets[-limit:] if len(all_bets) > limit else all_bets
    except Exception as e:
        logger.error(f"Error reading recent bets: {e}")
        return []


def export_stats_json(filename: str = "profit_stats.json", bet_file: Optional[str] = None) -> bool:
    """
    Export comprehensive statistics to JSON file.
    
    Args:
        filename: Output JSON filename
        bet_file: Optional custom bet history file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure output directory exists
        output_path = os.path.join(DATA_DIR, filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        stats = {
            "overall": get_total_stats(bet_file),
            "by_sport": get_stats_by_sport(bet_file),
            "by_market": get_stats_by_market(bet_file),
            "recent_bets": get_recent_bets(5, bet_file),
            "generated_at": datetime.now().isoformat()
        }
        
        with open(output_path, "w") as f:
            json.dump(stats, f, indent=2)
        
        logger.info(f"Stats exported to {output_path}")
        return True
    
    except Exception as e:
        logger.error(f"Error exporting stats to JSON: {e}")
        return False


def clear_bet_history(filename: Optional[str] = None, backup: bool = True) -> bool:
    """
    Clear bet history file (with optional backup).
    
    Args:
        filename: Optional custom bet history file
        backup: If True, create backup before clearing
        
    Returns:
        True if successful, False otherwise
    """
    path = filename or BET_HISTORY_FILE
    
    if not os.path.exists(path):
        logger.warning(f"Bet history file not found: {path}")
        return True
    
    try:
        if backup:
            # Ensure backup directory exists
            os.makedirs(BACKUP_DIR, exist_ok=True)
            
            # Create backup with timestamp
            backup_filename = f"{os.path.basename(path)}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = os.path.join(BACKUP_DIR, backup_filename)
            
            # Copy file to backup
            import shutil
            shutil.copy2(path, backup_path)
            logger.info(f"Backup created: {backup_path}")
            
            # Remove original
            os.remove(path)
            logger.info(f"Bet history cleared: {path}")
        else:
            os.remove(path)
            logger.info(f"Bet history cleared: {path}")
        
        return True
    
    except Exception as e:
        logger.error(f"Error clearing bet history: {e}")
        return False


if __name__ == "__main__":
    # CLI use-case: print comprehensive stats
    print("\n" + "="*60)
    print("PROFIT TRACKER SUMMARY")
    print("="*60)
    
    file = sys.argv[1] if len(sys.argv) > 1 else BET_HISTORY_FILE
    
    if not os.path.exists(file):
        print(f"\n❌ File not found: {file}")
        sys.exit(1)
    
    # Overall stats
    stats = get_total_stats(file)
    print(f"\n📊 Overall Statistics:")
    print(f"   Total Bets: {stats['total']}")
    print(f"   Wins: {stats['wins']} | Losses: {stats['losses']}")
    print(f"   Win Rate: {stats['win_rate']:.2f}%")
    print(f"   Net Profit: ${stats['profit']:.2f}")
    print(f"   ROI: {stats['roi']:.2f}%")
    print(f"   Avg Profit/Bet: ${stats['avg_profit']:.2f}")
    print(f"   Total Stake: ${stats['total_stake']:.2f}")
    
    # By sport
    by_sport = get_stats_by_sport(file)
    if by_sport:
        print(f"\n🏀 By Sport:")
        for sport, sport_stats in sorted(by_sport.items(), key=lambda x: x[1]['profit'], reverse=True):
            print(f"   {sport}: ${sport_stats['profit']:.2f} profit, {sport_stats['win_rate']:.1f}% win rate ({sport_stats['total']} bets)")
    
    # By market
    by_market = get_stats_by_market(file)
    if by_market:
        print(f"\n📈 By Market:")
        for market, market_stats in sorted(by_market.items(), key=lambda x: x[1]['profit'], reverse=True):
            print(f"   {market}: ${market_stats['profit']:.2f} profit, {market_stats['win_rate']:.1f}% win rate ({market_stats['total']} bets)")
    
    # Recent bets
    recent = get_recent_bets(5, file)
    if recent:
        print(f"\n📅 Recent Bets (last 5):")
        for bet in recent:
            print(f"   {bet.get('timestamp', 'N/A')} | {bet.get('match', 'N/A')} | ${bet.get('profit', 'N/A')} profit")
    
    print("\n" + "="*60 + "\n")
    
    # Optional: export to JSON
    if len(sys.argv) > 2 and sys.argv[2] == "--export":
        export_stats_json(bet_file=file)
        print("✅ Stats exported to data/profit_stats.json\n")
