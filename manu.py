import threading
import time
import logging
from connector_kucoin import KuCoinConnector
from strategist import Strategist
from executioner import Executioner
from config import *
from db_manager import DatabaseManager
from app import app # Flask App

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
        'ATR_MULTIPLIER_TP': DEFAULT_ATR_MULTIPLIER_TP
    }

    for key, val in defaults.items():
        if db.get_setting(key) is None:
            db.set_setting(key, val)
            print(f"⚙️ Initialized default setting: {key}")

def bot_loop(db, exchange):
    # Shared State kept for in-memory speed, but we will also sync to DB
    shared_state = {}

    strategist = Strategist(exchange, shared_state, db)
    executioner = Executioner(exchange, shared_state, db)

    t_strat = threading.Thread(target=strategist.run, daemon=True, name="Strategist")
    t_exec = threading.Thread(target=executioner.run, daemon=True, name="Executioner")

    t_strat.start()
    t_exec.start()

    # History Sync Thread
    t_sync = threading.Thread(target=history_sync_loop, args=(db, exchange), daemon=True, name="HistorySync")
    t_sync.start()

    try:
        while True:
            # Main Loop Heartbeat
            db.update_state('main_loop', {'status': 'running', 'timestamp': time.time()})
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 SHUTDOWN...")

def history_sync_loop(db, exchange):
    """
    Background loop to sync Trade History and PnL Ledger from KuCoin.
    Runs every 60 seconds.
    """
    print("📜 HISTORY SYNCHRONIZER STARTED.")
    while True:
        try:
            # 1. Sync Fills (for Trade History Table)
            symbols = db.get_setting('SYMBOLS', [])

            # Get last sync timestamp
            last_sync_state = db.get_state('history_sync')

            # Check if DB is empty to force deep sync
            existing_fills = db.get_history_fills(limit=1, days=365)
            is_empty = len(existing_fills) == 0

            if is_empty:
                print("📜 Empty History Detected: Fetching last 30 days...")
                start_ts = time.time() - (30 * 86400)
            else:
                # Default to last sync time or 24h ago if missing state
                start_ts = last_sync_state.get('last_ts', time.time() - 86400)

            # To be safe against clock skew or missed fills, we go back slightly more,
            # but 'trade_id' uniqueness prevents duplicates.
            # However, if we query too much, we hit rate limits.
            # KuCoin Trade History is limited.

            # If start_ts is too old, cap it? API might limit to 7 days or so.
            # But let's just stick to 'start_ts'.

            # We update 'new_last_ts' to now after successful sync
            new_last_ts = time.time()

            for symbol in symbols:
                fills = exchange.get_trade_history(symbol, start_at=start_ts)
                for fill in fills:
                    db.save_fill(fill)
                time.sleep(0.5) # Rate limit protection

            # 2. Sync Ledger (for PnL Stats)
            ledger_items = exchange.get_ledger_history(start_at=start_ts)
            for item in ledger_items:
                db.save_ledger_item(item)

            # Update state
            db.update_state('history_sync', {'last_ts': new_last_ts})

            # Log success (sparingly)
            # print(f"📜 History Synced. {len(ledger_items)} ledger items found.")

        except Exception as e:
            print(f"⚠️ HISTORY SYNC ERROR: {e}")

        time.sleep(60)

def main():
    print("\n--- MANU: HIGH-FREQUENCY SCALPER ACTIVATED ---")

    # Initialize Database
    db = DatabaseManager()
    init_db_settings(db)

    try:
        exchange = KuCoinConnector(KUCOIN_API_KEY, KUCOIN_SECRET, KUCOIN_PASSPHRASE)
        print(f"✅ Connesso a KuCoin.")
        # Avvia il Bot in un thread separato solo se connesso
        bot_thread = threading.Thread(target=bot_loop, args=(db, exchange), daemon=True)
        bot_thread.start()
    except Exception as e:
        print(f"❌ Errore Hardware (Bot Offline): {e}")
        # Non facciamo return, così il web server parte comunque per debug/config

    # Avvia Flask Web Server (Main Thread)
    # Host 0.0.0.0 rende accessibile dall'esterno (o dal sandbox)
    print("🚀 Avvio Interfaccia Web su porta 5002...")
    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
