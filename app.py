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

    # Recupera Trades Recenti per PnL Realizzato
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 50")
    cols = [description[0] for description in cursor.description]
    trades = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()

    # Calcola PnL Realizzato Totale (approssimativo dallo storico)
    realized_pnl = sum([t['pnl'] for t in trades if t['pnl'] is not None])

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
        'recent_trades': trades[:10]
    })

@app.route('/api/history')
def api_history():
    days = int(request.args.get('days', 30))
    limit_ts = 0
    if days > 0:
        limit_ts = time.time() - (days * 86400)

    conn = db.get_connection()
    cursor = conn.cursor()

    # Fetch History Fills (Authoritative) instead of 'trades' (Intent)
    # We only care about fills that have PnL (realized trades) for the equity curve,
    # but maybe we want to list all fills in the table.
    query = "SELECT * FROM history_fills WHERE timestamp >= ? ORDER BY timestamp ASC"
    cursor.execute(query, (limit_ts,))
    cols = [description[0] for description in cursor.description]
    fills = [dict(zip(cols, row)) for row in cursor.fetchall()]
    conn.close()

    # Calculate Metrics based on Fills
    # Only fills with non-zero PnL are considered "Closing Trades" (Realized) in most contexts,
    # OR we need to pair them.
    # For simplicity, if PnL is recorded, it's a realized PnL event (funding fee or close).

    # Filter for table display (All fills)
    display_trades = fills

    # Filter for Stats & Equity (Realized PnL only)
    # Note: KuCoin PnL in fills might be negative for losses, positive for wins.
    # Fees are separate. Net PnL = PnL - Fee?
    # Usually 'pnl' in fill is the Realized PnL of the contract.
    pnl_events = [f for f in fills if f.get('pnl', 0) != 0 or f.get('fee', 0) > 0]

    equity_curve = []
    cumulative_pnl = 0
    win_count = 0
    loss_count = 0

    # Initialize equity curve start
    start_ts = limit_ts if limit_ts > 0 else (fills[0]['timestamp'] - 3600 if fills else time.time() - 86400)
    equity_curve.append({'timestamp': start_ts, 'equity': 0})

    for f in fills:
        # Net PnL = Realized PnL - Fee
        # Assuming 'pnl' is gross realized pnl from the trade engine
        gross_pnl = f.get('pnl', 0)
        fee = f.get('fee', 0)
        net_pnl = gross_pnl - fee

        if net_pnl != 0:
            cumulative_pnl += net_pnl
            equity_curve.append({
                'timestamp': f['timestamp'],
                'equity': cumulative_pnl
            })

            # Count Wins/Losses based on Net PnL of Closing trades (usually larger magnitude than just funding)
            # Heuristic: If abs(net_pnl) > 0.05 (filter dust/funding)
            if abs(net_pnl) > 0.05:
                if net_pnl > 0: win_count += 1
                else: loss_count += 1

    total_closed = win_count + loss_count
    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0

    # Fetch Benchmark (BTC) Data
    exchange = get_exchange()
    benchmark_curve = []
    benchmark_return = 0

    if exchange:
        tf = '1d'
        limit = days if days > 0 else 365
        if days == 0: limit = 365

        # If days is small (e.g. 1), use 1h candles for better resolution
        if days <= 2:
            tf = '1h'
            limit = days * 24

        btc_data = exchange.get_historical_data('BTC/USDT:USDT', tf, limit=limit)

        if not btc_data.empty:
            start_price = btc_data.iloc[0]['close']
            end_price = btc_data.iloc[-1]['close']
            benchmark_return = ((end_price - start_price) / start_price) * 100

            for _, row in btc_data.iterrows():
                ts = row['timestamp'] / 1000
                price = row['close']
                pct_change = ((price - start_price) / start_price) * 100
                benchmark_curve.append({'timestamp': ts, 'value': pct_change})

    return jsonify({
        'trades': display_trades[::-1], # Newest first
        'equity_curve': equity_curve,
        'benchmark_curve': benchmark_curve,
        'stats': {
            'total_pnl': cumulative_pnl,
            'win_rate': win_rate,
            'total_trades': len(display_trades),
            'benchmark_return': benchmark_return
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
