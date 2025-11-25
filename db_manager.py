import sqlite3
import json
import logging
import time
from datetime import datetime

DB_PATH = "manu_bot.db"

class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        # Settings Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                type TEXT
            )
        ''')

        # Logs Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                level TEXT,
                module TEXT,
                message TEXT
            )
        ''')

        # Signals Table (AI Decisions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT,
                bias TEXT,
                risk TEXT,
                leverage REAL,
                reason TEXT
            )
        ''')

        # Trades Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                symbol TEXT,
                side TEXT,
                price REAL,
                quantity REAL,
                pnl REAL,
                status TEXT,
                order_id TEXT,
                stop_loss REAL,
                take_profit REAL
            )
        ''')

        # State/Heartbeat Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS state (
                component TEXT PRIMARY KEY,
                timestamp REAL,
                data TEXT
            )
        ''')

        # History Fills Table (Executions)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history_fills (
                trade_id TEXT PRIMARY KEY,
                symbol TEXT,
                side TEXT,
                price REAL,
                size REAL,
                value REAL,
                fee REAL,
                fee_currency TEXT,
                timestamp REAL,
                order_id TEXT,
                trade_type TEXT
            )
        ''')

        # History Ledger Table (PnL)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                amount REAL,
                type TEXT,
                currency TEXT,
                remark TEXT,
                UNIQUE(timestamp, amount, type, remark)
            )
        ''')

        conn.commit()
        conn.close()

    def get_setting(self, key, default=None, type_cast=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value, type FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()

        if row:
            val, val_type = row
            try:
                if val_type == 'int': return int(val)
                if val_type == 'float': return float(val)
                if val_type == 'bool': return val.lower() == 'true'
                if val_type == 'list' or val_type == 'json': return json.loads(val)
                return val
            except:
                return val
        return default

    def set_setting(self, key, value):
        conn = self.get_connection()
        cursor = conn.cursor()

        val_type = 'str'
        if isinstance(value, int): val_type = 'int'
        elif isinstance(value, float): val_type = 'float'
        elif isinstance(value, bool): val_type = 'bool'
        elif isinstance(value, (list, dict)):
            val_type = 'json'
            value = json.dumps(value)
        else:
            value = str(value)

        cursor.execute('''
            INSERT INTO settings (key, value, type) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, type=excluded.type
        ''', (key, value, val_type))

        conn.commit()
        conn.close()

    def log(self, module, message, level="INFO"):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO logs (timestamp, module, message, level) VALUES (?, ?, ?, ?)",
                       (time.time(), module, message, level))
        conn.commit()
        conn.close()

    def save_signal(self, symbol, bias, risk, leverage, reason):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO signals (timestamp, symbol, bias, risk, leverage, reason)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (time.time(), symbol, bias, risk, leverage, reason))
        conn.commit()
        conn.close()

    def save_trade(self, symbol, side, price, quantity, status, order_id, pnl=0, stop_loss=None, take_profit=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, price, quantity, status, order_id, pnl, stop_loss, take_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (time.time(), symbol, side, price, quantity, status, order_id, pnl, stop_loss, take_profit))
        conn.commit()
        conn.close()

    def get_active_trade(self, symbol):
        """Fetches the most recent active (FILLED) trade for a symbol."""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM trades
            WHERE symbol = ? AND status = 'FILLED'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol,))

        row = cursor.fetchone()
        if not row:
            return None

        # Convert row to dict
        cols = [description[0] for description in cursor.description]
        trade = dict(zip(cols, row))
        conn.close()
        return trade

    def update_state(self, component, data):
        conn = self.get_connection()
        cursor = conn.cursor()
        json_data = json.dumps(data)
        cursor.execute('''
            INSERT INTO state (component, timestamp, data) VALUES (?, ?, ?)
            ON CONFLICT(component) DO UPDATE SET timestamp=excluded.timestamp, data=excluded.data
        ''', (component, time.time(), json_data))
        conn.commit()
        conn.close()

    def save_fill(self, fill):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO history_fills
            (trade_id, symbol, side, price, size, value, fee, fee_currency, timestamp, order_id, trade_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            fill['tradeId'], fill['symbol'], fill['side'], fill['price'], fill['size'],
            fill['value'], fill['fee'], fill['feeCurrency'], fill['timestamp'],
            fill['orderId'], fill['tradeType']
        ))
        conn.commit()
        conn.close()

    def save_ledger_item(self, item):
        conn = self.get_connection()
        cursor = conn.cursor()
        # Ledger doesn't have a unique ID in the simple dict, using UNIQUE constraint on fields
        cursor.execute('''
            INSERT OR IGNORE INTO history_ledger
            (timestamp, amount, type, currency, remark)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            item['timestamp'], item['amount'], item['type'], item['currency'], item['remark']
        ))
        conn.commit()
        conn.close()

    def get_history_fills(self, limit=100, days=30):
        ts_limit = time.time() - (days * 86400)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM history_fills WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?", (ts_limit, limit))
        cols = [description[0] for description in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_history_ledger(self, days=30):
        ts_limit = time.time() - (days * 86400)
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM history_ledger WHERE timestamp >= ? ORDER BY timestamp ASC", (ts_limit,))
        cols = [description[0] for description in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_recent_logs(self, limit=50):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, module, message, level FROM logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_recent_signals(self, limit=20):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, symbol, bias, risk, leverage, reason FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_state(self, component):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM state WHERE component = ?", (component,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return {}
