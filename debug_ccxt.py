
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

def debug_ccxt():
    exchange = ccxt.kucoinfutures({
        'apiKey': os.getenv("KUCOIN_API_KEY"),
        'secret': os.getenv("KUCOIN_SECRET"),
        'password': os.getenv("KUCOIN_PASSPHRASE"),
        'options': {'defaultType': 'future'}
    })

    print("Methods available:", [m for m in dir(exchange) if 'stop' in m.lower() and 'fetch' in m.lower()])

    # Try to fetch stop orders for a symbol if possible (e.g. BEAT/USDT:USDT from logs)
    # We might need to guess the symbol or use one from the list
    symbol = 'BEAT/USDT:USDT'

    print(f"\nAttempting to fetch normal orders for {symbol}...")
    try:
        orders = exchange.fetch_open_orders(symbol)
        print(f"Normal Orders: {len(orders)}")
    except Exception as e:
        print(f"Normal Fetch Error: {e}")

    print(f"\nAttempting to fetch STOP orders for {symbol} (param stop=True)...")
    try:
        # KuCoin usually treats stop orders separately
        stop_orders = exchange.fetch_open_orders(symbol, params={'stop': True})
        print(f"Stop Orders (via params): {len(stop_orders)}")
        if stop_orders:
            print(f"Sample Stop Order: {stop_orders[0]}")
    except Exception as e:
        print(f"Stop Param Fetch Error: {e}")

if __name__ == "__main__":
    debug_ccxt()
