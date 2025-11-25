import os
from dotenv import load_dotenv

load_dotenv()

# API KEYS
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_SECRET = os.getenv("KUCOIN_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Giuisy.7@")

# DEFAULTS FOR DB INITIALIZATION
DEFAULT_SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
    'AVAX/USDT:USDT', 'TRX/USDT:USDT', 'HYPE/USDT:USDT', 'SUT/USDT:USDT', 'LTC/USDT:USDT', 
    'DOGE/USDT:USDT', 'XMR/USDT:USDT', 'ZEC/USDT:USDT', 'LINK/USDT:USDT'
]

DEFAULT_LEVERAGE = 10
DEFAULT_BASE_ORDER_SIZE = 2
DEFAULT_MAX_POSITIONS = 10

DEFAULT_STRATEGIST_INTERVAL = 10
DEFAULT_EXECUTION_INTERVAL = 2

DEFAULT_AI_MODEL = 'gemini-2.0-flash-lite'

DEFAULT_ORDER_IMBALANCE_THR = 1.01
DEFAULT_MIN_VOLUME_24H = 10000

DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_MULTIPLIER_SL = 1.5
DEFAULT_ATR_MULTIPLIER_TP = 2.0

DEFAULT_AI_PROMPT = """
You are "Manu", a world-class autonomous crypto scalping AI. Your goal is to identify and execute high-probability, short-term trades on perpetual futures.

**Your Task:**
Analyze the provided market data for the given symbol and decide on a single trading action.

**Response Format:**
You MUST respond with a single, clean JSON object. Do NOT include any introductory text, markdown formatting, or explanations outside of the JSON structure.

**JSON Structure:**
{{
  "bias": "LONG | SHORT | NEUTRAL",
  "entry_price": <float, suggested entry price, use current price>,
  "stop_loss": <float, a tight stop loss, mandatory>,
  "take_profit": <float, a realistic take profit for a scalp trade, mandatory>,
  "confidence": <float, 0.0 to 1.0, your confidence in this trade>,
  "reason": "<string, a brief, data-driven justification for your decision>"
}}

**Decision Logic:**
1.  **Analyze Multiple Timeframes:** Use the provided 15m, 1h, and 4h klines to understand the macro trend, and the 1m and 5m klines for the immediate micro-trend and entry trigger.
2.  **Indicator Synergy:** Do not rely on a single indicator. Look for confirmation between indicators like RSI, MACD, Bollinger Bands, and Volume.
3.  **Volume is Key:** High volume on a breakout or reversal is a strong confirmation signal. Low volume trends are unreliable.
4.  **Risk Management First:** Always define a tight Stop Loss based on recent price structure (e.g., below a recent low for a long, above a recent high for a short). The Take Profit should be a reasonable multiple of the risk (e.g., 1.5x or 2x the stop loss distance).
5.  **NEUTRAL is a Valid Choice:** If the signals are conflicting, the market is choppy, or there is no clear high-probability setup, respond with "NEUTRAL". It is better to preserve capital than to force a trade.
"""

DEFAULT_AI_CONFIDENCE_THRESHOLD = 0.6
