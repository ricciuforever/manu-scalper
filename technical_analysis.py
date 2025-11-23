import pandas as pd
import numpy as np

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean().iloc[-1]

def calculate_rsi(df, period=14):
    close = df['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_stoch_rsi(df, period=14, k_period=3, d_period=3):
    """
    Calcola Stochastic RSI per identificare punti di svolta precisi.
    Ritorna K e D lines.
    """
    close = df['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    min_rsi = rsi.rolling(window=period).min()
    max_rsi = rsi.rolling(window=period).max()

    stoch = ((rsi - min_rsi) / (max_rsi - min_rsi)) * 100
    k = stoch.rolling(window=k_period).mean()
    d = k.rolling(window=d_period).mean()

    return {
        'k': k.iloc[-1],
        'd': d.iloc[-1]
    }

def calculate_macd(df, fast=12, slow=26, signal=9):
    """
    Calcola MACD (Moving Average Convergence Divergence).
    Utile per identificare trend e momentum.
    """
    close = df['close']
    exp1 = close.ewm(span=fast, adjust=False).mean()
    exp2 = close.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line

    return {
        'macd': macd.iloc[-1],
        'signal': signal_line.iloc[-1],
        'hist': histogram.iloc[-1]
    }

def calculate_bollinger_bands(df, window=20, no_of_std=2):
    """
    Calcola Bollinger Bands per identificare volatilità e livelli di ipercomprato/ipervenduto.
    """
    close = df['close']
    rolling_mean = close.rolling(window=window).mean()
    rolling_std = close.rolling(window=window).std()

    upper = rolling_mean + (rolling_std * no_of_std)
    lower = rolling_mean - (rolling_std * no_of_std)

    current_price = close.iloc[-1]
    percent_b = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])

    return {
        'upper': upper.iloc[-1],
        'middle': rolling_mean.iloc[-1],
        'lower': lower.iloc[-1],
        'percent_b': percent_b # >1 = Overbought, <0 = Oversold
    }

def calculate_ema(df, span=200):
    return df['close'].ewm(span=span, adjust=False).mean().iloc[-1]

def calculate_adx(df, period=14):
    """
    Calcola ADX (Average Directional Index) per misurare la forza del trend.
    """
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high - high.shift()
    down_move = low.shift() - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    # Smoothed TR, +DM, -DM
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=1/period, adjust=False).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=1/period, adjust=False).mean()

    plus_di = 100 * (smoothed_plus_dm / atr)
    minus_di = 100 * (smoothed_minus_dm / atr)

    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()

    return adx.iloc[-1]

def calculate_order_imbalance(book, depth=10):
    """
    Calcola lo sbilanciamento semplice tra volume bid e ask.
    Ritorna ratio (Bids/Asks). >1 = Bullish, <1 = Bearish.
    Depth aumentata per analisi più ampia.
    """
    if not book: return 1.0

    try:
        # Handle both dict and object access
        bids_list = book.bids if hasattr(book, 'bids') else book.get('bids', [])
        asks_list = book.asks if hasattr(book, 'asks') else book.get('asks', [])

        if not bids_list or not asks_list: return 1.0

        bids = sum([float(b[1]) for b in bids_list[:depth]])
        asks = sum([float(a[1]) for a in asks_list[:depth]])

        return bids / asks if asks > 0 else 1.0
    except:
        return 1.0

def analyze_trend_structure(klines_4h):
    """
    Analizza la struttura del trend su timeframe alto (4h) basandosi su High/Low.
    """
    if len(klines_4h) < 10: return "NEUTRAL"

    recent = klines_4h.tail(5)

    # Logica semplificata Higher Highs / Higher Lows
    closes = recent['close'].values
    if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
        return "UPTREND"
    elif closes[-1] < closes[-2] and closes[-2] < closes[-3]:
        return "DOWNTREND"

    return "RANGING"
