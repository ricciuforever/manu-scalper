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

    try:
        while True:
            # Main Loop Heartbeat
            db.update_state('main_loop', {'status': 'running', 'timestamp': time.time()})
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 SHUTDOWN...")

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
