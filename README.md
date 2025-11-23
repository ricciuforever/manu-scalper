# 🤖 Manu Bot - AI Swing Trading System

Manu Bot è un sistema di trading automatizzato progettato per il mercato **Crypto Futures (KuCoin)**. Utilizza un'architettura ibrida che combina analisi tecnica classica (RSI, MACD, Bollinger Bands) con l'intelligenza artificiale (Google Gemini 2.0 Flash) per identificare opportunità di Swing Trading.

## 🚀 Caratteristiche Principali
- **Strategia Swing Trading:** Analisi Multi-Timeframe (1H/4H) per seguire il trend principale e ignorare il rumore di mercato.
- **AI Decision Making:** Gemini AI valuta il contesto di mercato (Price Action, Indicatori) per confermare i segnali.
- **Gestione Rischio Dinamica:** Stop Loss e Take Profit calcolati automaticamente in base all'ATR (Volatilità). Trailing Stop (Breakeven) automatico.
- **Interfaccia Web Flask:** Dashboard moderna e responsive per monitorare PnL, posizioni e log in tempo reale.

## 🛠️ Installazione

1. **Clona la repository**
2. **Configura le variabili d'ambiente**
   Crea un file `.env` (o modifica `config.py` se in locale) con:
   ```
   KUCOIN_API_KEY="tuo_api_key"
   KUCOIN_SECRET="tuo_secret"
   KUCOIN_PASSPHRASE="tua_passphrase"
   GEMINI_API_KEY="tua_gemini_key"
   ```
3. **Installa le dipendenze**
   ```bash
   pip install -r requirements.txt
   ```

## ▶️ Avvio

Il sistema è unificato. Per avviare sia il Bot di Trading che la Dashboard Web, esegui:

```bash
python manu.py
```

- **Dashboard:** Apri il browser su `http://localhost:5002`
- **Log:** I log del bot saranno visibili sia nel terminale che nella dashboard.

## ⚙️ Configurazione

Puoi modificare i parametri di trading direttamente dalla pagina **Configurazione** della Dashboard:
- **Symbols:** Lista degli asset da monitorare (es. `["BTC-USDT", "ETH-USDT"]`).
- **Leva:** Leva finanziaria utilizzata (Default: 5x-10x per Swing).
- **Rischio:** Dimensione ordine base in USDT.

## ⚠️ Disclaimer
Il trading di Futures comporta rischi elevati. Questo software è fornito "così com'è" senza garanzie di profitto. Usalo a tuo rischio.
