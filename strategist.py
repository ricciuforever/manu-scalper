import time
import json
import google.generativeai as genai
import technical_analysis as ta
from config import GEMINI_API_KEY
import pandas as pd

class Strategist:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        genai.configure(api_key=GEMINI_API_KEY)

        # Load initial model
        model_name = self.db.get_setting('AI_MODEL', 'gemini-2.0-flash-lite')
        self.model = genai.GenerativeModel(model_name)

    def run(self):
        print("🧠 STRATEGIST: Online. Modalità SWING TRADING.")
        while True:
            interval = self.db.get_setting('STRATEGIST_INTERVAL', 60)
            try:
                self._run_analysis_cycle()
            except Exception as e:
                print(f"🧠 CRITICAL STRATEGIST ERROR: {e}")
                self.db.log("Strategist", f"CRITICAL ERROR: {e}", "ERROR")

            print(f"💤 Strategist sleeping for {interval}s...")
            time.sleep(interval)

    def _run_analysis_cycle(self):
        symbols = self.db.get_setting('SYMBOLS', [])
        if not symbols:
             print("⚠️ Nessun simbolo configurato.")
             return

        # Update DB state
        self.db.update_state('strategist', {'status': 'scanning', 'symbols_count': len(symbols)})

        open_positions = self.exchange.get_all_open_positions()
        max_positions = self.db.get_setting('MAX_POSITIONS', 3)

        # Swing Trading: Non forzare entrate se siamo già esposti
        if len(open_positions) >= max_positions:
            print(f"💤 STRATEGIST PAUSED: Max Positions Raggiunto ({len(open_positions)}/{max_positions}). Gestione attiva.")
            self.db.update_state('strategist', {'status': 'paused', 'reason': 'max_positions_reached'})
            return

        print(f"🌍 STRATEGIST: Analisi di {len(symbols)} asset per opportunità Swing...")

        for symbol in symbols:
            # Salta se abbiamo già una posizione su questo simbolo
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            try:
                self._process_asset_for_swing(symbol)
                time.sleep(2) # Rispetto rate limit AI e Exchange
            except Exception as e:
                print(f"🧠 ERROR {symbol}: {e}")
                self.db.log("Strategist", f"AI Error {symbol}: {e}", "ERROR")

    def _process_asset_for_swing(self, symbol):

        # 1. Dati Multi-Timeframe
        # 1h per segnale entry, 4h per trend di fondo
        klines_1h = self.exchange.get_historical_data(symbol, '1h', limit=50)
        klines_4h = self.exchange.get_historical_data(symbol, '4h', limit=20)

        if klines_1h.empty or klines_4h.empty:
            return

        # 2. Indicatori Tecnici (1h)
        current_price = klines_1h['close'].iloc[-1]
        rsi = ta.calculate_rsi(klines_1h, 14)
        macd = ta.calculate_macd(klines_1h)
        bollinger = ta.calculate_bollinger_bands(klines_1h)
        trend_4h = ta.analyze_trend_structure(klines_4h)

        # Formattiamo la Price Action (ultime 5 candele 1h)
        price_history = []
        for i in range(max(0, len(klines_1h) - 5), len(klines_1h)):
            row = klines_1h.iloc[i]
            ts = pd.to_datetime(row['timestamp'], unit='ms').strftime('%H:%M')
            price_history.append(f"{ts}: O={row['open']}, H={row['high']}, L={row['low']}, C={row['close']}")
        price_history_str = "\n".join(price_history)

        # 3. Prompt AI - Swing Oriented
        prompt = f"""
        Sei un Trader Professionista specializzato in Swing Trading Intraday.
        Analizza i dati seguenti per {symbol} e decidi se aprire una posizione.
        Sii PAZIENTE. Cerca conferme, non rumore.

        DATI DI MERCATO:
        - Prezzo Attuale: {current_price}
        - Trend di Fondo (4H): {trend_4h} (Se Ranging, sii cauto. Se Trend, segui la direzione).

        INDICATORI TECNICI (1H):
        - RSI (14): {rsi:.2f} (Overbought > 70, Oversold < 30, ma in trend forte può restare estremo).
        - MACD: Line={macd['macd']:.4f}, Signal={macd['signal']:.4f}, Hist={macd['hist']:.4f} (Cerca incroci o divergenze).
        - Bollinger: %B={bollinger['percent_b']:.2f} (Vicino a 0 = Supporto, Vicino a 1 = Resistenza).

        PRICE ACTION RECENTE (1H):
        {price_history_str}

        OBIETTIVO:
        Catturare un movimento direzionale significativo, non pochi pip.
        Evita entrate se il mercato è piatto (Ranging senza chiari segnali dai bordi delle Bollinger).

        OUTPUT RICHIESTO (JSON):
        {{"bias": "LONG"|"SHORT"|"NEUTRAL", "risk": "LOW"|"MEDIUM"|"HIGH", "leverage": 5, "reason": "Spiegazione concisa"}}
        """

        try:
            # Reload model setting
            current_model_name = self.db.get_setting('AI_MODEL', 'gemini-2.0-flash-lite')
            # Simple logic to update instance if changed, or just init new one
            if self.model.model_name.split('/')[-1] != current_model_name:
                 self.model = genai.GenerativeModel(current_model_name)

            response = self.model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            decision = json.loads(text)

            bias = decision.get('bias', 'NEUTRAL')
            risk = decision.get('risk', 'HIGH')
            leverage = decision.get('leverage', 5) # Default conservative leverage
            reason = decision.get('reason', 'No reason provided')

            # Filtro aggiuntivo di sicurezza
            if trend_4h == "UPTREND" and bias == "SHORT":
                reason += " (WARNING: Counter-trend trade filtered)"
                bias = "NEUTRAL"
            if trend_4h == "DOWNTREND" and bias == "LONG":
                reason += " (WARNING: Counter-trend trade filtered)"
                bias = "NEUTRAL"

            # Update Shared State
            if symbol not in self.shared_state: self.shared_state[symbol] = {}
            self.shared_state[symbol] = {
                'bias': bias,
                'risk': risk,
                'leverage': leverage
            }

            # Log decision
            self.db.save_signal(symbol, bias, risk, leverage, reason)

            if bias != 'NEUTRAL':
                print(f"🚀 {symbol} SIGNAL: {bias} ({reason})")
                self.db.log("Strategist", f"SIGNAL {symbol}: {bias}. {reason}", "INFO")

        except Exception as e:
            print(f"AI Error: {e}")
