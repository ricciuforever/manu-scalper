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
        # --- 1. DATA FETCHING (Low Timeframes) ---
        # 1m per entry trigger, 5m per trend filter
        klines_1m = self.exchange.get_historical_data(symbol, '1m', limit=50)
        klines_5m = self.exchange.get_historical_data(symbol, '5m', limit=200)

        if klines_1m.empty or klines_5m.empty:
            return

        # --- 2. TREND FILTER (5m) ---
        # Usa EMA 200 su 5m per determinare il trend principale
        ema200_5m = ta.calculate_ema(klines_5m, 200)
        current_price = klines_1m['close'].iloc[-1]

        trend = "NEUTRAL"
        if current_price > ema200_5m:
            trend = "BULLISH"
        elif current_price < ema200_5m:
            trend = "BEARISH"

        # --- 3. INDICATORS (1m) ---
        rsi = ta.calculate_rsi(klines_1m, 14)
        stoch = ta.calculate_stoch_rsi(klines_1m)
        bollinger = ta.calculate_bollinger_bands(klines_1m)
        atr = ta.calculate_atr(klines_1m, 14)

        # --- 4. SCALPING LOGIC ---
        bias = "NEUTRAL"
        reason = ""
        leverage = 10 # Scalping di solito usa leva più alta, ma configurabile

        # LOGICA LONG:
        # 1. Trend Bullish (Prezzo > EMA200 5m)
        # 2. Pullback: RSI < 40 OR Stoch K < 20 (Oversold condition in trend)
        # 3. Price vicino a Lower BB (opzionale, ma aumenta winrate)
        if trend == "BULLISH":
            if (rsi < 45 and stoch['k'] < 20 and stoch['k'] > stoch['d']): # Incrocio StochRSI in oversold
                bias = "LONG"
                reason = f"Trend Bullish + StochRSI Cross Up ({stoch['k']:.2f}) + RSI {rsi:.2f}"
            elif (bollinger['percent_b'] < 0.1 and rsi < 35): # Bollinger Bounce
                bias = "LONG"
                reason = f"Trend Bullish + BB Low Bounce + RSI {rsi:.2f}"

        # LOGICA SHORT:
        # 1. Trend Bearish (Prezzo < EMA200 5m)
        # 2. Pullback: RSI > 60 OR Stoch K > 80 (Overbought condition in trend)
        if trend == "BEARISH":
            if (rsi > 55 and stoch['k'] > 80 and stoch['k'] < stoch['d']): # Incrocio StochRSI in overbought
                bias = "SHORT"
                reason = f"Trend Bearish + StochRSI Cross Down ({stoch['k']:.2f}) + RSI {rsi:.2f}"
            elif (bollinger['percent_b'] > 0.9 and rsi > 65): # Bollinger Bounce
                bias = "SHORT"
                reason = f"Trend Bearish + BB High Bounce + RSI {rsi:.2f}"

        # --- 5. VOLATILITY CHECK ---
        # Se ATR troppo basso, le fees mangiano i profitti.
        # Es. ATR deve essere almeno 0.05% del prezzo (molto basso, ma serve movimento)
        if atr < (current_price * 0.0005):
            bias = "NEUTRAL" # Mercato troppo piatto

        # Update Shared State
        if symbol not in self.shared_state: self.shared_state[symbol] = {}

        # Salva stato solo se cambia o se c'è segnale, per debug web
        self.shared_state[symbol] = {
            'bias': bias,
            'risk': 'HIGH', # Scalping è high risk
            'leverage': leverage,
            'metrics': {
                'rsi': rsi,
                'stoch_k': stoch['k'],
                'trend': trend,
                'atr': atr
            }
        }

        # Log decision only if signal
        if bias != 'NEUTRAL':
            self.db.save_signal(symbol, bias, "HIGH", leverage, reason)
            print(f"🚀 SCALP SIGNAL {symbol}: {bias} ({reason})")
            self.db.log("Strategist", f"SCALP {symbol}: {bias}. {reason}", "INFO")
