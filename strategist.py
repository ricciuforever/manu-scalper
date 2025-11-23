import time
import technical_analysis as ta
import pandas as pd

class Strategist:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        # Removed AI Initialization

    def run(self):
        print("⚡ STRATEGIST: Online. Modalità HIGH-FREQUENCY SCALPING.")
        while True:
            # Scalping richiede intervalli molto brevi (es. 10s)
            interval = self.db.get_setting('STRATEGIST_INTERVAL', 10)
            try:
                self._run_analysis_cycle()
            except Exception as e:
                print(f"⚡ CRITICAL STRATEGIST ERROR: {e}")
                self.db.log("Strategist", f"CRITICAL ERROR: {e}", "ERROR")

            time.sleep(interval)

    def _run_analysis_cycle(self):
        symbols = self.db.get_setting('SYMBOLS', [])
        if not symbols:
             return

        # Update DB state
        self.db.update_state('strategist', {'status': 'scanning', 'symbols_count': len(symbols)})

        open_positions = self.exchange.get_all_open_positions()
        max_positions = self.db.get_setting('MAX_POSITIONS', 5)

        if len(open_positions) >= max_positions:
            self.db.update_state('strategist', {'status': 'paused', 'reason': 'max_positions_reached'})
            return

        # print(f"⚡ STRATEGIST: Analisi Scalp...") # Ridotto log spam

        for symbol in symbols:
            # Salta se abbiamo già una posizione
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            try:
                self._process_asset_for_scalping(symbol)
                time.sleep(0.5) # Minimo delay per evitare rate limit
            except Exception as e:
                print(f"⚡ ERROR {symbol}: {e}")
                self.db.log("Strategist", f"Scalp Error {symbol}: {e}", "ERROR")

    def _process_asset_for_scalping(self, symbol):
        # --- 1. DATA FETCHING ---
        # 15m for MACRO TREND, 1m for TRIGGER
        klines_1m = self.exchange.get_historical_data(symbol, '1m', limit=200)
        klines_15m = self.exchange.get_historical_data(symbol, '15m', limit=200)

        if klines_1m.empty or klines_15m.empty:
            return

        # --- 2. MACRO TREND (15m) ---
        # Trend Filter: Price > EMA 99 (15m)
        ema99_15m = ta.calculate_ema(klines_15m, 99)
        current_price_15m = klines_15m['close'].iloc[-1]

        macro_trend = "NEUTRAL"
        if current_price_15m > ema99_15m:
            macro_trend = "BULLISH"
        elif current_price_15m < ema99_15m:
            macro_trend = "BEARISH"

        # --- 3. TRIGGER INDICATORS (1m) ---
        ema7 = ta.calculate_ema(klines_1m, 7)
        ema25 = ta.calculate_ema(klines_1m, 25)
        ema99 = ta.calculate_ema(klines_1m, 99)

        stoch = ta.calculate_stoch_rsi(klines_1m) # k, d
        current_price = klines_1m['close'].iloc[-1]

        # --- 4. SCALPING LOGIC (Trend-Scalper) ---
        bias = "NEUTRAL"
        reason = ""
        leverage = 10

        # LOGICA LONG:
        # 1. Macro Trend Bullish (15m Price > EMA 99)
        # 2. Perfect Storm (1m):
        #    - EMA Fan: EMA 7 > EMA 25 > EMA 99 (Ventaglio Aperto Up)
        #    - Pullback: StochRSI < 20 (Oversold)
        #    - Trigger: K cross D Up (K > D)
        if macro_trend == "BULLISH":
            # EMA Fan Check
            if ema7 > ema25 and ema25 > ema99:
                # Stoch Check
                if stoch['k'] < 20 and stoch['k'] > stoch['d']:
                    bias = "LONG"
                    reason = f"Macro Bull + EMA Fan Up + Stoch Cross Up ({stoch['k']:.1f})"

        # LOGICA SHORT:
        # 1. Macro Trend Bearish (15m Price < EMA 99)
        # 2. Perfect Storm (1m):
        #    - EMA Fan: EMA 7 < EMA 25 < EMA 99 (Ventaglio Aperto Down)
        #    - Pullback: StochRSI > 80 (Overbought)
        #    - Trigger: K cross D Down (K < D)
        if macro_trend == "BEARISH":
            # EMA Fan Check
            if ema7 < ema25 and ema25 < ema99:
                # Stoch Check
                if stoch['k'] > 80 and stoch['k'] < stoch['d']:
                    bias = "SHORT"
                    reason = f"Macro Bear + EMA Fan Down + Stoch Cross Down ({stoch['k']:.1f})"

        # --- 5. METRICS UPDATE ---
        if symbol not in self.shared_state: self.shared_state[symbol] = {}

        self.shared_state[symbol] = {
            'bias': bias,
            'risk': 'HIGH',
            'leverage': leverage,
            'metrics': {
                'macro_trend': macro_trend,
                'ema7': ema7,
                'ema25': ema25,
                'ema99': ema99,
                'stoch_k': stoch['k'],
                'stoch_d': stoch['d']
            }
        }

        # Log decision only if signal
        if bias != 'NEUTRAL':
            self.db.save_signal(symbol, bias, "HIGH", leverage, reason)
            print(f"🚀 SCALP SIGNAL {symbol}: {bias} ({reason})")
            self.db.log("Strategist", f"SCALP {symbol}: {bias}. {reason}", "INFO")
