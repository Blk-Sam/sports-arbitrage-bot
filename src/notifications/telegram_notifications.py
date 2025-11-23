"""
Telegram Notifications Module - User-Friendly Messaging

Provides clear, actionable, and easy-to-understand Telegram notifications
for arbitrage opportunities, errors, reports, and system status.

Usage:
    from telegram_notifications import send_arbitrage_alert, send_bet_placed_alert
    send_arbitrage_alert(arb, stakes, odds, profit)
    send_bet_placed_alert(bet_details, bet_number, total_bets)
"""

import os
import logging
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def decimal_to_american(decimal_odds: float) -> str:
    """Convert decimal odds to American format."""
    if decimal_odds >= 2.0:
        american = (decimal_odds - 1) * 100
        return f"+{int(american)}"
    else:
        american = -100 / (decimal_odds - 1)
        return f"{int(american)}"


def format_readable_time(iso_time: str) -> str:
    """Convert ISO time to human-readable format."""
    try:
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        now = datetime.now(dt.tzinfo)
        diff = dt - now
        
        hours = int(diff.total_seconds() / 3600)
        
        if hours < 0:
            return "LIVE NOW"
        elif hours < 1:
            mins = int(diff.total_seconds() / 60)
            return f"Starts in {mins} minutes"
        elif hours < 24:
            return f"Tonight {dt.strftime('%I:%M %p')} ({hours}h)"
        elif hours < 48:
            return f"Tomorrow {dt.strftime('%I:%M %p')}"
        else:
            return dt.strftime('%b %d, %I:%M %p')
    except:
        return iso_time


