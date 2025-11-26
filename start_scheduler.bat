@echo off
cd /d "C:\Users\Admin\Documents\GitHub\sports-arbitrage-bot"
set PYTHONPATH=%CD%

echo.
echo ============================================================
echo   SPORTS ARBITRAGE BOT - STARTUP
echo ============================================================
echo.

echo [1/2] Updating bankroll from last session...
python update_bankroll.py
echo.

echo [2/2] Starting scheduler...
echo.
python src\scheduling\scheduler.py

pause
