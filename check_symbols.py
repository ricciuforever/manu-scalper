
import logging
from kucoin_universal_sdk.api.client import DefaultClient
from kucoin_universal_sdk.model.client_option import ClientOptionBuilder
from kucoin_universal_sdk.model.transport_option import TransportOptionBuilder
from kucoin_universal_sdk.model.constants import GLOBAL_API_ENDPOINT, GLOBAL_FUTURES_API_ENDPOINT

logging.basicConfig(level=logging.INFO)

def check_symbols():
    transport_option = TransportOptionBuilder().build()
    options = ClientOptionBuilder()\
        .set_key("key").set_secret("secret").set_passphrase("pass")\
        .set_transport_option(transport_option)\
        .set_spot_endpoint(GLOBAL_API_ENDPOINT)\
        .set_futures_endpoint(GLOBAL_FUTURES_API_ENDPOINT)\
        .set_broker_endpoint(GLOBAL_API_ENDPOINT)\
        .build()

    client = DefaultClient(options)
    rest = client.rest_service()
    futures_svc = rest.get_futures_service()
    market_api = futures_svc.get_market_api()

    try:
        res = market_api.get_all_symbols()
        # Assume res.data is list of symbols
        # Check structure
        if hasattr(res, 'data'):
            items = res.data
            # search for USDT
            for s in items:
                if s.base_currency == 'BTC' and s.quote_currency == 'USDT':
                    print(f"Found BTC/USDT: {s.symbol} | Type: {s.type} | Multiplier: {s.multiplier}")
                if s.base_currency == 'ETH' and s.quote_currency == 'USDT':
                     print(f"Found ETH/USDT: {s.symbol}")

    except Exception as e:
        print(e)

if __name__ == "__main__":
    check_symbols()
