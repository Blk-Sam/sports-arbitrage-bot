from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("ODDS_API_KEY")
print("Loaded API key:", api_key)

import schedule
import time
import subprocess

def run_bot():
    print(f"Running bot at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        subprocess.run(['python', 'main.py'])
    except Exception as e:
        print(f"Failed to run main.py: {e}")

times_to_run = ["08:00", "12:00", "15:00", "18:00", "21:00"]
for t in times_to_run:
    schedule.every().day.at(t).do(run_bot)

print("Automated bot scheduling started. Runs at:", ', '.join(times_to_run))
while True:
    schedule.run_pending()
    time.sleep(60)
