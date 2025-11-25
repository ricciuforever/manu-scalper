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
app.secret_key = 'super_secret_manu_key'

app.config['BASIC_AUTH_USERNAME'] = 'admin'
app.config['BASIC_AUTH_PASSWORD'] = config.ADMIN_PASSWORD
app.config['BASIC_AUTH_FORCE'] = False

basic_auth = BasicAuth(app)

db = DatabaseManager()

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
        try:
            symbols_str = request.form.get('symbols')
            symbols_list = json.loads(symbols_str)
            db.set_setting('SYMBOLS', symbols_list)

            settings_map = {
                'LEVERAGE': int,
                'BASE_ORDER_SIZE': float,
                'MAX_POSITIONS': int,
                'STRATEGIST_INTERVAL': int,
                'EXECUTION_INTERVAL': int,
                'AI_CONFIDENCE_THRESHOLD': float
            }

            for key, type_func in settings_map.items():
                val = request.form.get(key)
                if val is not None:
                    db.set_setting(key, type_func(val))

            ai_prompt = request.form.get('AI_PROMPT')
            if ai_prompt is not None:
                db.set_setting('AI_PROMPT', ai_prompt)

            flash('Impostazioni salvate con successo!', 'success')
        except Exception as e:
            flash(f'Errore nel salvataggio: {str(e)}', 'danger')

        return redirect(url_for('settings'))

    current_settings = {
        'SYMBOLS': json.dumps(db.get_setting('SYMBOLS', []), indent=2),
        'LEVERAGE': db.get_setting('LEVERAGE', 10),
        'BASE_ORDER_SIZE': db.get_setting('BASE_ORDER_SIZE', 20),
        'MAX_POSITIONS': db.get_setting('MAX_POSITIONS', 3),
        'STRATEGIST_INTERVAL': db.get_setting('STRATEGIST_INTERVAL', 60),
        'EXECUTION_INTERVAL': db.get_setting('EXECUTION_INTERVAL', 5),
        'AI_PROMPT': db.get_setting('AI_PROMPT', config.DEFAULT_AI_PROMPT),
        'AI_CONFIDENCE_THRESHOLD': db.get_setting('AI_CONFIDENCE_THRESHOLD', config.DEFAULT_AI_CONFIDENCE_THRESHOLD)
    }
    return render_template('settings.html', settings=current_settings)

@app.route('/api/stats')
def api_stats():
    open_positions = db.get_state('open_positions') or []
    total_unrealized = sum([p.get('unrealisedPnl', 0) for p in open_positions])
    history_fills = db.get_history_fills(limit=10)

    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    start_ts = start_of_day.timestamp()

    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM history_ledger WHERE timestamp >= ? AND type = 'RealisedPNL'", (start_ts,))
    row = cursor.fetchone()
    realized_pnl = row[0] if row and row[0] is not None else 0.0
    conn.close()

    bot_state = db.get_state('main_loop')
    is_online = (time.time() - bot_state.get('timestamp', 0)) < 120

    return jsonify({
        'status': 'ONLINE' if is_online else 'OFFLINE',
        'active_positions_count': len(open_positions),
        'total_unrealized_pnl': total_unrealized,
        'total_realized_pnl': realized_pnl,
        'positions': open_positions,
        'recent_trades': history_fills
    })

@app.route('/api/history')
def api_history():
    days = int(request.args.get('days', 30))
    fills = db.get_history_fills(limit=200, days=days)
    ledger_entries = db.get_history_ledger(days=days)
    pnl_entries = [l for l in ledger_entries if l['type'] == 'RealisedPNL']

    equity_curve = []
    cumulative_pnl = 0
    win_count = 0
    total_closed = 0

    if not pnl_entries:
        equity_curve.append({'timestamp': time.time(), 'equity': 0})
    else:
        pnl_entries.sort(key=lambda x: x['timestamp'])
        equity_curve.append({'timestamp': pnl_entries[0]['timestamp'] - 1, 'equity': 0})
        for entry in pnl_entries:
            pnl = entry['amount']
            cumulative_pnl += pnl
            equity_curve.append({'timestamp': entry['timestamp'], 'equity': cumulative_pnl})
            total_closed += 1
            if pnl > 0: win_count += 1

    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0

    formatted_fills = []
    for f in fills:
        formatted_fills.append({
            'timestamp': f['timestamp'], 'symbol': f['symbol'], 'side': f['side'],
            'price': f['price'], 'quantity': f['size'], 'status': 'FILLED', 'pnl': None
        })

    exchange = get_exchange()
    benchmark_curve = []
    if exchange:
        tf = '1d'
        limit = days if days > 0 else 365
        if days == 0: limit = 365
        btc_data = exchange.get_historical_data('BTC/USDT:USDT', tf, limit=limit)
        if not btc_data.empty:
            start_price = btc_data.iloc[0]['close']
            for _, row in btc_data.iterrows():
                ts = row['timestamp'] / 1000
                price = row['close']
                pct_change = ((price - start_price) / start_price) * 100
                benchmark_curve.append({'timestamp': ts, 'value': pct_change})

    return jsonify({
        'trades': formatted_fills,
        'equity_curve': equity_curve,
        'benchmark_curve': benchmark_curve,
        'stats': {
            'total_pnl': cumulative_pnl, 'win_rate': win_rate, 'total_trades': total_closed,
            'benchmark_return': benchmark_curve[-1]['value'] if benchmark_curve else 0
        }
    })

@app.route('/api/logs')
def api_logs():
    logs = db.get_recent_logs(50)
    formatted_logs = [{'timestamp': ts, 'module': module, 'message': msg, 'level': level} for ts, module, msg, level in logs]
    return jsonify(formatted_logs)
