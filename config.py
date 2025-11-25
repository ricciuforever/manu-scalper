import os
from dotenv import load_dotenv

load_dotenv()

# --- API KEYS ---
KUCOIN_API_KEY = os.getenv("KUCOIN_API_KEY")
KUCOIN_SECRET = os.getenv("KUCOIN_SECRET")
KUCOIN_PASSPHRASE = os.getenv("KUCOIN_PASSPHRASE")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Giuisy.7@")

# --- DEFAULTS FOR DB INITIALIZATION ---

# General Settings
DEFAULT_SYMBOLS = ['BTC/USDT:USDT'] # Grid bot works best on a single, volatile pair
DEFAULT_LEVERAGE = 10
DEFAULT_BASE_ORDER_SIZE = 2 # This will be the size for each grid line

# Grid Bot Specific Settings
DEFAULT_GRID_RANGE_LOW = 60000
DEFAULT_GRID_RANGE_HIGH = 70000
DEFAULT_GRID_LEVELS = 10
DEFAULT_GRID_SIDE = 'NEUTRAL' # Can be 'LONG', 'SHORT', or 'NEUTRAL'
DEFAULT_PROFIT_PER_GRID = 0.5 # Profit per grid line in percentage (e.g., 0.5%)

# Risk Management
DEFAULT_STOP_LOSS_PRICE = 58000 # A hard stop loss price below the grid range

# Timing
DEFAULT_STRATEGIST_INTERVAL = 60 # Interval to check and maintain the grid
DEFAULT_EXECUTION_INTERVAL = 10 # Interval to check for filled orders
