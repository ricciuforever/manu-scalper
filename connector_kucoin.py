
import logging
import pandas as pd
import time
import uuid
from kucoin_universal_sdk.api.client import DefaultClient
from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder
from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT, GLOBAL_FUTURES_API_ENDPOINT

# Models - CORRECTED IMPORTS based on SDK structure
from kucoin_universal_sdk.generate.futures.market.model_get_ticker_req import GetTickerReqBuilder
from kucoin_universal_sdk.generate.futures.market.model_get_klines_req import GetKlinesReqBuilder
from kucoin_universal_sdk.generate.futures.market.model_get_part_order_book_req import GetPartOrderBookReqBuilder
from kucoin_universal_sdk.generate.futures.fundingfees.model_get_current_funding_rate_req import GetCurrentFundingRateReqBuilder

from kucoin_universal_sdk.generate.futures.positions.model_get_position_list_req import GetPositionListReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_cancel_all_orders_v1_req import CancelAllOrdersV1ReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_cancel_order_by_client_oid_req import CancelOrderByClientOidReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_cancel_order_by_id_req import CancelOrderByIdReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_get_order_by_order_id_req import GetOrderByOrderIdReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_get_order_list_req import GetOrderListReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_add_order_req import AddOrderReqBuilder
from kucoin_universal_sdk.generate.futures.positions.model_modify_margin_leverage_req import ModifyMarginLeverageReqBuilder

# NEW IMPORTS FOR STOP ORDERS
from kucoin_universal_sdk.generate.futures.order.model_get_stop_order_list_req import GetStopOrderListReqBuilder
from kucoin_universal_sdk.generate.futures.order.model_cancel_all_stop_orders_req import CancelAllStopOrdersReqBuilder

# IMPORTS FOR HISTORY
from kucoin_universal_sdk.generate.futures.order.model_get_trade_history_req import GetTradeHistoryReqBuilder
from kucoin_universal_sdk.generate.account.account.model_get_futures_ledger_req import GetFuturesLedgerReqBuilder