def send_telegram_message(message: str, bot_token: str = None, chat_id: str = None, retries: int = 2) -> bool:
    """
    Send text message to Telegram.
    
    Args:
        message: Message text (supports Markdown)
        bot_token: Bot token (uses env var if not provided)
        chat_id: Chat ID (uses env var if not provided)
        retries: Number of retry attempts
        
    Returns:
        True if sent successfully, False otherwise
    """
    token = bot_token or TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID
    
    if not token or not chat:
        logger.warning("âš ï¸ Telegram credentials not configured")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    for attempt in range(retries):
        try:
            data = {
                "chat_id": chat,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                logger.info("âœ… Telegram message sent successfully")
                return True
            else:
                logger.error(f"âŒ Telegram API error: {response.text}")
                
        except Exception as e:
            logger.error(f"âŒ Telegram send error (attempt {attempt+1}): {e}")
            
            if attempt == retries - 1:
                logger.warning("âš ï¸ Failed to send Telegram message after retries")
    
    return False


def send_telegram_file(file_path: str, caption: str = "", bot_token: str = None, 
                       chat_id: str = None, retries: int = 2) -> bool:
    """
    Send file to Telegram.
    
    Args:
        file_path: Path to file
        caption: File caption
        bot_token: Bot token (uses env var if not provided)
        chat_id: Chat ID (uses env var if not provided)
        retries: Number of retry attempts
        
    Returns:
        True if sent successfully, False otherwise
    """
    token = bot_token or TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID
    
    if not token or not chat:
        return False
    
    if not os.path.isfile(file_path):
        logger.error(f"âŒ File not found: {file_path}")
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    
    for attempt in range(retries):
        try:
            with open(file_path, "rb") as file:
                files = {"document": file}
                data = {"chat_id": chat, "caption": caption}
                
                response = requests.post(url, files=files, data=data, timeout=30)
                
                if response.status_code == 200:
                    logger.info(f"✅ File sent: {os.path.basename(file_path)}")
                    return True
                else:
                    logger.error(f"❌ Telegram API error: {response.text}")
                    
        except Exception as e:
            logger.error(f"❌ File send error (attempt {attempt+1}): {e}")
    
    return False


# === ARBITRAGE ALERTS ===

def send_arbitrage_alert(arb: Dict[str, Any], stakes: List[float], 
                        odds: List[float], profit: float) -> bool:
    """
    Send comprehensive, dummy-proof arbitrage opportunity notification.
    
    Args:
        arb: Arbitrage opportunity details
        stakes: Stake amounts for each bet
        odds: Odds for each outcome
        profit: Expected profit
        
    Returns:
        True if sent successfully
    """
    try:
        outcomes = list(arb.get('outcomes', {}).keys())
        bookmakers_dict = arb.get('bookmakers', {})
        market = arb.get('market', 'Unknown')
        sport = arb.get('sport', 'Unknown').replace('_', ' ').title()
        home_team = arb.get('home_team', 'Team A')
        away_team = arb.get('away_team', 'Team B')
        commence_time = arb.get('commence_time', '')
        
        # Determine profit emoji
        if profit >= 10:
            profit_emoji = "💰💰"
        elif profit >= 5:
            profit_emoji = "💰"
        else:
            profit_emoji = "💵"
        
        # Format time
        readable_time = format_readable_time(commence_time)
        
        # Calculate totals
        total_stake = sum(stakes)
        returns = [stake * odd for stake, odd in zip(stakes, odds)]
        
        # Build message
        message = f"""
{profit_emoji} *ARBITRAGE OPPORTUNITY - ACT NOW!*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🏀 {sport.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏟️ <b>GAME:</b>
{home_team} vs {away_team}
⏰ <b>Starts:</b> {readable_time}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>GUARANTEED PROFIT: ${profit:.2f}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>STEP-BY-STEP INSTRUCTIONS:</b>

"""
        
        # Add each bet with detailed instructions
        for i, (outcome, stake, odd) in enumerate(zip(outcomes, stakes, odds), 1):
            bookmaker = bookmakers_dict.get(outcome, 'Unknown').upper()
            american_odds = decimal_to_american(odd)
            potential_return = stake * odd
            
            message += f"""
🎯 <b>BET #{i} - {outcome}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━
📍 <b>Where:</b> {bookmaker}
💵 <b>Bet Amount:</b> ${stake:.2f}
📊 <b>Odds:</b> {odd:.2f} ({american_odds})
💰 <b>Potential Return:</b> ${potential_return:.2f}

🔹 <b>HOW TO PLACE:</b>
1. Open {bookmaker} app/website
2. Find: {home_team} vs {away_team}
3. Select: {outcome}
4. Enter stake: ${stake:.2f}
5. Confirm bet

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        # Add profit explanation
        message += f"""
💡 <b>WHY THIS WORKS:</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Total Invested:</b> ${total_stake:.2f}

"""
        
        # Show profit for each outcome
        for i, (outcome, stake, return_amt) in enumerate(zip(outcomes, stakes, returns)):
            other_stakes_total = sum(s for j, s in enumerate(stakes) if j != i)
            net_profit = return_amt - total_stake
            
            message += f"""
<b>IF {outcome.upper()} WINS:</b>
{bookmakers_dict.get(outcome, 'Unknown').upper()} pays: ${return_amt:.2f}
Other bets lose: -${other_stakes_total:.2f}
<b>Net Profit: ${net_profit:.2f}</b> ✅

"""
        
        message += f"""
🎉 <b>YOU WIN EITHER WAY!</b> 🎉

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ <b>URGENT - PLACE BETS NOW!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏱️ These odds can change in SECONDS
✅ Both bookmakers are reliable
💰 {(profit/total_stake*100):.2f}% return guaranteed
🔒 Risk-free profit

⚠️ <b>Tips:</b>
• Place both bets within 1-2 minutes
• Double-check odds before confirming
• Screenshot both bet slips
• Have accounts pre-funded

🚀 <b>GO GO GO!</b>

"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error formatting arbitrage notification: {e}", exc_info=True)
        # Send simplified fallback message
        fallback = f"""
💰 <b>ARBITRAGE ALERT!</b>

Match: {arb.get('home_team', 'N/A')} vs {arb.get('away_team', 'N/A')}
Profit: ${profit:.2f}

Check bot for details!
"""
        return send_telegram_message(fallback)


# === BET PLACEMENT NOTIFICATIONS ===

