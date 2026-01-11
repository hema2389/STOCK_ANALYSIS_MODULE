from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time
import pytz
import yfinance as yf
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/stockmonitor")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

IST = pytz.timezone("Asia/Kolkata")

# =========================
# DATABASE MODEL
# =========================
class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False)

    last_price = db.Column(db.Float)
    current_high = db.Column(db.Float)
    current_low = db.Column(db.Float)

    high_1030 = db.Column(db.Float)
    low_1030 = db.Column(db.Float)
    captured_1030 = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(20), default="NEUTRAL")
    last_update = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "lastPrice": self.last_price,
            "currentHigh": self.current_high,
            "currentLow": self.current_low,
            "high1030": self.high_1030,
            "low1030": self.low_1030,
            "status": self.status,
            "lastUpdate": self.last_update.isoformat() if self.last_update else None,
        }

# =========================
# HELPERS
# =========================
def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return time(9, 15) <= now.time() <= time(15, 30)

def fetch_stock_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="5m", auto_adjust=True)

        if hist.empty:
            return None

        hist.index = hist.index.tz_convert(IST)
        hist = hist.between_time("09:15", "15:30")

        return {
            "price": round(float(hist["Close"].iloc[-1]), 2),
            "high": round(float(hist["High"].max()), 2),
            "low": round(float(hist["Low"].min()), 2),
        }
    except Exception as e:
        print(symbol, e)
        return None

def capture_1030(stock):
    now = datetime.now(IST)
    if (
        now.time() >= time(10, 30)
        and not stock.captured_1030
        and stock.current_high is not None
        and stock.current_low is not None
    ):
        stock.high_1030 = stock.current_high
        stock.low_1030 = stock.current_low
        stock.captured_1030 = True

def update_status(stock):
    if not stock.high_1030 or not stock.low_1030:
        stock.status = "NEUTRAL"
        return

    if stock.last_price > stock.high_1030:
        stock.status = "GREEN"
    elif stock.last_price < stock.low_1030:
        stock.status = "RED"
    elif abs(stock.last_price - stock.high_1030) <= 5 or abs(stock.last_price - stock.low_1030) <= 5:
        stock.status = "AMBER"
    else:
        stock.status = "NEUTRAL"

# =========================
# API ROUTES
# =========================
@app.route("/api/stocks", methods=["GET"])
def get_stocks():
    return jsonify([s.to_dict() for s in Stock.query.all()])

@app.route("/api/stocks", methods=["POST"])
def add_stock():
    symbol = request.json.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "Symbol required"}), 400

    if Stock.query.filter_by(symbol=symbol).first():
        return jsonify({"error": "Stock exists"}), 400

    data = fetch_stock_data(symbol)
    if not data:
        return jsonify({"error": "Invalid symbol"}), 400

    stock = Stock(
        symbol=symbol,
        last_price=data["price"],
        current_high=data["high"],
        current_low=data["low"],
        last_update=datetime.utcnow(),
    )

    capture_1030(stock)
    update_status(stock)

    db.session.add(stock)
    db.session.commit()
    return jsonify(stock.to_dict()), 201

@app.route("/api/stocks/<symbol>", methods=["DELETE"])
def delete_stock(symbol):
    stock = Stock.query.filter_by(symbol=symbol.upper()).first()
    if not stock:
        return jsonify({"error": "Not found"}), 404

    db.session.delete(stock)
    db.session.commit()
    return jsonify({"message": "Deleted"})

@app.route("/api/stocks/update-all", methods=["POST"])
def update_all():
    if not is_market_open():
        return jsonify({"error": "Market closed"}), 400

    stocks = Stock.query.all()
    for stock in stocks:
        data = fetch_stock_data(stock.symbol)
        if not data:
            continue

        stock.last_price = data["price"]
        stock.current_high = data["high"]
        stock.current_low = data["low"]
        stock.last_update = datetime.utcnow()

        capture_1030(stock)
        update_status(stock)

    db.session.commit()
    return jsonify([s.to_dict() for s in stocks])

# =========================
# INIT
# =========================
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
