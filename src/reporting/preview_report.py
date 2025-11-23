import sys
import os
import logging
import argparse
from typing import Optional
from datetime import datetime
from src.reporting.reporting import run_report


# Import new Telegram notifications module
from src.notifications.telegram_notifications import send_error_alert


# Default directories
DATA_DIR = os.getenv("DASHBOARD_DATA_DIR", "data")
LOG_DIR = "logs"
STATIC_DIR = os.getenv("STATIC_DIR", "dashboard/static")


# Ensure required directories exist
os.makedirs(LOG_DIR, exist_ok=True)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'preview_report.log')),
        logging.StreamHandler()
    ]
)


logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Generate and preview arbitrage bot profit/loss reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python preview_report.py
  python preview_report.py data/bet_history.csv
  python preview_report.py --export-json
  python preview_report.py --telegram
  python preview_report.py --stats-only
        """
    )
    
    parser.add_argument(
        'csvfile',
        nargs='?',
        help=f'Path to bet history CSV file (default: {DATA_DIR}/bet_history.csv)'
    )
    parser.add_argument(
        '--export-json',
        action='store_true',
        help='Export statistics to JSON file'
    )
    parser.add_argument(
        '--telegram',
        action='store_true',
        help='Send report to Telegram'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Show only quick stats without generating full report'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    return parser.parse_args()


def validate_file(csvfile: str) -> bool:
    """
    Validate that CSV file exists and is readable.
    
    Args:
        csvfile: Path to CSV file
        
    Returns:
        True if valid, False otherwise
    """
    if not os.path.isfile(csvfile):
        logger.error(f"File not found: {csvfile}")
        print(f"\n❌ [Error] File not found: {csvfile}")
        print(f"Usage: python preview_report.py [optional_path_to_csv]")
        return False
    
    try:
        with open(csvfile, 'r') as f:
            # Check if file is readable and not empty
            first_line = f.readline()
            if not first_line:
                logger.error(f"File is empty: {csvfile}")
                print(f"\n❌ [Error] File is empty: {csvfile}")
                return False
    except PermissionError:
        logger.error(f"Permission denied reading file: {csvfile}")
        print(f"\n❌ [Error] Permission denied reading file: {csvfile}")
        return False
    except Exception as e:
        logger.error(f"Error reading file {csvfile}: {e}")
        print(f"\n❌ [Error] Could not read file: {e}")
        return False
    
    return True


def show_quick_stats(csvfile: str) -> None:
    """
    Display quick statistics without generating full report.
    
    Args:
        csvfile: Path to CSV file
    """
    print("\n" + "=" * 60)
    print("QUICK STATISTICS")
    print("=" * 60)
    
    try:
        from src.bot.profit_tracker import get_total_stats, get_stats_by_sport, get_stats_by_market
        
        # Overall stats
        stats = get_total_stats(csvfile)
        print(f"\n📊 Overall:")
        print(f"   Total Bets: {stats['total']}")
        print(f"   Wins: {stats['wins']} | Losses: {stats['losses']}")
        print(f"   Win Rate: {stats['win_rate']:.1f}%")
        print(f"   Total Profit: ${stats['profit']:.2f}")
        print(f"   ROI: {stats['roi']:.2f}%")
        print(f"   Avg Profit/Bet: ${stats['avg_profit']:.2f}")
        
        # By sport
        by_sport = get_stats_by_sport(csvfile)
        if by_sport:
            print(f"\n🏀 By Sport:")
            for sport, sport_stats in sorted(by_sport.items(), key=lambda x: x[1]['profit'], reverse=True)[:5]:
                print(f"   {sport}: ${sport_stats['profit']:.2f} ({sport_stats['win_rate']:.1f}% WR, {sport_stats['total']} bets)")
        
        # By market
        by_market = get_stats_by_market(csvfile)
        if by_market:
            print(f"\n📈 By Market:")
            for market, market_stats in sorted(by_market.items(), key=lambda x: x[1]['profit'], reverse=True):
                print(f"   {market}: ${market_stats['profit']:.2f} ({market_stats['win_rate']:.1f}% WR, {market_stats['total']} bets)")
        
        print("\n" + "=" * 60)
    
    except Exception as e:
        logger.error(f"Error generating quick stats: {e}", exc_info=True)
        print(f"\n❌ [Error] Could not generate stats: {e}")
        send_error_alert("Preview Report Stats", str(e), "error")


def preview_report(
    csvfile: Optional[str] = None,
    export_json: bool = False,
    send_telegram: bool = False,
    stats_only: bool = False
) -> None:
    """
    Generate and preview profit/loss report.
    
    Args:
        csvfile: Path to CSV file (optional)
        export_json: Export statistics to JSON
        send_telegram: Send report to Telegram
        stats_only: Only show quick stats
    """
    # Determine CSV file path
    if csvfile is None:
        csvfile = os.path.join(DATA_DIR, "bet_history.csv")
    
    # Display header
    print("\n" + "=" * 70)
    print("ARBITRAGE BOT - PROFIT/LOSS REPORT PREVIEW")
    print("=" * 70)
    print(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Using history file: {csvfile}")
    print("=" * 70)
    
    # Validate file
    if not validate_file(csvfile):
        return
    
    # Quick stats only
    if stats_only:
        show_quick_stats(csvfile)
        return
    
    # Generate full report
    print("\n🔄 Generating comprehensive report...")
    logger.info(f"Generating report from {csvfile}")
    
    try:
        # Get Telegram credentials if requested
        telegram_bot_token = None
        telegram_chat_id = None
        
        if send_telegram:
            telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
            
            if not telegram_bot_token or not telegram_chat_id:
                logger.warning("Telegram credentials not found in environment")
                print("\n⚠️  Warning: Telegram credentials not configured")
                print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
            else:
                print("📱 Telegram notification enabled")
        
        # Generate report
        run_report(
            bet_log_file=csvfile,
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id
        )
        
        print("\n✅ Report generated successfully!")
        logger.info("Report generated successfully")
        
        # Export JSON if requested
        if export_json:
            print("\n📄 Exporting statistics to JSON...")
            try:
                from src.bot.profit_tracker import export_stats_json
                export_stats_json(bet_file=csvfile)
                print(f"✅ Statistics exported to {DATA_DIR}/profit_stats.json")
                logger.info("Statistics exported to JSON")
            except Exception as e:
                logger.error(f"Error exporting JSON: {e}")
                print(f"❌ Error exporting JSON: {e}")
                send_error_alert("JSON Export", str(e), "warning")
        
        # Show output file locations
        print("\n📁 Output Files:")
        print(f"   Data files ({DATA_DIR}/):")
        print(f"      - daily_pnl.csv (daily profit/loss data)")
        print(f"      - pnl_summary.json (summary statistics)")
        print(f"      - breakdown_market.csv (market breakdown)")
        print(f"      - breakdown_sport.csv (sport breakdown)")
        print(f"      - market_edge_summary.csv (market edge analytics)")
        print(f"      - report.html (comprehensive HTML report)")
        if export_json:
            print(f"      - profit_stats.json (detailed statistics)")
        
        print(f"\n   Chart files ({STATIC_DIR}/):")
        print(f"      - daily_pnl_chart.png (daily PnL chart)")
        print(f"      - cumulative_profit.png (cumulative profit chart)")
        print(f"      - drawdown_chart.png (drawdown visualization)")
        print(f"      - win_rate_by_market.png (win rate breakdown)")
        print(f"      - profit_distribution.png (profit histogram)")
        
        print("\n💡 Tips:")
        print(f"   • Open {DATA_DIR}/report.html in your browser for interactive view")
        print("   • Use --stats-only for quick summary without charts")
        print("   • Use --telegram to send report to Telegram")
        print("   • Use --export-json for JSON export")
        print(f"   • Check {LOG_DIR}/preview_report.log for detailed logs")
    
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        print(f"\n❌ [Error] Required file not found: {e}")
        send_error_alert("Report Generation", f"File not found: {e}", "error")
    
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        print(f"\n❌ [Error] Missing required library: {e}")
        print("Install with: pip install pandas matplotlib numpy")
        send_error_alert("Missing Dependency", str(e), "error")
    
    except Exception as e:
        logger.error(f"Could not generate report: {e}", exc_info=True)
        print(f"\n❌ [Error] Could not generate report: {e}")
        print(f"Check {LOG_DIR}/preview_report.log for details")
        send_error_alert("Report Generation", str(e), "error")


def main():
    """Main entry point."""
    args = parse_arguments()
    
    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    try:
        preview_report(
            csvfile=args.csvfile,
            export_json=args.export_json,
            send_telegram=args.telegram,
            stats_only=args.stats_only
        )
    except KeyboardInterrupt:
        print("\n\n⚠️  Report generation cancelled by user")
        logger.info("Report generation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\n❌ Unexpected error: {e}")
        send_error_alert("Preview Report", f"Unexpected error: {e}", "critical")
        sys.exit(1)


if __name__ == "__main__":
    main()