def send_bet_placed_alert(
    bet_details: Dict[str, Any],
    bet_number: int,
    total_bets: int,
    arb_id: Optional[str] = None,
    is_simulation: bool = True
) -> bool:
    """
    Send detailed notification when individual bet is placed (Option B).
    
    Args:
        bet_details: Dictionary containing bet information
        bet_number: Current bet number (1, 2, etc.)
        total_bets: Total number of bets in this arbitrage
        arb_id: Arbitrage opportunity ID
        is_simulation: Whether this is a demo/simulation bet
        
    Returns:
        True if sent successfully
    """
    try:
        mode_indicator = "🔴 DEMO MODE" if is_simulation else "🟢 LIVE"
        
        bookmaker = bet_details.get('bookmaker', 'Unknown').upper()
        selection = bet_details.get('selection', 'Unknown')
        stake = bet_details.get('stake', 0)
        odds = bet_details.get('odds', 0)
        sport = bet_details.get('sport', 'Unknown').replace('_', ' ').title()
        home_team = bet_details.get('home_team', 'Team A')
        away_team = bet_details.get('away_team', 'Team B')
        game_time = bet_details.get('game_time', '')
        
        american_odds = decimal_to_american(odds)
        potential_return = stake * odds
        potential_profit = potential_return - stake
        readable_time = format_readable_time(game_time) if game_time else "TBD"
        timestamp = datetime.now().strftime('%B %d, %I:%M:%S %p')
        
        # Calculate what's next
        remaining_bets = total_bets - bet_number
        next_bet_info = bet_details.get('next_bet', {})
        
        message = f"""
✅ <b>BET SUCCESSFULLY PLACED</b>
{mode_indicator}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 <b>BET DETAILS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏀 <b>Sport:</b> {sport}
🏟️ <b>Match:</b> {home_team} vs {away_team}
⏰ <b>Game Time:</b> {readable_time}

📍 <b>Bookmaker:</b> {bookmaker}
🎯 <b>Selection:</b> {selection}
💵 <b>Stake:</b> ${stake:.2f}
📊 <b>Odds:</b> {odds:.2f} (American: {american_odds})
💰 <b>Potential Return:</b> ${potential_return:.2f}
💸 <b>Potential Profit:</b> ${potential_profit:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>ARBITRAGE PROGRESS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Bet {bet_number} of {total_bets} placed
"""
        
        if remaining_bets > 0 and next_bet_info:
            next_bookmaker = next_bet_info.get('bookmaker', 'Unknown').upper()
            next_selection = next_bet_info.get('selection', 'Unknown')
            next_stake = next_bet_info.get('stake', 0)
            
            message += f"""
⏳ <b>Next:</b> Bet ${next_stake:.2f} on {next_selection} @ {next_bookmaker}
"""
        else:
            guaranteed_profit = bet_details.get('guaranteed_profit', 0)
            message += f"""
🎉 <b>All bets for this arbitrage placed!</b>
🔒 <b>Guaranteed Profit:</b> ${guaranteed_profit:.2f}
"""
        
        message += f"""

⏱️ <b>Time:</b> {timestamp}
"""
        
        if arb_id:
            message += f"🆔 <b>Arb ID:</b> {arb_id}\n"
        
        if is_simulation:
            message += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <b>SIMULATION MODE</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is a TEST bet - no real money used.
Bet logged for demo analysis.

💡 To enable live betting:
Set SIMULATE_BET_PLACEMENT=0 in .env
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending bet placed alert: {e}", exc_info=True)
        return False


def send_arbitrage_complete_alert(
    arb_summary: Dict[str, Any],
    is_simulation: bool = True
) -> bool:
    """
    Send completion notification when all bets in arbitrage are placed (Option C).
    
    Args:
        arb_summary: Dictionary containing complete arbitrage summary
        is_simulation: Whether this is a demo/simulation
        
    Returns:
        True if sent successfully
    """
    try:
        mode_indicator = "🔴 DEMO" if is_simulation else "🟢 LIVE"
        
        home_team = arb_summary.get('home_team', 'Team A')
        away_team = arb_summary.get('away_team', 'Team B')
        sport = arb_summary.get('sport', 'Unknown').replace('_', ' ').title()
        game_time = arb_summary.get('game_time', '')
        bets = arb_summary.get('bets', [])
        total_stake = arb_summary.get('total_stake', 0)
        guaranteed_return = arb_summary.get('guaranteed_return', 0)
        guaranteed_profit = arb_summary.get('guaranteed_profit', 0)
        roi = arb_summary.get('roi', 0)
        
        readable_time = format_readable_time(game_time) if game_time else "TBD"
        
        message = f"""
🎉 <b>ARBITRAGE COMPLETE!</b> {mode_indicator}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ <b>ALL BETS SUCCESSFULLY PLACED</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏀 <b>{sport}</b>
🏟️ {home_team} vs {away_team}
⏰ {readable_time}

"""
        
        # List all bets
        for i, bet in enumerate(bets, 1):
            bookmaker = bet.get('bookmaker', 'Unknown').upper()
            selection = bet.get('selection', 'Unknown')
            stake = bet.get('stake', 0)
            odds = bet.get('odds', 0)
            
            message += f"""
<b>BET {i}:</b> ✅ CONFIRMED
📍 {bookmaker}
🎯 {selection}
💵 Stake: ${stake:.2f} @ {odds:.2f}

"""
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>GUARANTEED RESULTS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Total Invested:</b> ${total_stake:.2f}
💵 <b>Guaranteed Return:</b> ${guaranteed_return:.2f}
✨ <b>Guaranteed Profit:</b> ${guaranteed_profit:.2f}
📈 <b>ROI:</b> {roi:.2f}%

