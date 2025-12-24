from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from storage import Stock, get_db
from datetime import datetime, time, date
import yfinance as yf
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

# ================= CONFIG =================
IST = pytz.timezone("Asia/Kolkata")
PROXIMITY_PCT = 0.0025  # 0.25%
DEFAULT_SCRIPS = ["ICICIBANK.NS", "INFY.NS", "RELIANCE.NS"]

# =========================================

app = FastAPI(title="NSE 10:30 Monitor")

# ---------- INIT DEFAULT STOCKS ----------
@app.on_event("startup")
def init_defaults():
    db = next(get_db())
    for s in DEFAULT_SCRIPS:
        if not db.query(Stock).filter_by(symbol=s).first():
            db.add(Stock(symbol=s))
    db.commit()

# ---------- RESET AT 9:15 ----------
def reset_trading_day():
    db = next(get_db())
    today = date.today()
    for stock in db.query(Stock).all():
        stock.high_1030 = None
        stock.low_1030 = None
        stock.last_price = None
        stock.status = "NEUTRAL"
        stock.trading_date = today
    db.commit()

# ---------- FETCH & UPDATE ----------
def update_prices():
    db = next(get_db())
    now = datetime.now(IST).time()

    for stock in db.query(Stock).all():
        ticker = yf.Ticker(stock.symbol)
        data = ticker.history(interval="1m", period="1d")

        if data.empty:
            continue

        stock.last_price = float(data["Close"][-1])

        # Capture exactly ONCE after 10:30
        if stock.high_1030 is None and now >= time(10, 30):
            slice_data = data.between_time("09:15", "10:30")
            if not slice_data.empty:
                stock.high_1030 = float(slice_data["High"].max())
                stock.low_1030 = float(slice_data["Low"].min())

        # STATUS LOGIC
        if stock.high_1030 and stock.low_1030:
            P = stock.last_price
            H = stock.high_1030
            L = stock.low_1030

            if P > H:
                stock.status = "GREEN"

            elif P < L:
                stock.status = "RED"

            elif (
                H * (1 - PROXIMITY_PCT) <= P <= H * (1 + PROXIMITY_PCT)
                or
                L * (1 - PROXIMITY_PCT) <= P <= L * (1 + PROXIMITY_PCT)
            ):
                stock.status = "AMBER"

            else:
                stock.status = "NEUTRAL"

    db.commit()

# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(reset_trading_day, "cron", hour=9, minute=15)
scheduler.add_job(update_prices, "interval", seconds=60)
scheduler.start()

# ---------- API ----------
@app.get("/stocks")
def get_stocks(db: Session = Depends(get_db)):
    return db.query(Stock).all()

@app.post("/add/{symbol}")
def add_stock(symbol: str, db: Session = Depends(get_db)):
    if not symbol.endswith(".NS"):
        symbol += ".NS"

    if db.query(Stock).filter_by(symbol=symbol).first():
        return {"message": "Already exists"}

    db.add(Stock(symbol=symbol))
    db.commit()
    return {"message": "Added"}
