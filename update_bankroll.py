import sys
import os

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    import pandas as pd
    from pathlib import Path
    from dotenv import set_key
    
    # Check if bet history exists
    bet_history_file = "data/bet_history.csv"
    env_file = "src/config/.env"
    
    if not os.path.exists(bet_history_file):
        print("ℹ️  No bet history found - keeping current START_BANKROLL")
        sys.exit(0)
    
    # Read bet history
    df = pd.read_csv(bet_history_file)
    
    if len(df) == 0:
        print("ℹ️  No bets in history - keeping current START_BANKROLL")
        sys.exit(0)
    
    # Calculate total profit
    total_profit = df['sim_actual_profit'].sum()
    new_bankroll = 100 + total_profit
    
    # Update .env file
    set_key(env_file, "START_BANKROLL", str(new_bankroll))
    
    print(f"✅ Updated bankroll: ${new_bankroll:.2f}")
    print(f"   Total profit: ${total_profit:.2f}")
    print(f"   Bets counted: {len(df)}")
    
except Exception as e:
    print(f"❌ Error updating bankroll: {e}")
    sys.exit(1)