🎉 <b>YOU CAN'T LOSE!</b>

Regardless of which team wins, you profit ${guaranteed_profit:.2f}

⏰ <b>Game Time:</b> {readable_time}
📱 Track both bets in your bookmaker apps
"""
        
        if is_simulation:
            message += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 <b>DEMO MODE</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This was a simulated arbitrage.
All bets logged for analysis.

📊 Check dashboard for performance
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending arbitrage complete alert: {e}", exc_info=True)
        return False


def send_bet_failed_alert(
    bet_details: Dict[str, Any],
    reason: str,
    bet_number: int,
    total_bets: int
) -> bool:
    """
    Send notification when bet placement fails.
    
    Args:
        bet_details: Dictionary containing bet information
        reason: Failure reason
        bet_number: Current bet number
        total_bets: Total number of bets in this arbitrage
        
    Returns:
        True if sent successfully
    """
    try:
        bookmaker = bet_details.get('bookmaker', 'Unknown').upper()
        selection = bet_details.get('selection', 'Unknown')
        stake = bet_details.get('stake', 0)
        home_team = bet_details.get('home_team', 'Team A')
        away_team = bet_details.get('away_team', 'Team B')
        
        completed_bets = bet_number - 1
        
        message = f"""
❌ <b>BET PLACEMENT FAILED</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <b>ISSUE WITH BET</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏟️ <b>Match:</b> {home_team} vs {away_team}
📍 <b>Bookmaker:</b> {bookmaker}
🎯 <b>Selection:</b> {selection}
💵 <b>Attempted Stake:</b> ${stake:.2f}

📝 <b>Reason:</b> {reason}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ <b>ACTION REQUIRED</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 <b>ARBITRAGE INCOMPLETE</b>
Only {completed_bets} of {total_bets} bets placed
"""
        
        if completed_bets > 0:
            message += """

⚠️ <b>You may have EXPOSURE RISK if you place the other bet</b>
"""
        
        message += f"""

💡 <b>Next Steps:</b>
1. Resolve issue with {bookmaker}
2. Retry this arbitrage opportunity
3. OR skip this opportunity

⏰ <b>Odds may change - act quickly!</b>
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending bet failed alert: {e}", exc_info=True)
        return False


# === ERROR ALERTS ===

def send_error_alert(error_type: str, error_msg: str, severity: str = "warning") -> bool:
    """
    Send user-friendly error notification.
    
    Args:
        error_type: Type of error (API, Network, etc)
        error_msg: Error message
        severity: warning, error, critical
    """
    emoji_map = {
        'warning': '⚠️',
        'error': '❌',
        'critical': '🚨'
    }
    
    emoji = emoji_map.get(severity, '⚠️')
    
    message = f"""
{emoji} *{severity.upper()}: {error_type}*

📝 <b>Issue:</b> {error_msg}

"""
    
    if severity == "critical":
        message += """
🚨 <b>IMMEDIATE ACTION REQUIRED</b>
Please check bot immediately!
Bot may have stopped functioning
"""
    elif severity == "error":
        message += """
⚠️ <b>Bot may need attention</b>
Check logs for details.
Monitoring may be affected.
"""
    else:
        message += """
ℹ️ <b>Minor issue - bot continuing</b>
No action required.
This is informational only.
"""
    
    return send_telegram_message(message)


# === SYSTEM STATUS ===

