import time
import numpy as np

class Strategist:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        # Cache to prevent re-creating the grid on every check if nothing has changed
        self.grid_orders_placed = False

    def run(self):
        print("📈 STRATEGIST: Online. Mode: GRID BOT.")
        while True:
            interval = self.db.get_setting('STRATEGIST_INTERVAL', 60)
            try:
                self._maintain_grid()
            except Exception as e:
                print(f"📈 STRATEGIST ERROR: {e}")
                self.db.log("Strategist", f"CRITICAL ERROR: {e}", "ERROR")
            time.sleep(interval)

    def _maintain_grid(self):
        """
        Calculates and places the grid limit orders.
        This is the core logic to set up the static grid based on user settings.
        """
        # Grid bot is designed to run on ONE symbol at a time
        symbols = self.db.get_setting('SYMBOLS', [])
        if not symbols:
            return
        symbol = symbols[0]

        # Get grid parameters from DB
        low = self.db.get_setting('GRID_RANGE_LOW')
        high = self.db.get_setting('GRID_RANGE_HIGH')
        levels = self.db.get_setting('GRID_LEVELS')
        side = self.db.get_setting('GRID_SIDE', 'NEUTRAL')

        if not all([low, high, levels]):
            self.db.log("Strategist", "Grid parameters are not fully configured. Halting.", "WARNING")
            return

        # --- Grid Calculation ---
        # Create a series of prices from low to high
        grid_prices = np.linspace(low, high, levels)

        # --- Get Current State ---
        current_price = self.exchange.get_ticker_price(symbol)
        if not current_price:
            self.db.log("Strategist", f"Could not fetch current price for {symbol}. Skipping grid maintenance.", "WARNING")
            return

        open_orders = self.exchange.get_open_orders(symbol)
        open_order_prices = {float(o['price']) for o in open_orders if o['type'] == 'limit'}

        self.db.log("Strategist", f"Maintaining grid for {symbol}. Found {len(open_order_prices)} open limit orders.", "DEBUG")

        # --- Place Missing Orders ---
        for price in grid_prices:
            # Round the calculated price to the correct precision for the exchange
            rounded_price = self.exchange.round_price(symbol, price)

            if rounded_price in open_order_prices:
                continue # Order already exists

            # Determine order side based on price relative to current market price
            order_side = None
            if side == 'NEUTRAL':
                if rounded_price < current_price:
                    order_side = 'buy'
                else:
                    order_side = 'sell'
            elif side == 'LONG':
                 if rounded_price < current_price:
                    order_side = 'buy'
            elif side == 'SHORT':
                if rounded_price > current_price:
                    order_side = 'sell'

            if order_side:
                self.db.log("Strategist", f"Placing missing grid order: {order_side} {symbol} @ {rounded_price}", "INFO")

                order_size_usdt = self.db.get_setting('BASE_ORDER_SIZE')
                leverage = self.db.get_setting('LEVERAGE')

                # Calculate the size in base currency (e.g., BTC) for the limit order
                # This is a simplified calculation. A more robust one would use the contract multiplier.
                # Size = (USDT Amount * Leverage) / Price
                notional_size = (order_size_usdt * leverage) / rounded_price

                # KuCoin Futures orders are in integer lots, so we must round down.
                order_size_lots = int(notional_size)

                if order_size_lots > 0:
                    self.exchange.place_limit_order(
                        symbol,
                        order_side,
                        order_size_lots,
                        rounded_price
                    )
                else:
                    self.db.log("Strategist", f"Order size for {symbol} @ {rounded_price} is zero. Skipping. Increase BASE_ORDER_SIZE.", "WARNING")
                time.sleep(0.2) # Avoid rate limiting
