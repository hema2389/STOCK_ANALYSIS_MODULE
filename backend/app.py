from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import yfinance as yf
from datetime import datetime, time
import pytz
import os
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
CORS(app)

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/stockmonitor')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

IST = pytz.timezone('Asia/Kolkata')

# Database Models
class Stock(db.Model):
    __tablename__ = 'stocks'
    
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(50), unique=True, nullable=False)
    last_price = db.Column(db.Float)
    current_high = db.Column(db.Float)
    current_low = db.Column(db.Float)
    high_1030 = db.Column(db.Float)
    low_1030 = db.Column(db.Float)
    final_price = db.Column(db.Float)
    final_high = db.Column(db.Float)
    final_low = db.Column(db.Float)
    status = db.Column(db.String(20), default='NEUTRAL')
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    captured_1030 = db.Column(db.Boolean, default=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'lastPrice': self.last_price,
            'currentHigh': self.current_high,
            'currentLow': self.current_low,
            'high1030': self.high_1030,
            'low1030': self.low_1030,
            'finalPrice': self.final_price,
            'finalHigh': self.final_high,
            'finalLow': self.final_low,
            'status': self.status,
            'lastUpdate': self.last_update.isoformat() if self.last_update else None
        }

# Helper Functions
def is_market_open():
    now = datetime.now(IST)
    day = now.weekday()
    current_time = now.time()
    
    if day >= 5:  # Weekend
        return False
    
    market_open = time(9, 15)
    market_close = time(15, 30)
    
    return market_open <= current_time <= market_close

def is_past_1030():
    now = datetime.now(IST)
    return now.time() >= time(10, 30)

def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)

        hist = ticker.history(
            period='1d',
            interval='5m',   # 🔥 change here
            auto_adjust=True
        )

        if hist is None or hist.empty:
            print(f"No data for {symbol}")
            return None

        current_price = float(hist['Close'].iloc[-1])
        day_high = float(hist['High'].max())
        day_low = float(hist['Low'].min())

        return {
            'price': round(current_price, 2),
            'high': round(day_high, 2),
            'low': round(day_low, 2)
        }

    except Exception as e:
        print(f"Yahoo error {symbol}: {e}")
        return None


def update_stock_status(stock):
    """Update stock status based on 10:30 levels"""
    if not stock.high_1030 or not stock.low_1030:
        return
    
    price = stock.last_price
    high = stock.high_1030
    low = stock.low_1030
    
    if price < low:
        stock.status = 'RED'
    elif price > high:
        stock.status = 'GREEN'
    elif abs(price - high) <= 5 or abs(price - low) <= 5:
        stock.status = 'AMBER'
    else:
        stock.status = 'NEUTRAL'

def update_all_stocks():
    """Background job to update all stocks"""
    if not is_market_open():
        return
    
    with app.app_context():
        stocks = Stock.query.all()
        
        for stock in stocks:
            data = fetch_stock_data(stock.symbol)
            
            if data:
                stock.last_price = data['price']
                stock.current_high = max(stock.current_high or data['high'], data['high'])
                stock.current_low = min(stock.current_low or data['low'], data['low'])
                stock.last_update = datetime.utcnow()
                
                # Capture 10:30 levels
                if is_past_1030() and not stock.captured_1030:
                    stock.high_1030 = stock.current_high
                    stock.low_1030 = stock.current_low
                    stock.captured_1030 = True
                
                update_stock_status(stock)
        
        db.session.commit()
        print(f"Updated {len(stocks)} stocks at {datetime.now(IST)}")

def save_final_prices():
    """Save final prices at market close"""
    with app.app_context():
        stocks = Stock.query.all()
        
        for stock in stocks:
            stock.final_price = stock.last_price
            stock.final_high = stock.current_high
            stock.final_low = stock.current_low
        
        db.session.commit()
        print(f"Saved final prices at {datetime.now(IST)}")

def reset_daily_data():
    """Reset daily data at market open"""
    with app.app_context():
        stocks = Stock.query.all()
        
        for stock in stocks:
            stock.current_high = None
            stock.current_low = None
            stock.high_1030 = None
            stock.low_1030 = None
            stock.captured_1030 = False
            stock.status = 'NEUTRAL'
        
        db.session.commit()
        print(f"Reset daily data at {datetime.now(IST)}")

