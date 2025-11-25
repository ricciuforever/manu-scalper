# mock_connector.py
# This is a mock KuCoinConnector to allow the application to run in an offline test environment.

import pandas as pd
import time

class MockKuCoinConnector:
    def __init__(self, api_key, api_secret, api_passphrase):
        """Mocks the initialization. Does not connect to any real service."""
        print("🔧 MOCK KuCoinConnector initialized.")
        self._positions = []

    def get_historical_data(self, symbol, timeframe, limit=200):
        """Returns a DataFrame with fake kline data."""
        # print(f"🔧 MOCK: Getting historical data for {symbol} ({timeframe})")
        end_time = int(time.time() * 1000)
        start_time = end_time - limit * self._tf_to_ms(timeframe)

        timestamps = pd.to_datetime(range(start_time, end_time, self._tf_to_ms(timeframe)), unit='ms')

        data = {
            'timestamp': [ts.timestamp() * 1000 for ts in timestamps],
            'open': [100 + i for i in range(len(timestamps))],
            'high': [105 + i for i in range(len(timestamps))],
            'low': [95 + i for i in range(len(timestamps))],
            'close': [102 + i for i in range(len(timestamps))],
            'volume': [1000 + i * 10 for i in range(len(timestamps))]
        }
        df = pd.DataFrame(data)
        return df

    def get_ticker_price(self, symbol):
        """Returns a fake ticker price."""
        return 102.5

    def get_all_open_positions(self):
        """Returns the list of mock open positions."""
        return self._positions

    def get_open_orders(self, symbol):
        """Returns an empty list of open orders."""
        return []

    def cancel_all_orders(self, symbol):
        """Mocks cancelling all orders."""
        print(f"🔧 MOCK: Canceled all orders for {symbol}")
        return True

    def place_stop_market_order(self, symbol, side, quantity, stop_price, stop_dir, margin_mode):
        """Mocks placing a stop market order."""
        print(f"🔧 MOCK: Placed STOP MARKET order for {symbol} ({side}, {quantity} @ {stop_price})")
        return {'id': f'mock_stop_{int(time.time())}'}

    def place_market_order(self, symbol, side, qty, reduce_only=False):
        """Mocks placing a market order."""
        print(f"🔧 MOCK: Placed MARKET order for {symbol} ({side}, {qty})")
        if reduce_only:
            self._positions = [p for p in self._positions if p['symbol'] != symbol]
        return {'id': f'mock_market_{int(time.time())}'}

    def execute_trade(self, symbol, side, amount, leverage):
        """Mocks executing a trade and simulates adding a position."""
        print(f"🔧 MOCK: Executed TRADE for {symbol} ({side}, ${amount}, {leverage}x)")

        new_pos = {
            'symbol': symbol,
            'side': side,
            'quantity': amount / 100,
            'entryPrice': self.get_ticker_price(symbol),
            'unrealisedPnl': 0.0,
            'marginMode': 'isolated'
        }
        self._positions.append(new_pos)

        return {'id': f'mock_trade_{int(time.time())}'}

    def get_trade_history(self, symbol, start_at):
        return []

    def get_ledger_history(self, start_at):
        return []

    def _tf_to_ms(self, timeframe):
        if timeframe == '1m': return 60 * 1000
        if timeframe == '5m': return 5 * 60 * 1000
        if timeframe == '15m': return 15 * 60 * 1000
        if timeframe == '1h': return 60 * 60 * 1000
        if timeframe == '4h': return 4 * 60 * 60 * 1000
        return 60 * 1000
