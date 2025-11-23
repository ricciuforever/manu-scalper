from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import sqlite3
import json
import time
from datetime import datetime, timedelta
from werkzeug.serving import WSGIRequestHandler
from db_manager import DatabaseManager
import config
from connector_kucoin import KuCoinConnector
from flask_basicauth import BasicAuth

app = Flask(__name__)
app.secret_key = 'super_secret_manu_key'  # In produzione andrebbe in .env

# Basic Auth Configuration
app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = 'Giuisy.7@'
app.config['BASIC_AUTH_FORCE'] = False # We will protect specific routes manually or via decorator

basic_auth = BasicAuth(app)

db = DatabaseManager()

# Initialize Connector for History Benchmarking (Cached if possible or fresh)
def get_exchange():
    try:
        return KuCoinConnector(config.KUCOIN_API_KEY, config.KUCOIN_SECRET, config.KUCOIN_PASSPHRASE)
    except:
        return None

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/settings', methods=['GET', 'POST'])
@basic_auth.required
def settings():
    if request.method == 'POST':
        # Salvataggio impostazioni
        try:
            # Gestione Symbols (JSON list)
            symbols_str = request.form.get('symbols')
            symbols_list = json.loads(symbols_str)
            db.set_setting('SYMBOLS', symbols_list)

            # Gestione parametri numerici
            settings_map = {
                'LEVERAGE': int,
                'BASE_ORDER_SIZE': float,
                'MAX_POSITIONS': int,
                'STRATEGIST_INTERVAL': int,
                'EXECUTION_INTERVAL': int
            }

            for key, type_func in settings_map.items():
                val = request.form.get(key)
                if val is not None:
                    db.set_setting(key, type_func(val))

            flash('Impostazioni salvate con successo!', 'success')
        except Exception as e:
            flash(f'Errore nel salvataggio: {str(e)}', 'danger')

        return redirect(url_for('settings'))

    # Recupero impostazioni attuali
    current_settings = {
        'SYMBOLS': json.dumps(db.get_setting('SYMBOLS', []), indent=2),
        'LEVERAGE': db.get_setting('LEVERAGE', 10),
        'BASE_ORDER_SIZE': db.get_setting('BASE_ORDER_SIZE', 20),
        'MAX_POSITIONS': db.get_setting('MAX_POSITIONS', 3),
        'STRATEGIST_INTERVAL': db.get_setting('STRATEGIST_INTERVAL', 10),
        'EXECUTION_INTERVAL': db.get_setting('EXECUTION_INTERVAL', 2)
    }
    return render_template('settings.html', settings=current_settings)

@app.route('/api/stats')
def api_stats():
    # Recupera dati per la dashboard in tempo reale
    open_positions = db.get_state('open_positions') or []

    # Calcolo PnL Unrealized Totale
    total_unrealized = sum([p.get('unrealisedPnl', 0) for p in open_positions])

    # Recupera Trades Recenti
    # Recupera Trades Recenti (History Fills)
    # Preferiamo mostrare gli ultimi fills reali invece della tabella 'trades' interna che è incompleta
    history_fills = db.get_history_fills(limit=10)

    # Calcola PnL Realizzato Totale (Sessione odierna UTC)
    # Start of day UTC timestamp
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    start_ts = start_of_day.timestamp()

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM history_ledger WHERE timestamp >= ? AND type = 'RealisedPNL'", (start_ts,))
    row = cursor.fetchone()
    realized_pnl = row[0] if row and row[0] is not None else 0.0
    conn.close()

    # Bot Status
    bot_state = db.get_state('main_loop')
    import time
    is_online = (time.time() - bot_state.get('timestamp', 0)) < 120

    return jsonify({
        'status': 'ONLINE' if is_online else 'OFFLINE',
        'active_positions_count': len(open_positions),
        'total_unrealized_pnl': total_unrealized,
        'total_realized_pnl': realized_pnl,
        'positions': open_positions,
        'recent_trades': history_fills # Now returning fills structure
    })

