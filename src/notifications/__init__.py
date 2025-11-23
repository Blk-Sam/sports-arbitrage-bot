"""
Notifications Module - Telegram Alert System

Handles all notification types:
- Arbitrage opportunity alerts
- Bet placement confirmations
- Error and warning notifications
- System status updates
- Daily summaries
- Backup notifications
"""

from src.notifications.telegram_notifications import (
    send_arbitrage_alert,
    send_bet_placed_alert,
    send_arbitrage_complete_alert,
    send_bet_failed_alert,
    send_error_alert,
    send_startup_notification,
    send_shutdown_notification,
    send_telegram_message,
    send_backup_notification,
    send_backup_cleanup_notification,
)

__all__ = [
    'send_arbitrage_alert',
    'send_bet_placed_alert',
    'send_arbitrage_complete_alert',
    'send_bet_failed_alert',
    'send_error_alert',
    'send_startup_notification',
    'send_shutdown_notification',
    'send_telegram_message',
    'send_backup_notification',
    'send_backup_cleanup_notification',
]
