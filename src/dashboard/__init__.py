"""
Dashboard Module - Streamlit Web Interface

Provides real-time monitoring and analytics dashboard for:
- Live performance metrics
- Manual P&L entry and reconciliation
- Historical bet tracking
- Profit/loss visualization
- ROI and win rate analytics
"""

from src.dashboard.backup_panel import render_backup_panel

__all__ = [
    'dashboard',
    'render_backup_panel',
]