class KuCoinConnector:
    def __init__(self, api_key, secret, passphrase):
        self.logger = logging.getLogger("KuCoinConnector")

        transport_option = TransportOptionBuilder().build()
        options = ClientOptionBuilder()\
            .set_key(api_key)\
            .set_secret(secret)\
            .set_passphrase(passphrase)\
            .set_transport_option(transport_option)\
            .set_spot_endpoint(GLOBAL_API_ENDPOINT)\
            .set_futures_endpoint(GLOBAL_FUTURES_API_ENDPOINT)\
            .set_broker_endpoint(GLOBAL_API_ENDPOINT)\
            .build()

        try:
            self.client = DefaultClient(options)
            self.rest = self.client.rest_service()
            self.futures_svc = self.rest.get_futures_service()

            self.market_api = self.futures_svc.get_market_api()
            self.positions_api = self.futures_svc.get_positions_api()
            self.order_api = self.futures_svc.get_order_api()
            self.funding_api = self.futures_svc.get_funding_fees_api()

            self.logger.info("✅ KuCoin Futures Connected (Universal SDK)")
        except Exception as e:
            self.logger.error(f"❌ Connection Failed: {e}")

    def _to_sdk_symbol(self, symbol):
        """Converts CCXT style symbol (BTC/USDT:USDT) to SDK style (XBTUSDTM)."""
        if symbol == 'BTC/USDT:USDT': return 'XBTUSDTM'
        if symbol == 'ETH/USDT:USDT': return 'ETHUSDTM'
        try:
            base = symbol.split('/')[0]
            return f"{base}USDTM"
        except:
            return symbol

    def _to_ccxt_symbol(self, sdk_symbol):
        """Reverse mapping for returning consistent symbols to the bot."""
        if sdk_symbol == 'XBTUSDTM': return 'BTC/USDT:USDT'
        if sdk_symbol.endswith('USDTM'):
            base = sdk_symbol[:-5]
            return f"{base}/USDT:USDT"
        return sdk_symbol

    def get_ticker_price(self, symbol):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            req = GetTickerReqBuilder().set_symbol(sdk_symbol).build()
            ticker = self.market_api.get_ticker(req)
            if ticker.price:
                return float(ticker.price)
            return None
        except Exception as e:
            return None

    def get_historical_data(self, symbol, timeframe='5m', limit=100):
        sdk_symbol = self._to_sdk_symbol(symbol)
        tf_map = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
        granularity = tf_map.get(timeframe, 5)

        try:
            req = GetKlinesReqBuilder().set_symbol(sdk_symbol).set_granularity(granularity).build()
            resp = self.market_api.get_klines(req)

            data = []
            if resp.data:
                for k in resp.data:
                    ts = float(k[0])
                    op = float(k[1])
                    hi = float(k[2])
                    lo = float(k[3])
                    cl = float(k[4])
                    vo = float(k[5])
                    data.append([ts, op, hi, lo, cl, vo])

            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            if len(df) > limit:
                df = df.iloc[-limit:]

            return df
        except Exception as e:
            self.logger.error(f"❌ Klines Error {symbol}: {e}")
            return pd.DataFrame()

    def get_order_book(self, symbol, limit=20):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            req = GetPartOrderBookReqBuilder().set_symbol(sdk_symbol).set_size(str(limit)).build()
            return self.market_api.get_part_order_book(req)
        except: return None

    def get_funding_rate(self, symbol):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            req = GetCurrentFundingRateReqBuilder().set_symbol(sdk_symbol).build()
            resp = self.funding_api.get_current_funding_rate(req)
            return float(resp.value) if resp.value else 0.0
        except Exception as e:
            self.logger.error(f"⚠️ Funding Rate Error {symbol}: {e}")
            return 0.0

    def get_24h_stats(self, symbol):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            req = GetTickerReqBuilder().set_symbol(sdk_symbol).build()
            ticker = self.market_api.get_ticker(req)
            # Assuming price_change_percent is unavailable in ticker, we rely on logic
            return {'price_change_percent': 0.0}
        except Exception as e:
            self.logger.error(f"⚠️ Stats 24h Error {symbol}: {e}")
            return {'price_change_percent': 0.0}

    def _ensure_symbol_map(self):
        """Ensures symbol multipliers are cached."""
        if not hasattr(self, 'symbol_map'):
            self.symbol_map = {}
            try:
                resp = self.market_api.get_all_symbols()
                if resp.data:
                    for s in resp.data:
                        self.symbol_map[s.symbol] = float(s.multiplier)
            except Exception as e:
                self.logger.error(f"⚠️ Error caching symbols: {e}")

    def get_all_open_positions(self):
        try:
            self._ensure_symbol_map()
            req = GetPositionListReqBuilder().set_currency('USDT').build()
            resp = self.positions_api.get_position_list(req)
            results = []
            if resp.data:
                for p in resp.data:
                    qty = float(p.current_qty)
                    if qty != 0:
                        entry_price = float(p.avg_entry_price or 0)
                        leverage = float(p.real_leverage or 0)
                        pnl = float(p.unrealised_pnl or 0)
                        sdk_symbol = p.symbol
                        multiplier = self.symbol_map.get(sdk_symbol, 1.0)

                        # Calculate ROE %
                        roe_pcnt = 0
                        if entry_price > 0 and leverage > 0:
                            # Margin = (Entry Price * Lots * Multiplier) / Leverage
                            margin = (entry_price * abs(qty) * multiplier) / leverage
                            if margin > 0:
                                roe_pcnt = pnl / margin

                        results.append({
                            'symbol': self._to_ccxt_symbol(p.symbol),
                            'pnl': pnl,
                            'unrealisedPnl': pnl,
                            'unrealisedPnlPcnt': roe_pcnt,
                            'markPrice': float(getattr(p, 'mark_price', 0) or 0),
                            'side': 'long' if qty > 0 else 'short',
                            'quantity': abs(qty),
                            'entryPrice': entry_price,
                            'leverage': leverage,
                            'marginMode': p.margin_mode.value if p.margin_mode else None
                        })
            return results
        except Exception as e:
            self.logger.error(f"❌ Error fetching open positions: {e}")
            return []

    def cancel_all_orders(self, symbol):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            # Cancel Normal Orders
            req1 = CancelAllOrdersV1ReqBuilder().set_symbol(sdk_symbol).build()
            self.order_api.cancel_all_orders_v1(req1)

            # Cancel STOP Orders
            req2 = CancelAllStopOrdersReqBuilder().set_symbol(sdk_symbol).build()
            self.order_api.cancel_all_stop_orders(req2)

            self.logger.info(f"🗑️ Canceled ALL orders (Limit + Stop) for {symbol}.")
            return True
        except Exception as e:
            self.logger.info(f"⚠️ Cancel All Failed {symbol}: {e}")
            return False

    def cancel_order(self, symbol, order_id, silent=False):
        try:
            req = CancelOrderByIdReqBuilder().set_order_id(order_id).build()
            self.order_api.cancel_order_by_id(req)
            if not silent: self.logger.info(f"🗑️ Canceled order {order_id}")
            return True
        except Exception as e:
            if not silent: self.logger.info(f"⚠️ Failed to cancel {order_id}: {e}")
            return False

    def get_order_status(self, symbol, order_id):
        if not order_id: return 'missing'
        try:
            req = GetOrderByOrderIdReqBuilder().set_order_id(order_id).build()
            order = self.order_api.get_order_by_order_id(req)
            return order.status.lower()
        except:
            return 'missing'

    def get_open_orders(self, symbol):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            # 1. Normal Orders
            req_normal = GetOrderListReqBuilder().set_symbol(sdk_symbol).set_status('active').build()
            resp_normal = self.order_api.get_order_list(req_normal)

            # 2. Stop Orders
            req_stop = GetStopOrderListReqBuilder().set_symbol(sdk_symbol).build()
            resp_stop = self.order_api.get_stop_order_list(req_stop)

            orders = []

            # Process Normal
            if resp_normal.items:
                for o in resp_normal.items:
                    orders.append({
                        'id': o.id,
                        'symbol': self._to_ccxt_symbol(o.symbol),
                        'status': o.status,
                        'side': o.side,
                        'stopPrice': float(o.stop_price or 0), # Usually None for normal orders
                        'price': float(o.price or 0),
                        'info': o
                    })

            # Process Stop
            if resp_stop.items:
                 for o in resp_stop.items:
                    # Stop orders have stop_price
                    orders.append({
                        'id': o.id,
                        'symbol': self._to_ccxt_symbol(o.symbol),
                        'status': o.status,
                        'side': o.side,
                        'stopPrice': float(o.stop_price or 0),
                        'price': float(o.price or 0),
                        'info': o
                    })

            return orders
        except Exception as e:
            self.logger.error(f"❌ Error fetching open orders {symbol}: {e}")
            return []

    def place_stop_market_order(self, symbol, side, amount, stop_price, stop_dir, margin_mode=None):
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            # Use AddOrderReqBuilder.
            # KuCoin Futures Unified API uses the SAME endpoint for stop orders if `stop` param is set.
            # OR uses `add_stop_order`?
            # SDK structure has `add_order` and `add_tpsl_order`?
            # But often `add_order` handles conditional orders if `stop` property is set.
            # Reviewer said: "Verify that `place_stop_market_order` uses the correct SDK builder... often `AddStopOrderReqBuilder`"
            # Let's check if `model_add_stop_order_req.py` exists in file listing earlier.
            # List was: `model_add_order_req.py`, `model_add_tpsl_order_req.py`.
            # No `model_add_stop_order_req.py`.
            # So `AddOrderReqBuilder` with `set_stop(...)` IS likely correct for this SDK version.

            builder = AddOrderReqBuilder()\
                .set_client_oid(str(uuid.uuid4()))\
                .set_symbol(sdk_symbol)\
                .set_side(side)\
                .set_type('market')\
                .set_size(int(amount))\
                .set_stop(stop_dir)\
                .set_stop_price(str(stop_price))\
                .set_stop_price_type('TP')\
                .set_reduce_only(True)\
                .set_time_in_force('GTC')

            if margin_mode:
                builder.set_margin_mode(margin_mode)

            req = builder.build()
            resp = self.order_api.add_order(req)

            return {'id': resp.order_id}
        except Exception as e:
            self.logger.error(f"❌ Error placing STOP-MARKET {symbol}: {e}")
            return None

    def execute_trade(self, symbol, side, amount_usdt, leverage):
        """
        Esegue un ordine MARKET calcolando i lotti corretti.
        amount_usdt: Margine che vuoi investire (es. 10 USDT).
        """
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            # 1. Recupera il prezzo attuale
            price = self.get_ticker_price(symbol)
            if not price:
                self.logger.error(f"❌ Price Missing for {symbol}")
                return None

            # 2. Recupera info sul contratto (Multiplier) per calcolare i lotti
            self._ensure_symbol_map()
            multiplier = self.symbol_map.get(sdk_symbol, 1.0)

            # 3. Calcolo Size (Numero di Lotti)
            # Formula: (Margine * Leva) / (Prezzo * Multiplier)
            notional_value = amount_usdt * leverage
            contract_value = price * multiplier
            num_lots = int(notional_value / contract_value)

            if num_lots <= 0:
                self.logger.warning(f"⚠️ Order size too small for {symbol} (Lots: {num_lots}). Increase BASE_ORDER_SIZE.")
                return None

            # 4. Invia l'Ordine (MARKET)
            order_side = 'buy' if side.lower() == 'buy' else 'sell'

            req = AddOrderReqBuilder()\
                .set_client_oid(str(uuid.uuid4()))\
                .set_symbol(sdk_symbol)\
                .set_side(order_side)\
                .set_type('market')\
                .set_size(num_lots)\
                .set_leverage(int(leverage))\
                .set_margin_mode('ISOLATED')\
                .build()

            resp = self.order_api.add_order(req)
            self.logger.info(f"✅ EXEC {order_side.upper()} {symbol} | Lots: {num_lots} | Id: {resp.order_id}")
            return {'id': resp.order_id}

        except Exception as e:
            self.logger.error(f"❌ EXEC FAIL {symbol}: {e}")
            return None

    def place_market_order(self, symbol, side, size, reduce_only=True):
        """
        Piazza un ordine a mercato diretto (utile per chiusure).
        size: numero di lotti/contratti.
        """
        sdk_symbol = self._to_sdk_symbol(symbol)
        try:
            req = AddOrderReqBuilder()\
                .set_client_oid(str(uuid.uuid4()))\
                .set_symbol(sdk_symbol)\
                .set_side(side)\
                .set_type('market')\
                .set_size(int(size))\
                .set_reduce_only(reduce_only)\
                .build()

            resp = self.order_api.add_order(req)
            self.logger.info(f"✅ MARKET ORDER {side} {symbol} | Size: {size} | Id: {resp.order_id}")
            return {'id': resp.order_id}
        except Exception as e:
            self.logger.error(f"❌ MARKET ORDER FAIL {symbol}: {e}")
            return None

    def get_trade_history(self, symbol, start_at=None, limit=20):
        """
        Recupera lo storico dei fills (esecuzioni) privati.
        Include paginazione automatica per recuperare tutto.
        """
        sdk_symbol = self._to_sdk_symbol(symbol)
        results = []
        page = 1
        page_size = 50 # Max usually 50 or 100

        try:
            while True:
                builder = GetTradeHistoryReqBuilder().set_symbol(sdk_symbol)
                if start_at:
                    builder.set_start_at(int(start_at * 1000)) # ms

                builder.set_page_size(page_size)
                builder.set_current_page(page)

                req = builder.build()
                resp = self.order_api.get_trade_history(req)

                if not resp.items:
                    break

                for t in resp.items:
                    results.append({
                        'tradeId': t.trade_id,
                        'symbol': self._to_ccxt_symbol(t.symbol),
                        'side': t.side,
                        'price': float(t.price),
                        'size': float(t.size),
                        'value': float(t.value),
                        'fee': float(t.fee or 0),
                        'feeCurrency': t.fee_currency,
                        'timestamp': t.trade_time / 1000,
                        'orderId': t.order_id,
                        'tradeType': t.trade_type,
                        'liquidity': t.liquidity
                    })

                if len(resp.items) < page_size:
                    break

                page += 1
                time.sleep(0.1) # Prevent Rate Limit

            return results
        except Exception as e:
            self.logger.error(f"⚠️ Trade History Error {symbol}: {e}")
            return results

    def get_ledger_history(self, start_at=None):
        """
        Recupera il registro transazioni (Ledger) per trovare il PnL Realizzato.
        Include paginazione (offset).
        """
        results = []
        offset = 0
        limit = 50 # Max count usually 100?

        try:
            account_svc = self.client.rest_service().get_account_service()
            account_api = account_svc.get_account_api()

            while True:
                builder = GetFuturesLedgerReqBuilder().set_type('RealisedPNL')
                if start_at:
                    builder.set_start_at(int(start_at * 1000))

                builder.set_offset(offset)
                builder.set_max_count(limit)

                req = builder.build()
                resp = account_api.get_futures_ledger(req)

                if not resp.data_list:
                    break

                for l in resp.data_list:
                    results.append({
                        'timestamp': float(l.time) / 1000,
                        'amount': float(l.amount),
                        'type': l.type,
                        'currency': l.currency,
                        'remark': l.remark
                    })

                if len(resp.data_list) < limit:
                    break

                offset += limit
                time.sleep(0.1)

            return results
        except Exception as e:
            self.logger.error(f"⚠️ Ledger History Error: {e}")
            return results
