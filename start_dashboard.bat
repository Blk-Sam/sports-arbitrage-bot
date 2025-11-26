@echo off
cd /d "C:\Users\Admin\Documents\GitHub\sports-arbitrage-bot"
set PYTHONPATH=%CD%

echo.
echo ============================================================
echo   SPORTS ARBITRAGE BOT - DASHBOARD
echo ============================================================
echo.
echo Starting dashboard server...
echo.
echo Press Ctrl+C to stop the dashboard
echo.

streamlit run src\dashboard\dashboard.py

pause
