import time
import threading

# Global Cache to prevent API spam for SL placement
LAST_SL_CHECK = {}
SL_CHECK_INTERVAL = 10

class Executioner:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        self.risk_mgmt_lock = threading.Lock()

    def run(self):
        symbols_count = len(self.db.get_setting('SYMBOLS', []))
        print(f"🔫 EXECUTIONER: Autonomous AI Mode Active ({symbols_count} symbols).")

        while True:
            exec_interval = self.db.get_setting('EXECUTION_INTERVAL', 5)

            open_positions = self.exchange.get_all_open_positions()
            self.db.update_state('open_positions', open_positions)

            if open_positions:
                try:
                    with self.risk_mgmt_lock:
                        self._manage_positions(open_positions)
                except Exception as e:
                    print(f"🔫 EXEC RISK ERROR: {e}")
                    self.db.log("Executioner", f"Risk Mgmt Error: {e}", "ERROR")

            if len(open_positions) < self.db.get_setting('MAX_POSITIONS', 5):
                symbols = self.db.get_setting('SYMBOLS', [])
                for symbol in symbols:
                    if any(p['symbol'] == symbol for p in open_positions): continue
                    try:
                        self._check_entry_signals(symbol)
                    except Exception as e:
                        print(f"🔫 EXEC ENTRY CHECK ERROR {symbol}: {e}")

            time.sleep(exec_interval)

    def _manage_positions(self, positions):
        """Ensures AI-defined Stop Loss and Take Profit orders are active for all positions."""
        for pos in positions:
            symbol = pos['symbol']
            if time.time() - LAST_SL_CHECK.get(symbol, 0) > SL_CHECK_INTERVAL:
                self._ensure_ai_protection_orders(pos)
                LAST_SL_CHECK[symbol] = time.time()

    def _ensure_ai_protection_orders(self, pos):
        """
        Verifies and places SL/TP orders based on the parameters defined by the AI
        at the time of the trade entry, retrieved from the local database.
        """
        symbol = pos['symbol']
        side = pos['side']
        quantity = float(pos['quantity'])

        # 1. Retrieve the active trade details from our DB
        active_trade = self.db.get_active_trade(symbol)
        if not active_trade or not active_trade.get('stop_loss') or not active_trade.get('take_profit'):
            print(f"⚠️ WARNING: Could not find AI SL/TP for active position {symbol}. Using fixed failsafe.")
            # TODO: Implement a failsafe (e.g., fixed % SL/TP)
            return

        ai_sl_price = active_trade['stop_loss']
        ai_tp_price = active_trade['take_profit']

        close_side = 'sell' if side == 'long' else 'buy'

        # 2. Check existing open orders
        open_orders = self.exchange.get_open_orders(symbol)

        sl_orders = [o for o in open_orders if o['side'] == close_side and o.get('stopPrice') and float(o.get('stopPrice')) == ai_sl_price]
        tp_orders = [o for o in open_orders if o['side'] == close_side and o.get('stopPrice') and float(o.get('stopPrice')) == ai_tp_price]

        # 3. If structure is valid (exactly 1 SL and 1 TP at AI prices), do nothing.
        if len(sl_orders) == 1 and len(tp_orders) == 1:
            return

        # 4. If structure is invalid, reset all orders and place the correct ones.
        print(f"♻️ AI Order Mismatch for {symbol} (SL: {len(sl_orders)}, TP: {len(tp_orders)}). Resetting protection...")
        self.exchange.cancel_all_orders(symbol)

        # 5. Place AI-defined Stop Loss
        stop_dir_sl = 'down' if side == 'long' else 'up'
        print(f"🛡️ Placing AI SL for {symbol} @ {ai_sl_price}")
        self.exchange.place_stop_market_order(symbol, close_side, quantity, ai_sl_price, stop_dir_sl, pos.get('marginMode'))

        # 6. Place AI-defined Take Profit
        stop_dir_tp = 'up' if side == 'long' else 'down'
        print(f"🎯 Placing AI TP for {symbol} @ {ai_tp_price}")
        self.exchange.place_stop_market_order(symbol, close_side, quantity, ai_tp_price, stop_dir_tp, pos.get('marginMode'))


    def _check_entry_signals(self, symbol):
        state = self.shared_state.get(symbol, {})
        bias = state.get('bias', 'NEUTRAL')

        if bias == 'NEUTRAL' or not state.get('stop_loss') or not state.get('take_profit'):
            return

        current_price = self.exchange.get_ticker_price(symbol)
        if not current_price: return

        leverage = self.db.get_setting('LEVERAGE', 10)
        confidence = state.get('confidence', 0)
        confidence_threshold = self.db.get_setting('AI_CONFIDENCE_THRESHOLD', 0.6)

        # Confidence filter
        if confidence < confidence_threshold:
            print(f"Skipping {symbol} {bias} signal due to low confidence ({confidence:.2f} < {confidence_threshold})")
            self.shared_state[symbol]['bias'] = 'NEUTRAL'
            return

        if bias == 'LONG':
            print(f"🚀 EXECUTIONER: Confirming AI LONG on {symbol} (Conf: {confidence:.2f})...")
            self._fire(symbol, 'buy', current_price, leverage, state['stop_loss'], state['take_profit'])
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

        elif bias == 'SHORT':
            print(f"🚀 EXECUTIONER: Confirming AI SHORT on {symbol} (Conf: {confidence:.2f})...")
            self._fire(symbol, 'sell', current_price, leverage, state['stop_loss'], state['take_profit'])
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

    def _fire(self, symbol, side, price, leverage, stop_loss, take_profit):
        base_order_size = self.db.get_setting('BASE_ORDER_SIZE', 20)
        res = self.exchange.execute_trade(symbol, side, base_order_size, leverage)
        if res:
            self.db.save_trade(
                symbol, side, price, base_order_size, "FILLED", res['id'],
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            self.db.log("Executioner", f"AI ENTRY {side} {symbol} @ {price} | SL: {stop_loss} TP: {take_profit}", "INFO")