def send_startup_notification(version: str, config: Dict[str, Any]) -> bool:
    """Notify that bot has started."""
    message = f"""

🤑 <b>ARBITRAGE BOT STARTED</b><br>
📊 <b>Version:</b> {version}<br>
⚙️ <b>Mode:</b> {'🧪 SIMULATION' if config.get('simulate', True) else '🎯 LIVE TRADING'}<br>
💰 <b>Bankroll:</b> ${config.get('bankroll', 0):.2f}<br>
📈 <b>Min Margin:</b> {config.get('min_margin', 0)*100:.2f}%<br><br>
⚡ <b>Sports Monitored:</b><br>
{', '.join(config.get('sports', []))}<br>
📊 <b>Markets:</b><br>
{', '.join(config.get('markets', []))}<br><br>
✅ <b>Bot is now monitoring for opportunities!</b><br>
📲 You'll receive alerts when arbitrage is detected.
"""
    
    return send_telegram_message(message)


def send_shutdown_notification(reason: str = "Normal shutdown", stats: Dict[str, Any] = None) -> bool:
    """Notify that bot has stopped."""
    message = f"""
🛑 <b>ARBITRAGE BOT STOPPED</b>

Reason: {reason}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

"""
    
    if stats:
        message += f"""
📊 <b>Session Summary:</b>
• Opportunities Found: {stats.get('opportunities', 0)}
• Total Profit: ${stats.get('total_profit', 0):.2f}
• Runtime: {stats.get('uptime', 'N/A')}
"""
    
    message += """
ℹ️ <b>Bot has stopped monitoring.</b>
Restart required to resume operations.
"""
    
    return send_telegram_message(message)


# === PERFORMANCE REPORTS ===

def send_daily_report(metrics: Dict[str, Any]) -> bool:
    """Send clear daily performance summary."""
    profit = metrics.get('total_profit', 0)
    profit_emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
    
    message = f"""
📊 <b>DAILY PERFORMANCE REPORT</b>
{datetime.now().strftime('%B %d, %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>PROFIT/LOSS:</b> {profit_emoji} ${profit:.2f}

📈 <b>TRADING STATS:</b>
• Total Bets: {metrics.get('total_bets', 0)}
• Wins: {metrics.get('wins', 0)} ✅
• Losses: {metrics.get('losses', 0)} ❌
• Win Rate: {metrics.get('win_rate', 0)*100:.1f}%

📊 <b>PERFORMANCE:</b>
• Avg Profit/Bet: ${metrics.get('avg_profit', 0):.2f}
• Best Bet: ${metrics.get('best_bet', 0):.2f}
• Worst Bet: ${metrics.get('worst_bet', 0):.2f}

💼 <b>BANKROLL:</b>
• Starting: ${metrics.get('start_bankroll', 0):.2f}
• Current: ${metrics.get('current_bankroll', 0):.2f}
• ROI: {metrics.get('roi', 0):.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if profit > 0:
        message += "🎉 <b>Excellent trading day!</b>"
    elif profit < 0:
        message += "📉 <b>Review and adjust strategy</b>"
    else:
        message += "⚖️ <b>Break-even day</b>"
    
    return send_telegram_message(message)
def send_daily_report(metrics: Dict[str, Any]) -> bool:
    """Send clear daily performance summary."""
    profit = metrics.get('total_profit', 0)
    profit_emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
    
    message = f"""
