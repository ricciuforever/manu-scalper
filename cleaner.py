# cleaner.py
import os
import sys
# Aggiungi il percorso corrente al sistema per importare il connettore
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from connector_kucoin import KuCoinConnector
from config import KUCOIN_API_KEY, KUCOIN_SECRET, KUCOIN_PASSPHRASE

def cleanup_symbol(symbol):
    """Annulla tutti gli ordini aperti per un dato simbolo."""
    print(f"Tentativo di annullare tutti gli ordini residui per {symbol}...")
    try:
        # Inizializza il connettore
        exchange = KuCoinConnector(KUCOIN_API_KEY, KUCOIN_SECRET, KUCOIN_PASSPHRASE)

        # Chiama la funzione di annullamento totale
        exchange.cancel_all_orders(symbol)

        print(f"✅ Pulizia completata. Controlla l'Exchange.")
    except Exception as e:
        print(f"❌ Errore critico durante la pulizia: {e}")

if __name__ == '__main__':
    # L'asset con l'ordine residuo è TNSR
    cleanup_symbol('TNSR/USDT:USDT')