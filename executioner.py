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
                    self.db.log("Executioner", f"CRITICAL Risk Mgmt Error: {e}", "ERROR")

            if len(open_positions) < self.db.get_setting('MAX_POSITIONS', 5):
                symbols = self.db.get_setting('SYMBOLS', [])
                for symbol in symbols:
                    if any(p['symbol'] == symbol for p in open_positions): continue
                    try:
                        self._check_entry_signals(symbol)
                    except Exception as e:
                        self.db.log("Executioner", f"Entry Check Error {symbol}: {e}", "ERROR")
            time.sleep(exec_interval)

    def _manage_positions(self, positions):
        """Ensures AI-defined Stop Loss and Take Profit orders are active for all positions."""
        for pos in positions:
            symbol = pos['symbol']
            if time.time() - LAST_SL_CHECK.get(symbol, 0) > SL_CHECK_INTERVAL:
                self._ensure_ai_protection_orders(pos)
                LAST_SL_CHECK[symbol] = time.time()

    def _ensure_ai_protection_orders(self, pos):
        """Verifies and places SL/TP orders based on AI parameters from the DB."""
        symbol = pos['symbol']
        side = pos['side']
        quantity = float(pos['quantity'])

        active_trade = self.db.get_active_trade(symbol)
        if not active_trade or not active_trade.get('stop_loss') or not active_trade.get('take_profit'):
            self.db.log("Executioner", f"WARNING: No AI SL/TP found for {symbol}. Position is unprotected.", "WARNING")
            return

        ai_sl_price = active_trade['stop_loss']
        ai_tp_price = active_trade['take_profit']
        self.db.log("Executioner", f"Verifying protection for {symbol}: AI SL={ai_sl_price}, AI TP={ai_tp_price}", "DEBUG")

        close_side = 'sell' if side == 'long' else 'buy'
        open_orders = self.exchange.get_open_orders(symbol)

        sl_found = False
        tp_found = False

        # Use a small tolerance for float comparison
        TOLERANCE = 1e-9

        for o in open_orders:
            stop_price = o.get('stopPrice')
            if o['side'] == close_side and stop_price:
                stop_price = float(stop_price)
                self.db.log("Executioner", f"Found open stop order for {symbol}: Side={o['side']}, StopPrice={stop_price}", "DEBUG")
                if abs(stop_price - ai_sl_price) < TOLERANCE:
                    sl_found = True
                    self.db.log("Executioner", f"Matched AI SL for {symbol} at {stop_price}", "INFO")
                elif abs(stop_price - ai_tp_price) < TOLERANCE:
                    tp_found = True
                    self.db.log("Executioner", f"Matched AI TP for {symbol} at {stop_price}", "INFO")

        if sl_found and tp_found:
            return # All good

        self.db.log("Executioner", f"Order Mismatch for {symbol} (SL Found: {sl_found}, TP Found: {tp_found}). Resetting protection.", "WARNING")

        cancel_res = self.exchange.cancel_all_orders(symbol)
        if not cancel_res:
             self.db.log("Executioner", f"Failed to cancel orders for {symbol} during reset. Aborting.", "ERROR")
             return

        # Place AI-defined Stop Loss
        stop_dir_sl = 'down' if side == 'long' else 'up'
        self.db.log("Executioner", f"Placing AI SL for {symbol} @ {ai_sl_price}", "INFO")
        sl_res = self.exchange.place_stop_market_order(symbol, close_side, quantity, ai_sl_price, stop_dir_sl, pos.get('marginMode'))
        if not sl_res:
            self.db.log("Executioner", f"FAILED to place AI SL for {symbol} @ {ai_sl_price}", "ERROR")

        # Place AI-defined Take Profit
        stop_dir_tp = 'up' if side == 'long' else 'down'
        self.db.log("Executioner", f"Placing AI TP for {symbol} @ {ai_tp_price}", "INFO")
        tp_res = self.exchange.place_stop_market_order(symbol, close_side, quantity, ai_tp_price, stop_dir_tp, pos.get('marginMode'))
        if not tp_res:
            self.db.log("Executioner", f"FAILED to place AI TP for {symbol} @ {ai_tp_price}", "ERROR")

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

        if confidence < confidence_threshold:
            self.shared_state[symbol]['bias'] = 'NEUTRAL'
            return

        if bias == 'LONG':
            self.db.log("Executioner", f"Confirming AI LONG on {symbol} (Conf: {confidence:.2f})", "INFO")
            self._fire(symbol, 'buy', current_price, leverage, state['stop_loss'], state['take_profit'])
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

        elif bias == 'SHORT':
            self.db.log("Executioner", f"Confirming AI SHORT on {symbol} (Conf: {confidence:.2f})", "INFO")
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
