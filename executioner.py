import time
import threading
import technical_analysis as ta

# Global Cache
ORDER_CACHE = {}
LAST_PLACEMENT_TIMESTAMP = {}
PLACEMENT_BUFFER_SECONDS = 5
RISK_MGMT_INTERVAL = 1

class Executioner:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        self.risk_mgmt_lock = threading.Lock()

    def run(self):
        symbols_count = len(self.db.get_setting('SYMBOLS', []))
        print(f"🔫 EXECUTIONER: Pattugliamento attivo su {symbols_count} asset. Modalità Swing.")

        while True:
            exec_interval = self.db.get_setting('EXECUTION_INTERVAL', 10)

            open_positions = self.exchange.get_all_open_positions()
            self.db.update_state('open_positions', open_positions)

            if open_positions:
                try:
                    with self.risk_mgmt_lock:
                        self._apply_swing_risk(open_positions)
                except Exception as e:
                    print(f"🔫 EXEC RISK ERROR: {e}")
                    self.db.log("Executioner", f"Risk Mgmt Error: {e}", "ERROR")

                # Monitoraggio costante se siamo vicini al limite posizioni
                if len(open_positions) >= self.db.get_setting('MAX_POSITIONS', 3):
                    time.sleep(RISK_MGMT_INTERVAL)
                    continue

            # Scansione per nuove entrate
            symbols = self.db.get_setting('SYMBOLS', [])
            for symbol in symbols:
                # Evita di rientrare se abbiamo già una posizione
                if any(p['symbol'] == symbol for p in open_positions): continue

                try:
                    self._check_entry_signals(symbol)
                except Exception as e:
                    print(f"🔫 EXEC ENTRY CHECK ERROR {symbol}: {e}")

            time.sleep(exec_interval)

    def _get_atr_for_management(self, symbol):
        # Swing Trading usa un ATR su timeframe più alto (1h) per SL/TP più ampi
        atr_period = self.db.get_setting('ATR_PERIOD', 14)
        try:
            klines = self.exchange.get_historical_data(symbol, '1h', limit=atr_period + 5)
            if klines.empty: return 0.0
            return ta.calculate_atr(klines, atr_period)
        except:
            return 0.0

    def _apply_swing_risk(self, open_positions):
        """Gestisce SL e TP per Swing Trading (più larghi e pazienti).
           *** LOGICA MODIFICATA: SL/TP fisso, senza trailing o aggiornamenti dopo il piazzamento iniziale. ***
        """
        global ORDER_CACHE
        global LAST_PLACEMENT_TIMESTAMP

        # Cleanup Cache
        open_symbols = {pos['symbol'] for pos in open_positions}
        keys_to_delete = [s for s in ORDER_CACHE if s not in open_symbols]
        for key in keys_to_delete:
            if key in ORDER_CACHE: del ORDER_CACHE[key]

        # Swing Settings: SL/TP basati su ATR 1H (moltiplicatori configurabili)
        # Default Swing: SL=2.0 ATR, TP=3.0 ATR (Risk:Reward 1:1.5)
        atr_mult_sl = 2.0
        atr_mult_tp = 3.0

        for pos in open_positions:
            symbol = pos['symbol']

            if symbol not in ORDER_CACHE:
                ORDER_CACHE[symbol] = {'sl_id': None, 'tp_id': None}

            entry_price = float(pos.get('entryPrice') or 0)
            side = pos.get('side')
            quantity = float(pos.get('quantity') or 0)
            leverage = float(pos.get('leverage') or 5) # Swing usa meno leva
            margin_mode = pos.get('marginMode')

            if entry_price == 0 or quantity == 0: continue

            current_price = self.exchange.get_ticker_price(symbol)
            if not current_price: current_price = entry_price

            # Check Active Orders
            current_open_orders = self.exchange.get_open_orders(symbol)

            sl_orders_found = []
            tp_orders_found = []

            for o in current_open_orders:
                stop_price = float(o.get('stopPrice') or 0)
                if stop_price == 0: continue

                o_side = o['side']
                is_sl = False
                is_tp = False

                if side == 'long' and o_side == 'sell':
                    if stop_price < entry_price: is_sl = True # Basic check
                    elif stop_price > entry_price: is_tp = True
                elif side == 'short' and o_side == 'buy':
                    if stop_price > entry_price: is_sl = True
                    elif stop_price < entry_price: is_tp = True

                if is_sl: sl_orders_found.append(o)
                if is_tp: tp_orders_found.append(o)

            # Gestione SL/TP (Placement Logic)
            atr = self._get_atr_for_management(symbol)
            if atr == 0: atr = entry_price * 0.02 # Fallback 2%

            base_sl_dist = atr * atr_mult_sl
            base_tp_dist = atr * atr_mult_tp

            # --- CALCOLO PREZZI ---
            if side == 'long':
                target_sl = entry_price - base_sl_dist
                target_tp = entry_price + base_tp_dist
                close_side = 'sell'
                sl_dir = 'down'
                tp_dir = 'up'
            else:
                target_sl = entry_price + base_sl_dist
                target_tp = entry_price - base_tp_dist
                close_side = 'buy'
                sl_dir = 'up'
                tp_dir = 'down'

            target_sl = round(target_sl, 5)
            target_tp = round(target_tp, 5)

            # --- PIAZZAMENTO ORDINI (FISSO) ---

            # 1. SL: Piazza solo se non è già presente. Nessun aggiornamento.
            sl_key = f"{symbol}_SL"
            if not sl_orders_found:
                if time.time() - LAST_PLACEMENT_TIMESTAMP.get(sl_key, 0) > PLACEMENT_BUFFER_SECONDS:
                    print(f"🛡️ New SL {symbol} @ {target_sl}")
                    res = self.exchange.place_stop_market_order(symbol, close_side, quantity, target_sl, sl_dir, margin_mode)
                    if res: LAST_PLACEMENT_TIMESTAMP[sl_key] = time.time()

            # 2. TP: Piazza solo se non è già presente. Nessun aggiornamento.
            tp_key = f"{symbol}_TP"
            if not tp_orders_found:
                if time.time() - LAST_PLACEMENT_TIMESTAMP.get(tp_key, 0) > PLACEMENT_BUFFER_SECONDS:
                    print(f"🎯 New TP {symbol} @ {target_tp}")
                    res = self.exchange.place_stop_market_order(symbol, close_side, quantity, target_tp, tp_dir, margin_mode)
                    if res: LAST_PLACEMENT_TIMESTAMP[tp_key] = time.time()


    def _check_entry_signals(self, symbol):
        # Legge il segnale generato dallo Strategist AI
        state = self.shared_state.get(symbol, {})
        bias = state.get('bias', 'NEUTRAL')

        if bias == 'NEUTRAL': return

        # Execution conferma e spara
        current_price = self.exchange.get_ticker_price(symbol)
        leverage = state.get('leverage', 5)

        if bias == 'LONG':
            print(f"🚀 EXECUTIONER: Conferma ENTRY LONG su {symbol}. Executing...")
            self._fire(symbol, 'buy', current_price, leverage)
            # Pulisce il segnale per evitare doppi ingressi
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

        elif bias == 'SHORT':
            print(f"🚀 EXECUTIONER: Conferma ENTRY SHORT su {symbol}. Executing...")
            self._fire(symbol, 'sell', current_price, leverage)
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

    def _fire(self, symbol, side, price, leverage):
        base_order_size = self.db.get_setting('BASE_ORDER_SIZE', 20)

        res = self.exchange.execute_trade(symbol, side, base_order_size, leverage)
        if res:
            order_id = res['id']
            self.db.save_trade(symbol, side, price, base_order_size, "FILLED", order_id)
            self.db.log("Executioner", f"ENTRY {side} {symbol} @ {price}", "INFO")
        else:
            print(f"❌ FAIL {symbol}: Order execution failed.")
            self.db.log("Executioner", f"FAIL {side} {symbol}", "ERROR")

        time.sleep(2)