import sqlite3
import json
import time
import random

DB_PATH = "manu_bot.db"

def seed_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Seeding database...")

    # 1. Seed State (Open Positions) - Mock
    positions = [
        {
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "leverage": 10,
            "entryPrice": 95000,
            "markPrice": 95100,
            "quantity": 0.05,
            "unrealisedPnl": 50,
            "unrealisedPnlPcnt": 0.01,
            "marginMode": "ISOLATED"
        }
    ]
    cursor.execute('''
        INSERT INTO state (component, timestamp, data) VALUES (?, ?, ?)
        ON CONFLICT(component) DO UPDATE SET timestamp=excluded.timestamp, data=excluded.data
    ''', ("open_positions", time.time(), json.dumps(positions)))

    # 2. Seed History Ledger (PnL)
    # Generate a random equity curve over the last 30 days
    now = time.time()
    balance = 1000.0

    # Clear existing data to avoid duplicates/confusion during dev
    cursor.execute("DELETE FROM history_ledger")
    cursor.execute("DELETE FROM history_fills")

    for day in range(30, 0, -1):
        # 1-3 trades per day
        num_trades = random.randint(1, 3)
        for _ in range(num_trades):
            ts = now - (day * 86400) + random.randint(0, 8000)
            pnl = random.uniform(-20, 35) # Slightly positive expectancy
            balance += pnl

            cursor.execute('''
                INSERT INTO history_ledger
                (timestamp, amount, type, currency, remark)
                VALUES (?, ?, ?, ?, ?)
            ''', (ts, pnl, "RealisedPNL", "USDT", "Trade PnL"))

            # Also add a corresponding Fill (execution)
            trade_id = f"t_{int(ts)}"
            symbol = random.choice(["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])
            side = random.choice(["buy", "sell"])
            price = random.uniform(2000, 90000) if "ETH" in symbol or "BTC" in symbol else random.uniform(100, 200)
            size = random.uniform(0.1, 2.0)
            value = price * size

            cursor.execute('''
                INSERT INTO history_fills
                (trade_id, symbol, side, price, size, value, fee, fee_currency, timestamp, order_id, trade_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id, symbol, side, price, size, value,
                value * 0.0006, "USDT", ts * 1000, f"ord_{int(ts)}", "trade"
            ))

    conn.commit()
    conn.close()
    print(f"Database seeded with ~{30*2} trades and ledger entries.")

if __name__ == "__main__":
    seed_db()
