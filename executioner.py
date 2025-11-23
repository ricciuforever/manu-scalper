import time
import threading
import technical_analysis as ta

# Global Cache to prevent API spam for Fixed SL placement
LAST_SL_CHECK = {}
SL_CHECK_INTERVAL = 10

class Executioner:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        self.risk_mgmt_lock = threading.Lock()

        # State tracking for Dynamic Trailing TP
        # Format: { 'BTC/USDT:USDT': { 'high': 96000, 'low': 95000, 'armed': False } }
        self.trailing_state = {}

    def run(self):
        symbols_count = len(self.db.get_setting('SYMBOLS', []))
        print(f"🔫 EXECUTIONER: Trend-Scalper Active ({symbols_count} symbols).")

        while True:
            exec_interval = self.db.get_setting('EXECUTION_INTERVAL', 2)

            # 1. Get Open Positions
            open_positions = self.exchange.get_all_open_positions()
            self.db.update_state('open_positions', open_positions)

            # 2. Risk Management (SL & Dynamic TP)
            if open_positions:
                try:
                    with self.risk_mgmt_lock:
                        self._manage_positions(open_positions)
                except Exception as e:
                    print(f"🔫 EXEC RISK ERROR: {e}")
                    self.db.log("Executioner", f"Risk Mgmt Error: {e}", "ERROR")

            # 3. Check for New Entries
            # Only scan if we are not maxed out
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
        """
        Master function for position management:
        1. Ensure Fixed SL (-1%) is present.
        2. Manage Dynamic Trailing TP (Arm +0.5%, Trail 0.2%).
        """
        # Cleanup trailing state for closed positions
        active_symbols = {p['symbol'] for p in positions}
        for s in list(self.trailing_state.keys()):
            if s not in active_symbols:
                del self.trailing_state[s]

        for pos in positions:
            symbol = pos['symbol']

            # --- A. FIXED STOP LOSS (-1%) & SAFETY TP (+2%) ---
            # Only check every few seconds to save API calls
            if time.time() - LAST_SL_CHECK.get(symbol, 0) > SL_CHECK_INTERVAL:
                self._ensure_protection_orders(pos)
                LAST_SL_CHECK[symbol] = time.time()

            # --- B. DYNAMIC TRAILING TAKE PROFIT ---
            self._manage_dynamic_exit(pos)

    def _ensure_protection_orders(self, pos):
        """
        Checks if SL and Safety TP orders exist.
        Ensures strict 1 SL (-1%) and 1 TP (+2%) structure.
        If missing or duplicate, resets BOTH.
        """
        symbol = pos['symbol']
        entry_price = float(pos['entryPrice'])
        side = pos['side']
        quantity = float(pos['quantity'])

        # Determine expected Close Side
        if side == 'long':
            close_side = 'sell'
        else:
            close_side = 'buy'

        # 1. Check existing orders
        open_orders = self.exchange.get_open_orders(symbol)

        sl_orders = []
        tp_orders = []

        for o in open_orders:
            # Both SL and TP are Stop Market orders in the Close direction
            if o['side'] == close_side and o.get('stopPrice'):
                price = float(o['stopPrice'])

                # Classify based on price relative to Entry
                if side == 'long':
                    if price < entry_price:
                        sl_orders.append(o)
                    elif price > entry_price:
                        tp_orders.append(o)
                else: # Short
                    if price > entry_price:
                        sl_orders.append(o)
                    elif price < entry_price:
                        tp_orders.append(o)

        # 2. Strict Verification: Must have exactly 1 SL and 1 TP
        if len(sl_orders) == 1 and len(tp_orders) == 1:
            return # All good

        # 3. If structure is invalid (0,0 or 1,0 or 0,1 or duplicates), RESET ALL.
        print(f"♻️ Order Mismatch for {symbol} (SL: {len(sl_orders)}, TP: {len(tp_orders)}). Resetting protection...")
        self.exchange.cancel_all_orders(symbol)

        # 4. Place Fixed SL (-1%)
        sl_percent = 0.01
        if side == 'long':
            stop_price = entry_price * (1 - sl_percent)
            stop_dir = 'down'
        else:
            stop_price = entry_price * (1 + sl_percent)
            stop_dir = 'up'

        print(f"🛡️ Placing FIXED SL for {symbol} @ {stop_price:.2f}")
        self.exchange.place_stop_market_order(symbol, close_side, quantity, stop_price, stop_dir, pos.get('marginMode'))

        # 5. Place Safety TP (+2%)
        tp_percent = 0.02
        if side == 'long':
            tp_price = entry_price * (1 + tp_percent)
            stop_dir = 'up'
        else:
            tp_price = entry_price * (1 - tp_percent)
            stop_dir = 'down'

        print(f"🎯 Placing SAFETY TP for {symbol} @ {tp_price:.2f}")
        self.exchange.place_stop_market_order(symbol, close_side, quantity, tp_price, stop_dir, pos.get('marginMode'))

    def _manage_dynamic_exit(self, pos):
        """
        Implements the Dynamic Trailing Logic:
        - Arm when Profit > 0.5%
        - Trail High/Low
        - Exit if Retracement > 0.2%
        """
        symbol = pos['symbol']
        entry_price = float(pos['entryPrice'])
        current_price = self.exchange.get_ticker_price(symbol)
        if not current_price: return

        side = pos['side']

        # Init State if missing
        if symbol not in self.trailing_state:
            self.trailing_state[symbol] = {
                'high': current_price, # For Longs
                'low': current_price,  # For Shorts
                'armed': False
            }

        state = self.trailing_state[symbol]

        # --- LOGIC LONG ---
        if side == 'long':
            # Update High Water Mark
            if current_price > state['high']:
                state['high'] = current_price

            # Check Arming Condition (+0.5%)
            roi = (current_price - entry_price) / entry_price
            if roi >= 0.005:
                if not state['armed']:
                    print(f"🎯 DYNAMIC TP ARMED for {symbol} (ROI: {roi*100:.2f}%)")
                state['armed'] = True

            # Check Exit Trigger (Retrace 0.2% from High)
            # Trigger = High * (1 - 0.002)
            trigger_price = state['high'] * 0.998

            if state['armed'] and current_price <= trigger_price:
                print(f"💰 TRAILING HIT {symbol}: Price {current_price} <= Trigger {trigger_price:.2f}. CLOSING.")
                self._close_position(symbol, 'sell', pos['quantity'])

        # --- LOGIC SHORT ---
        elif side == 'short':
            # Update Low Water Mark
            if current_price < state['low']:
                state['low'] = current_price

            # Check Arming Condition (+0.5% profit => Price dropped 0.5%)
            # ROI is positive when Price < Entry
            roi = (entry_price - current_price) / entry_price
            if roi >= 0.005:
                if not state['armed']:
                    print(f"🎯 DYNAMIC TP ARMED for {symbol} (ROI: {roi*100:.2f}%)")
                state['armed'] = True

            # Check Exit Trigger (Retrace 0.2% from Low => Price rises 0.2%)
            # Trigger = Low * (1 + 0.002)
            trigger_price = state['low'] * 1.002

            if state['armed'] and current_price >= trigger_price:
                 print(f"💰 TRAILING HIT {symbol}: Price {current_price} >= Trigger {trigger_price:.2f}. CLOSING.")
                 self._close_position(symbol, 'buy', pos['quantity'])

    def _close_position(self, symbol, side, qty):
        # Market Close
        print(f"⚡ CLOSING {symbol} MARKET ({side})")
        res = self.exchange.place_market_order(symbol, side, qty, reduce_only=True)

        # Always cleanup open orders (SL/TP) for this symbol
        self.exchange.cancel_all_orders(symbol)

        if res:
             self.db.log("Executioner", f"CLOSED {side} {symbol}", "INFO")
             # Clean up trailing state immediately
             if symbol in self.trailing_state:
                 del self.trailing_state[symbol]

    def _check_entry_signals(self, symbol):
        # Legge il segnale generato dallo Strategist
        state = self.shared_state.get(symbol, {})
        bias = state.get('bias', 'NEUTRAL')

        if bias == 'NEUTRAL': return

        current_price = self.exchange.get_ticker_price(symbol)
        leverage = state.get('leverage', 10)

        if bias == 'LONG':
            print(f"🚀 EXECUTIONER: Conferma SCALP LONG su {symbol}. Executing...")
            self._fire(symbol, 'buy', current_price, leverage)
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

        elif bias == 'SHORT':
            print(f"🚀 EXECUTIONER: Conferma SCALP SHORT su {symbol}. Executing...")
            self._fire(symbol, 'sell', current_price, leverage)
            self.shared_state[symbol]['bias'] = 'NEUTRAL'

    def _fire(self, symbol, side, price, leverage):
        base_order_size = self.db.get_setting('BASE_ORDER_SIZE', 20)
        res = self.exchange.execute_trade(symbol, side, base_order_size, leverage)
        if res:
            self.db.save_trade(symbol, side, price, base_order_size, "FILLED", res['id'])
            self.db.log("Executioner", f"ENTRY {side} {symbol} @ {price}", "INFO")