# API Routes
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'time': datetime.now(IST).isoformat()})

@app.route('/api/market-status', methods=['GET'])
def market_status():
    return jsonify({
        'is_open': is_market_open(),
        'current_time': datetime.now(IST).isoformat()
    })

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    stocks = Stock.query.all()
    return jsonify([stock.to_dict() for stock in stocks])

@app.route('/api/stocks/<symbol>', methods=['GET'])
def get_stock(symbol):
    stock = Stock.query.filter_by(symbol=symbol.upper()).first()
    
    if not stock:
        return jsonify({'error': 'Stock not found'}), 404
    
    return jsonify(stock.to_dict())

@app.route('/api/stocks', methods=['POST'])
def add_stock():
    data = request.json
    symbol = data.get('symbol', '').upper()
    
    if not symbol:
        return jsonify({'error': 'Symbol required'}), 400
    
    # Check if stock already exists
    existing = Stock.query.filter_by(symbol=symbol).first()
    if existing:
        return jsonify({'error': 'Stock already exists'}), 400
    
    # Fetch initial data
    stock_data = fetch_stock_data(symbol)
    
    if not stock_data:
        return jsonify({'error': 'Invalid symbol or unable to fetch data'}), 400
    
    # Create new stock
    stock = Stock(
        symbol=symbol,
        last_price=stock_data['price'],
        current_high=stock_data['high'],
        current_low=stock_data['low'],
        status='NEUTRAL'
    )
    
    # If past 10:30, capture levels immediately
    if is_past_1030():
        stock.high_1030 = stock_data['high']
        stock.low_1030 = stock_data['low']
        stock.captured_1030 = True
        update_stock_status(stock)
    
    db.session.add(stock)
    db.session.commit()
    
    return jsonify(stock.to_dict()), 201

@app.route('/api/stocks/<symbol>', methods=['DELETE'])
def delete_stock(symbol):
    stock = Stock.query.filter_by(symbol=symbol.upper()).first()
    
    if not stock:
        return jsonify({'error': 'Stock not found'}), 404
    
    db.session.delete(stock)
    db.session.commit()
    
    return jsonify({'message': 'Stock deleted'}), 200

@app.route('/api/stocks/<symbol>/update', methods=['POST'])
def update_stock(symbol):
    stock = Stock.query.filter_by(symbol=symbol.upper()).first()
    
    if not stock:
        return jsonify({'error': 'Stock not found'}), 404
    
    stock_data = fetch_stock_data(symbol)
    
    if not stock_data:
        return jsonify({'error': 'Unable to fetch data'}), 400
    
    stock.last_price = stock_data['price']
    stock.current_high = max(stock.current_high or stock_data['high'], stock_data['high'])
    stock.current_low = min(stock.current_low or stock_data['low'], stock_data['low'])
    stock.last_update = datetime.utcnow()
    
    # Capture 10:30 levels
    if is_past_1030() and not stock.captured_1030:
        stock.high_1030 = stock.current_high
        stock.low_1030 = stock.current_low
        stock.captured_1030 = True
    
    update_stock_status(stock)
    
    db.session.commit()
    
    return jsonify(stock.to_dict())

@app.route('/api/stocks/update-all', methods=['POST'])
def update_all():
    if not is_market_open():
        return jsonify({'error': 'Market is closed'}), 400
    
    update_all_stocks()
    stocks = Stock.query.all()
    
    return jsonify([stock.to_dict() for stock in stocks])

# Initialize database and scheduler
with app.app_context():
    db.create_all()
    print("Database initialized")

# Background scheduler for automatic updates
scheduler = BackgroundScheduler()
scheduler.add_job(func=update_all_stocks, trigger="interval", seconds=30)
scheduler.add_job(func=save_final_prices, trigger="cron", hour=15, minute=35, timezone=IST)
scheduler.add_job(func=reset_daily_data, trigger="cron", hour=9, minute=10, timezone=IST)
scheduler.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
