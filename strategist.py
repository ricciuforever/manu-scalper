import time
import technical_analysis as ta
import pandas as pd
from manu_agent import AIAgent

class Strategist:
    def __init__(self, exchange, shared_state, db_manager):
        self.exchange = exchange
        self.shared_state = shared_state
        self.db = db_manager
        self.ai_agent = AIAgent(db_manager)

    def run(self):
        print("🤖 STRATEGIST: Online. Modalità AUTONOMOUS AI AGENT.")
        while True:
            interval = self.db.get_setting('STRATEGIST_INTERVAL', 10) # Intervallo breve per test
            try:
                self._run_ai_analysis_cycle()
            except Exception as e:
                print(f"🤖 CRITICAL STRATEGIST ERROR: {e}")
                self.db.log("Strategist", f"CRITICAL ERROR: {e}", "ERROR")

            time.sleep(interval)

    def _run_ai_analysis_cycle(self):
        symbols = self.db.get_setting('SYMBOLS', [])
        if not symbols:
             return

        self.db.update_state('strategist', {'status': 'scanning', 'symbols_count': len(symbols)})

        open_positions = self.exchange.get_all_open_positions()
        max_positions = self.db.get_setting('MAX_POSITIONS', 5)

        if len(open_positions) >= max_positions:
            self.db.update_state('strategist', {'status': 'paused', 'reason': 'max_positions_reached'})
            return

        for symbol in symbols:
            if any(p['symbol'] == symbol for p in open_positions):
                continue

            try:
                self._process_symbol_with_ai(symbol)
                time.sleep(1)
            except Exception as e:
                print(f"🤖 ERROR processing {symbol} with AI: {e}")
                self.db.log("Strategist", f"AI Error {symbol}: {e}", "ERROR")

    def _process_symbol_with_ai(self, symbol):
        print(f"🧠 Analysing {symbol} with Autonomous Agent...")

        timeframes = ['1m', '5m', '15m', '1h', '4h']
        market_data = {
            "symbol": symbol,
            "current_price": self.exchange.get_ticker_price(symbol),
            "klines": {},
            "indicators": {}
        }

        all_klines_valid = True
        for tf in timeframes:
            klines = self.exchange.get_historical_data(symbol, tf, limit=200)
            if klines.empty:
                all_klines_valid = False
                break
            market_data["klines"][tf] = {"close": klines['close'].tolist()[-5:]}
            market_data["indicators"][tf] = {"rsi": ta.calculate_rsi(klines)}

        if not all_klines_valid:
            print(f"Skipping {symbol} due to incomplete kline data.")
            return

        ai_decision = self.ai_agent.get_trade_decision(symbol, market_data)

        if not ai_decision or 'bias' not in ai_decision:
            print(f"AI returned invalid or no decision for {symbol}.")
            return

        bias = ai_decision.get('bias', 'NEUTRAL')

        if symbol not in self.shared_state: self.shared_state[symbol] = {}
        self.shared_state[symbol] = ai_decision

        if bias != 'NEUTRAL':
            reason = ai_decision.get('reason', 'N/A')
            confidence = ai_decision.get('confidence', 0)
            leverage = self.db.get_setting('LEVERAGE', 10)
            print(f"💡 AI SIGNAL for {symbol}: {bias} (Confidence: {confidence:.2f}) - {reason}")
            self.db.save_signal(symbol, bias, f"AI-{confidence:.2f}", leverage, reason)
