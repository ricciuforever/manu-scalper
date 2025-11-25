import time
import threading

# Global Cache to prevent API spam for SL placement
LAST_SL_CHECK = {}
SL_CHECK_INTERVAL = 10

# Failsafe percentages for unprotected positions
FAILSAFE_SL_PERCENT = 0.015  # 1.5%
FAILSAFE_TP_PERCENT = 0.030  # 3.0%

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
            try:
                open_positions = self.exchange.get_all_open_positions()
                self.db.update_state('open_positions', open_positions)

                if open_positions:
                    with self.risk_mgmt_lock:
                        self._manage_positions(open_positions)

                if len(open_positions) < self.db.get_setting('MAX_POSITIONS', 5):
                    symbols = self.db.get_setting('SYMBOLS', [])
                    for symbol in symbols:
                        if any(p['symbol'] == symbol for p in open_positions): continue
                        self._check_entry_signals(symbol)
            except Exception as e:
                self.db.log("Executioner", f"CRITICAL LOOP ERROR: {e}", "ERROR")
            time.sleep(exec_interval)

    def _manage_positions(self, positions):
        """Ensures Stop Loss and Take Profit orders are active for all positions."""
        for pos in positions:
            symbol = pos['symbol']
            if time.time() - LAST_SL_CHECK.get(symbol, 0) > SL_CHECK_INTERVAL:
                self._ensure_protection_orders(pos)
                LAST_SL_CHECK[symbol] = time.time()

    def _ensure_protection_orders(self, pos):
        """
        Verifies and places SL/TP orders using intelligent rounding.
        Applies a failsafe if no AI parameters are found.
        """
        symbol = pos['symbol']
        side = pos['side']
        quantity = float(pos['quantity'])
        entry_price = float(pos['entryPrice'])

        sl_price_raw, tp_price_raw = None, None

        active_trade = self.db.get_active_trade(symbol)
        if active_trade and active_trade.get('stop_loss') and active_trade.get('take_profit'):
            sl_price_raw = active_trade['stop_loss']
            tp_price_raw = active_trade['take_profit']
        else:
            self.db.log("Executioner", f"No AI SL/TP found for {symbol}. Applying failsafe.", "WARNING")
            if side == 'long':
                sl_price_raw = entry_price * (1 - FAILSAFE_SL_PERCENT)
                tp_price_raw = entry_price * (1 + FAILSAFE_TP_PERCENT)
            else:
                sl_price_raw = entry_price * (1 + FAILSAFE_SL_PERCENT)
                tp_price_raw = entry_price * (1 - FAILSAFE_TP_PERCENT)

        # ** CRITICAL STEP: Round prices to the exchange's required precision **
        sl_price = self.exchange.round_price(symbol, sl_price_raw)
        tp_price = self.exchange.round_price(symbol, tp_price_raw)

        close_side = 'sell' if side == 'long' else 'buy'
        open_orders = self.exchange.get_open_orders(symbol)

        sl_found, tp_found = False, False

        for o in open_orders:
            stop_price = o.get('stopPrice')
            if o['side'] == close_side and stop_price:
                # Direct comparison is now safe because we rounded our calculated price
                if float(stop_price) == sl_price:
                    sl_found = True
                elif float(stop_price) == tp_price:
                    tp_found = True

        if sl_found and tp_found:
            return

        self.db.log("Executioner", f"Protection mismatch for {symbol} (SL: {sl_found}, TP: {tp_found}). Resetting.", "INFO")
        self.exchange.cancel_all_orders(symbol)

        stop_dir_sl = 'down' if side == 'long' else 'up'
        self.exchange.place_stop_market_order(symbol, close_side, quantity, sl_price, stop_dir_sl, pos.get('marginMode'))

        stop_dir_tp = 'up' if side == 'long' else 'down'
        self.exchange.place_stop_market_order(symbol, close_side, quantity, tp_price, stop_dir_tp, pos.get('marginMode'))

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

        # ** CRITICAL STEP: Round AI prices before saving them **
        sl = self.exchange.round_price(symbol, state['stop_loss'])
        tp = self.exchange.round_price(symbol, state['take_profit'])

        if bias == 'LONG':
            self._fire(symbol, 'buy', current_price, leverage, sl, tp)
            self.shared_state[symbol]['bias'] = 'NEUTRAL'
        elif bias == 'SHORT':
            self._fire(symbol, 'sell', current_price, leverage, sl, tp)
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

    def _fire(self, symbol, side, price, leverage, stop_loss, take_profit):
        self.db.log("Executioner", f"Executing AI ENTRY {side} {symbol} @ {price} | SL: {stop_loss} TP: {take_profit}", "INFO")
        base_order_size = self.db.get_setting('BASE_ORDER_SIZE', 20)
        res = self.exchange.execute_trade(symbol, side, base_order_size, leverage)
        if res:
            self.db.save_trade(
                symbol, side, price, base_order_size, "FILLED", res['id'],
                stop_loss=stop_loss,
                take_profit=take_profit
            )
