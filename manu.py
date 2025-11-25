import threading
import time
import logging
import os
from config import *
from db_manager import DatabaseManager
from app import app # Flask App

# --- Dynamic Connector Import based on Environment ---
IS_TEST_ENV = os.getenv('IS_TEST_ENV', 'false').lower() == 'true'
if IS_TEST_ENV:
    from mock_connector import MockKuCoinConnector as KuCoinConnector
else:
    from connector_kucoin import KuCoinConnector
# --- End Dynamic Import ---

from strategist import Strategist
from executioner import Executioner


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def init_db_settings(db):
    """Initialize DB with defaults if empty."""
    defaults = {
        'SYMBOLS': DEFAULT_SYMBOLS,
        'LEVERAGE': DEFAULT_LEVERAGE,
        'BASE_ORDER_SIZE': DEFAULT_BASE_ORDER_SIZE,
        'MAX_POSITIONS': DEFAULT_MAX_POSITIONS,
        'STRATEGIST_INTERVAL': DEFAULT_STRATEGIST_INTERVAL,
        'EXECUTION_INTERVAL': DEFAULT_EXECUTION_INTERVAL,
        'AI_MODEL': DEFAULT_AI_MODEL,
        'ORDER_IMBALANCE_THR': DEFAULT_ORDER_IMBALANCE_THR,
        'MIN_VOLUME_24H': DEFAULT_MIN_VOLUME_24H,
        'ATR_PERIOD': DEFAULT_ATR_PERIOD,
        'ATR_MULTIPLIER_SL': DEFAULT_ATR_MULTIPLIER_SL,
        'ATR_MULTIPLIER_TP': DEFAULT_ATR_MULTIPLIER_TP,
        'AI_PROMPT': DEFAULT_AI_PROMPT,
        'AI_CONFIDENCE_THRESHOLD': DEFAULT_AI_CONFIDENCE_THRESHOLD
    }

    for key, val in defaults.items():
        if db.get_setting(key) is None:
            db.set_setting(key, val)
            print(f"⚙️ Initialized default setting: {key}")

def bot_loop(db, exchange):
    shared_state = {}
    strategist = Strategist(exchange, shared_state, db)
    executioner = Executioner(exchange, shared_state, db)

    t_strat = threading.Thread(target=strategist.run, daemon=True, name="Strategist")
    t_exec = threading.Thread(target=executioner.run, daemon=True, name="Executioner")

    t_strat.start()
    t_exec.start()

    # History sync is disabled in test env to avoid mock complexity
    if not IS_TEST_ENV:
        t_sync = threading.Thread(target=history_sync_loop, args=(db, exchange), daemon=True, name="HistorySync")
        t_sync.start()

    try:
        while True:
            db.update_state('main_loop', {'status': 'running', 'timestamp': time.time()})
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 SHUTDOWN...")

def history_sync_loop(db, exchange):
    """Background loop to sync Trade History and PnL Ledger from KuCoin."""
    print("📜 HISTORY SYNCHRONIZER STARTED.")
    while True:
        try:
            symbols = db.get_setting('SYMBOLS', [])
            last_sync_state = db.get_state('history_sync')
            existing_fills = db.get_history_fills(limit=1, days=365)
            is_empty = len(existing_fills) == 0

            if is_empty:
                start_ts = time.time() - (30 * 86400)
            else:
                start_ts = last_sync_state.get('last_ts', time.time() - 86400)

            new_last_ts = time.time()
            for symbol in symbols:
                fills = exchange.get_trade_history(symbol, start_at=start_ts)
                for fill in fills:
                    db.save_fill(fill)
                time.sleep(0.5)

            ledger_items = exchange.get_ledger_history(start_at=start_ts)
            for item in ledger_items:
                db.save_ledger_item(item)

            db.update_state('history_sync', {'last_ts': new_last_ts})
        except Exception as e:
            print(f"⚠️ HISTORY SYNC ERROR: {e}")
        time.sleep(60)

def main():
    print("\n--- MANU: HIGH-FREQUENCY SCALPER ACTIVATED ---")
    if IS_TEST_ENV:
        print("--- RUNNING IN TEST ENVIRONMENT (MOCKED DATA) ---")

    db = DatabaseManager()
    init_db_settings(db)

    try:
        exchange = KuCoinConnector(KUCOIN_API_KEY, KUCOIN_SECRET, KUCOIN_PASSPHRASE)
        print(f"✅ Connesso a KuCoin.")
        bot_thread = threading.Thread(target=bot_loop, args=(db, exchange), daemon=True)
        bot_thread.start()
    except Exception as e:
        print(f"❌ Errore Hardware (Bot Offline): {e}")

    print("🚀 Avvio Interfaccia Web su porta 5002...")
    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
