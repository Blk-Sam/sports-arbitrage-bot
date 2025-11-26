@echo off
cd /d "C:\Users\Admin\Documents\GitHub\sports-arbitrage-bot"
set PYTHONPATH=%CD%

echo.
echo ============================================================
echo   SPORTS ARBITRAGE BOT - DASHBOARD
echo ============================================================
echo.
echo Starting dashboard server...
echo Dashboard will open at: http://localhost:8050
echo.
echo Press Ctrl+C to stop the dashboard
echo.

python src/dashboard/app.py

pause
