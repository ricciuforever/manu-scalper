import time
import threading

class Executioner:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        self.processed_fills = set() # Cache in-memory of processed trade IDs

    def run(self):
        print("🔫 EXECUTIONER: Online. Mode: GRID BOT.")
        # Populate cache with recent fills to avoid processing old ones on startup
        self._warm_up_processed_fills()

        while True:
            exec_interval = self.db.get_setting('EXECUTION_INTERVAL', 10)
            try:
                self._process_grid_fills()
                self._check_global_stop_loss()
            except Exception as e:
                self.db.log("Executioner", f"CRITICAL ERROR: {e}", "ERROR")
            time.sleep(exec_interval)

    def _warm_up_processed_fills(self):
        """Pre-loads the processed_fills cache with recent trade IDs from the DB."""
        try:
            recent_fills = self.exchange.get_trade_history(
                self.db.get_setting('SYMBOLS')[0],
                limit=100 # Look at last 100 fills on startup
            )
            for fill in recent_fills:
                self.processed_fills.add(fill['tradeId'])
            self.db.log("Executioner", f"Warmed up cache with {len(self.processed_fills)} recent fills.", "INFO")
        except Exception as e:
            self.db.log("Executioner", f"Error during fill cache warm-up: {e}", "WARNING")

    def _process_grid_fills(self):
        """Checks for new fills and places the corresponding profit-taking order."""
        symbol = self.db.get_setting('SYMBOLS')[0]
        profit_margin = self.db.get_setting('PROFIT_PER_GRID') / 100 # Convert % to decimal

        # Fetch the last few fills. We don't need a deep history.
        recent_fills = self.exchange.get_trade_history(symbol, limit=20)

        for fill in recent_fills:
            if fill['tradeId'] in self.processed_fills:
                continue

            self.db.log("Executioner", f"New fill detected: {fill['side']} {fill['size']} {symbol} @ {fill['price']}", "INFO")

            fill_price = float(fill['price'])
            fill_size = float(fill['size'])

            # This was a grid order, now we place the opposing profit-taking order
            if fill['side'] == 'buy':
                # Placed a buy, now place a sell order slightly higher
                sell_price = fill_price * (1 + profit_margin)
                rounded_sell_price = self.exchange.round_price(symbol, sell_price)

                self.db.log("Executioner", f"Placing profit-take SELL order for {symbol} @ {rounded_sell_price}", "INFO")
                self.exchange.place_limit_order(
                    symbol,
                    'sell',
                    fill_size,
                    rounded_sell_price,
                    reduce_only=True # This ensures it only closes a position, not opens a new one
                )

            elif fill['side'] == 'sell':
                # Placed a sell, now place a buy order slightly lower
                buy_price = fill_price * (1 - profit_margin)
                rounded_buy_price = self.exchange.round_price(symbol, buy_price)

                self.db.log("Executioner", f"Placing profit-take BUY order for {symbol} @ {rounded_buy_price}", "INFO")
                self.exchange.place_limit_order(
                    symbol,
                    'buy',
                    fill_size,
                    rounded_buy_price,
                    reduce_only=True
                )

            # Mark this fill as processed
            self.processed_fills.add(fill['tradeId'])

    def _check_global_stop_loss(self):
        """If the price goes beyond the grid, close all positions and orders."""
        symbol = self.db.get_setting('SYMBOLS')[0]
        stop_loss_price = self.db.get_setting('STOP_LOSS_PRICE')

        if not stop_loss_price:
            return

        current_price = self.exchange.get_ticker_price(symbol)
        if not current_price:
            return

        positions = self.exchange.get_all_open_positions()

        # We assume for now that if there are any positions, they are for our grid symbol.
        if not positions:
            return

        # Global stop loss logic
        # A simple implementation: if price crosses the SL price, panic.
        # This assumes a LONG grid. A SHORT grid would need the inverse.
        # Let's handle NEUTRAL/LONG grid for now.

        if current_price < stop_loss_price:
            self.db.log("Executioner", f"!!! GLOBAL STOP LOSS TRIGGERED at {current_price} !!!", "CRITICAL")

            # 1. Close all open positions for the symbol
            for pos in positions:
                if pos['symbol'] == symbol:
                    close_side = 'sell' if pos['side'] == 'long' else 'buy'
                    self.exchange.place_market_order(
                        symbol,
                        close_side,
                        pos['quantity'],
                        reduce_only=True
                    )

            # 2. Cancel all open orders for the symbol to stop the grid
            self.exchange.cancel_all_orders(symbol)

            self.db.log("Executioner", "PANIC: All positions closed and grid orders canceled.", "CRITICAL")

            # Here we should probably have a mechanism to stop the bot or wait for manual intervention.
            # For now, we'll just let it try to rebuild the grid on the next cycle,
            # which might not be ideal. A 'paused' state would be better.
            time.sleep(3600) # Pause for an hour after a global stop loss

