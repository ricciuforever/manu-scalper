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
                order_id TEXT
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

    def save_trade(self, symbol, side, price, quantity, status, order_id, pnl=0):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (timestamp, symbol, side, price, quantity, status, order_id, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (time.time(), symbol, side, price, quantity, status, order_id, pnl))
        conn.commit()
        conn.close()

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
