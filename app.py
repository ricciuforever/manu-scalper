from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import json
import time
from datetime import datetime
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
            # Handle Symbols (now a single symbol for grid bot)
            symbol_str = request.form.get('symbol')
            if symbol_str:
                db.set_setting('SYMBOLS', [symbol_str])

            # Handle Grid Bot parameters
            settings_map = {
                'LEVERAGE': int,
                'BASE_ORDER_SIZE': float,
                'GRID_RANGE_LOW': float,
                'GRID_RANGE_HIGH': float,
                'GRID_LEVELS': int,
                'PROFIT_PER_GRID': float,
                'STOP_LOSS_PRICE': float,
                'STRATEGIST_INTERVAL': int,
                'EXECUTION_INTERVAL': int,
            }

            for key, type_func in settings_map.items():
                val = request.form.get(key)
                if val is not None:
                    db.set_setting(key, type_func(val))

            flash('Impostazioni salvate con successo!', 'success')
        except Exception as e:
            flash(f'Errore nel salvataggio: {str(e)}', 'danger')
        return redirect(url_for('settings'))

    # Load current settings for the form
    symbols = db.get_setting('SYMBOLS', config.DEFAULT_SYMBOLS)
    current_settings = {
        'SYMBOL': symbols[0] if symbols else '',
        'LEVERAGE': db.get_setting('LEVERAGE', config.DEFAULT_LEVERAGE),
        'BASE_ORDER_SIZE': db.get_setting('BASE_ORDER_SIZE', config.DEFAULT_BASE_ORDER_SIZE),
        'GRID_RANGE_LOW': db.get_setting('GRID_RANGE_LOW', config.DEFAULT_GRID_RANGE_LOW),
        'GRID_RANGE_HIGH': db.get_setting('GRID_RANGE_HIGH', config.DEFAULT_GRID_RANGE_HIGH),
        'GRID_LEVELS': db.get_setting('GRID_LEVELS', config.DEFAULT_GRID_LEVELS),
        'PROFIT_PER_GRID': db.get_setting('PROFIT_PER_GRID', config.DEFAULT_PROFIT_PER_GRID),
        'STOP_LOSS_PRICE': db.get_setting('STOP_LOSS_PRICE', config.DEFAULT_STOP_LOSS_PRICE),
        'STRATEGIST_INTERVAL': db.get_setting('STRATEGIST_INTERVAL', config.DEFAULT_STRATEGIST_INTERVAL),
        'EXECUTION_INTERVAL': db.get_setting('EXECUTION_INTERVAL', config.DEFAULT_EXECUTION_INTERVAL),
    }
    return render_template('settings.html', settings=current_settings)

# API endpoints remain largely the same, but might show less data
# as the grid bot logic is different. For now, we leave them as is.

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

@app.route('/api/logs')
def api_logs():
    logs = db.get_recent_logs(50)
    formatted_logs = [{'timestamp': ts, 'module': module, 'message': msg, 'level': level} for ts, module, msg, level in logs]
    return jsonify(formatted_logs)

@app.route('/api/history')
def api_history():
    # This endpoint can be simplified or adjusted for grid bot stats later
    # For now, it will continue to show PnL from the ledger.
    days = int(request.args.get('days', 30))
    fills = db.get_history_fills(limit=200, days=days)
    # ... rest of the history logic can remain for now ...
    return jsonify({'trades': fills, 'equity_curve': [], 'stats': {}})
