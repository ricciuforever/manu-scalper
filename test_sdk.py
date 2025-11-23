
import os
import logging
from dotenv import load_dotenv
from kucoin_universal_sdk.api.client import DefaultClient
from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder
from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT, GLOBAL_FUTURES_API_ENDPOINT
from kucoin_universal_sdk.generate.futures.market.model_get_ticker_req import GetTickerReqBuilder

load_dotenv()
logging.basicConfig(level=logging.INFO)

def test_sdk():
    transport_option = TransportOptionBuilder().build()
    options = ClientOptionBuilder()\
        .set_key("key")\
        .set_secret("secret")\
        .set_passphrase("pass")\
        .set_transport_option(transport_option)\
        .set_spot_endpoint(GLOBAL_API_ENDPOINT)\
        .set_futures_endpoint(GLOBAL_FUTURES_API_ENDPOINT)\
        .set_broker_endpoint(GLOBAL_API_ENDPOINT)\
        .build()

    client = DefaultClient(options)
    rest = client.rest_service()
    futures_svc = rest.get_futures_service()
    market_api = futures_svc.get_market_api()

    # Try XBTUSDTM again
    symbol = 'XBTUSDTM'
    print(f"\n--- TICKER for {symbol} ---")
    try:
        req = GetTickerReqBuilder().set_symbol(symbol).build()
        ticker = market_api.get_ticker(req)
        print(f"Ticker Price: {ticker.price}")
    except Exception as e:
        print(f"Error ticker: {e}")

if __name__ == "__main__":
    test_sdk()
