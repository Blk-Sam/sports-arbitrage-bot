"""
Reporting Module - Analytics & Report Generation

Generates comprehensive reports including:
- Daily/weekly/monthly P&L reports
- Market performance breakdowns
- Sport-specific analytics
- ROI and profitability metrics
- HTML report generation
"""

from src.reporting.reporting import (
    run_report,
    calculate_sharpe_ratio,
    calculate_advanced_metrics
)

__all__ = [
    'run_report',
    'calculate_sharpe_ratio',
    'calculate_advanced_metrics',
]
