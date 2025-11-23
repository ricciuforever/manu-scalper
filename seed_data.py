import sqlite3
import json
import time

DB_PATH = "manu_bot.db"

def seed_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Seed State (Open Positions)
    # Simulate 1 Long, 1 Short
    positions = [
        {
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "leverage": 10,
            "entryPrice": 50000,
            "markPrice": 51000,
            "quantity": 0.1,
            "unrealisedPnl": 100,
            "unrealisedPnlPcnt": 0.02,
            "marginMode": "ISOLATED"
        },
        {
            "symbol": "ETH/USDT:USDT",
            "side": "short",
            "leverage": 10,
            "entryPrice": 3000,
            "markPrice": 2900,
            "quantity": 1,
            "unrealisedPnl": 100,
            "unrealisedPnlPcnt": 0.033,
            "marginMode": "ISOLATED"
        }
    ]
    cursor.execute('''
        INSERT INTO state (component, timestamp, data) VALUES (?, ?, ?)
        ON CONFLICT(component) DO UPDATE SET timestamp=excluded.timestamp, data=excluded.data
    ''', ("open_positions", time.time(), json.dumps(positions)))

    # 2. Seed Trades (History)
    trades = [
        (time.time() - 86400*2, "SOL/USDT:USDT", "buy", 100, 10, "FILLED", "ord_1", 50),
        (time.time() - 86400*1, "XRP/USDT:USDT", "sell", 0.5, 1000, "FILLED", "ord_2", -10),
        (time.time() - 3600, "BTC/USDT:USDT", "buy", 52000, 0.01, "FILLED", "ord_3", 20)
    ]
    for t in trades:
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, price, quantity, status, order_id, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', t)

    # 3. Seed Logs
    logs = [
        (time.time(), "Strategist", "Scanning market...", "INFO"),
        (time.time(), "Executioner", "Order Filled", "INFO")
    ]
    for l in logs:
        cursor.execute("INSERT INTO logs (timestamp, module, message, level) VALUES (?, ?, ?, ?)", l)

    conn.commit()
    conn.close()
    print("Database seeded.")

if __name__ == "__main__":
    seed_db()