📊 <b>DAILY PERFORMANCE REPORT</b>
{datetime.now().strftime('%B %d, %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>PROFIT/LOSS:</b> {profit_emoji} ${profit:.2f}

📈 <b>TRADING STATS:</b>
• Total Bets: {metrics.get('total_bets', 0)}
• Wins: {metrics.get('wins', 0)} ✅
• Losses: {metrics.get('losses', 0)} ❌
• Win Rate: {metrics.get('win_rate', 0)*100:.1f}%

📊 <b>PERFORMANCE:</b>
• Avg Profit/Bet: ${metrics.get('avg_profit', 0):.2f}
• Best Bet: ${metrics.get('best_bet', 0):.2f}
• Worst Bet: ${metrics.get('worst_bet', 0):.2f}

💼 <b>BANKROLL:</b>
• Starting: ${metrics.get('start_bankroll', 0):.2f}
• Current: ${metrics.get('current_bankroll', 0):.2f}
• ROI: {metrics.get('roi', 0):.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if profit > 0:
        message += "🎉 <b>Excellent trading day!</b>"
    elif profit < 0:
        message += "📉 <b>Review and adjust strategy</b>"
    else:
        message += "⚖️ <b>Break-even day</b>"
    
    return send_telegram_message(message)

# === BACKUP NOTIFICATIONS ===

def send_backup_notification(
    backup_path: str,
    backup_type: str,
    backup_size_mb: float,
    checksum: str = None,
    is_success: bool = True
) -> bool:
    """
    Send backup creation notification to Telegram.
    
    Args:
        backup_path: Path to backup file
        backup_type: Type of backup (startup, shutdown, daily, manual)
        backup_size_mb: Size of backup in MB
        checksum: SHA256 checksum
        is_success: Whether backup was successful
        
    Returns:
        True if sent successfully
    """
    try:
        if is_success:
            emoji = "✅"
            status = "SUCCESSFUL"
        else:
            emoji = "❌"
            status = "FAILED"
        
        message = f"""
{emoji} *BACKUP {status}*

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 <b>Backup Type:</b> {backup_type.upper()}
📁 <b>File:</b> <code>{os.path.basename(backup_path)}</code>
💾 <b>Size:</b> {backup_size_mb:.2f} MB
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if checksum and len(checksum) > 0:
            message += f"🔐 <b>Checksum:</b> <code>{checksum[:16]}...</code>\n"
        
        message += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if is_success:
            message += """
✅ Backup stored and ready for recovery
📊 Use dashboard for restore options
"""
        else:
            message += """
⚠️ Please check logs for error details
🔧 Retry manually or contact support
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending backup notification: {e}", exc_info=True)
        return False


def send_backup_cleanup_notification(
    stats: dict
) -> bool:
    """
    Send backup cleanup notification to Telegram.
    
    Args:
        stats: Cleanup statistics dictionary
        
    Returns:
        True if sent successfully
    """
    try:
        message = f"""
🧹 <b>BACKUP CLEANUP COMPLETE</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>Cleanup Statistics:</b>

Backups before: {stats.get('total_before', 0)}
Backups deleted: {stats.get('deleted', 0)}
Backups kept: {stats.get('total_before', 0) - stats.get('deleted', 0)}

✅ Recent (7d): {stats.get('kept_recent', 0)}
📊 Medium (30d): {stats.get('kept_medium', 0)}
📈 Archive (90d): {stats.get('kept_archive', 0)}

💾 Space freed: {stats.get('freed_mb', 0):.2f} MB
⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Storage optimized and ready
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending cleanup notification: {e}", exc_info=True)
        return False


def send_backup_restore_notification(
    backup_path: str,
    is_success: bool = True,
    error_msg: str = None
) -> bool:
    """
    Send backup restore notification to Telegram.
    
    Args:
        backup_path: Path to restored backup
        is_success: Whether restore was successful
        error_msg: Error message if failed
        
    Returns:
        True if sent successfully
    """
    try:
        if is_success:
            message = f"""
✅ <b>BACKUP RESTORE SUCCESSFUL</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 <b>Backup:</b> {os.path.basename(backup_path)}
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ All files restored successfully
🔄 Please restart bot to apply changes
"""
        else:
            message = f"""
❌ <b>BACKUP RESTORE FAILED</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 <b>Backup:</b> {os.path.basename(backup_path)}
📝 <b>Error:</b> {error_msg or 'Unknown error'}
⏰ <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ Restore failed - check logs for details
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending restore notification: {e}", exc_info=True)
        return False


def send_backup_status_report(
    stats: dict
) -> bool:
    """
    Send backup status report to Telegram.
    
    Args:
        stats: Backup statistics dictionary
        
    Returns:
        True if sent successfully
    """
    try:
        total_backups = stats.get('total_backups', 0)
        total_size_gb = stats.get('total_size_gb', 0)
        by_type = stats.get('by_type', {})
        
        message = f"""
📊 <b>BACKUP STATUS REPORT</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 <b>Overview:</b>
• Total Backups: {total_backups}
• Total Storage: {total_size_gb} GB
• Oldest: {stats.get('oldest_backup', 'N/A')}
• Newest: {stats.get('newest_backup', 'N/A')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📂 <b>By Type:</b>
"""
        
        for backup_type, data in by_type.items():
            message += f"â€¢ {backup_type.title()}: {data['count']} backups ({data['size_mb']:.1f} MB)\n"
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ Report Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

✅ Backup system is healthy and operational
"""
        
        return send_telegram_message(message)
        
    except Exception as e:
        logger.error(f"Error sending status report: {e}", exc_info=True)
        return False