@app.route('/api/history')
def api_history():
    days = int(request.args.get('days', 30))

    # 1. Fetch Executions (Fills) for the Table
    fills = db.get_history_fills(limit=200, days=days)

    # 2. Fetch Ledger PnL for Stats & Equity Curve
    ledger_entries = db.get_history_ledger(days=days)
    pnl_entries = [l for l in ledger_entries if l['type'] == 'RealisedPNL']

    equity_curve = []
    cumulative_pnl = 0
    win_count = 0
    total_closed = 0

    if not pnl_entries:
        equity_curve.append({'timestamp': time.time(), 'equity': 0})
    else:
        # Sort by timestamp (asc)
        pnl_entries.sort(key=lambda x: x['timestamp'])

        # Add start point
        equity_curve.append({'timestamp': pnl_entries[0]['timestamp'] - 1, 'equity': 0})

        for entry in pnl_entries:
            pnl = entry['amount']
            cumulative_pnl += pnl

            equity_curve.append({
                'timestamp': entry['timestamp'],
                'equity': cumulative_pnl
            })

            # Stats Calculation
            # Ignore tiny dust < 0.01? Maybe not.
            total_closed += 1
            if pnl > 0: win_count += 1

    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0

    # Format fills for frontend table
    # Frontend expects: {timestamp, symbol, side, price, quantity, status='FILLED', pnl=?}
    # PnL per fill is NOT in trade history. We have to map from Ledger or leave it blank/approx.
    # For now we leave PnL blank ('-') or try to match if possible.
    # Actually, we can just omit PnL in the table for individual fills if we can't map it,
    # OR we can try to display the Fee.
    formatted_fills = []
    for f in fills:
        formatted_fills.append({
            'timestamp': f['timestamp'],
            'symbol': f['symbol'],
            'side': f['side'],
            'price': f['price'],
            'quantity': f['size'],
            'status': 'FILLED',
            'pnl': None # Hard to map 1:1 without orderId matching complex logic
        })

    # Fetch Benchmark (BTC) Data
    exchange = get_exchange()
    benchmark_curve = []

    if exchange:
        # Determine number of klines needed based on days. Default to 1 day candles.
        # If days < 2, use 1h candles? Let's stick to 1d for simplicity or 4h.
        tf = '1d'
        limit = days if days > 0 else 365 # Default 1 year if "All"
        if days == 0: limit = 365

        # Fetch BTC History
        btc_data = exchange.get_historical_data('BTC/USDT:USDT', tf, limit=limit)

        if not btc_data.empty:
            # Normalize to % change from start
            start_price = btc_data.iloc[0]['close']
            for _, row in btc_data.iterrows():
                ts = row['timestamp'] / 1000 # BTC data is usually in ms
                price = row['close']
                pct_change = ((price - start_price) / start_price) * 100
                benchmark_curve.append({'timestamp': ts, 'value': pct_change})

    return jsonify({
        'trades': formatted_fills, # Already filtered/formatted
        'equity_curve': equity_curve,
        'benchmark_curve': benchmark_curve,
        'stats': {
            'total_pnl': cumulative_pnl,
            'win_rate': win_rate,
            'total_trades': total_closed,
            'benchmark_return': benchmark_curve[-1]['value'] if benchmark_curve else 0
        }
    })

@app.route('/api/logs')
def api_logs():
    logs = db.get_recent_logs(50)
    formatted_logs = []
    for ts, module, msg, level in logs:
        formatted_logs.append({
            'timestamp': ts,
            'module': module,
            'message': msg,
            'level': level
        })
    return jsonify(formatted_logs)

class CustomRequestHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        if any(self.path.startswith(p) for p in ['/api/stats', '/api/logs']):
            return
        super().log_request(code, size)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True, request_handler=CustomRequestHandler)
