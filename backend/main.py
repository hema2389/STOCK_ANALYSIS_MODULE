from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from storage import Stock, get_db
from datetime import datetime, time, date
import yfinance as yf
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.middleware.cors import CORSMiddleware

# ================= CONFIG =================
IST = pytz.timezone("Asia/Kolkata")
PROXIMITY_PCT = 0.001  # 0.1%

DEFAULT_SCRIPS = [
    "ICICIBANK.NS", "VEDL.NS", "RECLTD.NS",
    "RELIANCE.NS", "TCS.NS", "INFY.NS",
    "HDFCBANK.NS", "SWANCORP.NS", "LT.NS",
    "SBIN.NS", "AXISBANK.NS", "BHARTIARTL.NS",
    "HINDUNILVR.NS"
]
# =========================================

app = FastAPI(title="NSE 10:30 Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- STARTUP ----------
@app.on_event("startup")
def startup_event():
    print("🚀 App started")
    db = next(get_db())
    for s in DEFAULT_SCRIPS:
        if not db.query(Stock).filter_by(symbol=s).first():
            db.add(Stock(symbol=s))
    db.commit()

# ---------- RESET DAY ----------
def reset_trading_day():
    print("🔄 Reset trading day")
    db = next(get_db())
    today = date.today()

    for stock in db.query(Stock).all():
        stock.high_1030 = None
        stock.low_1030 = None
        stock.last_price = None
        stock.current_high = None
        stock.current_low = None
        stock.status = "NEUTRAL"
        stock.trading_date = today

    db.commit()

# ---------- FREEZE EOD ----------
def capture_eod():
    print("🔒 Capturing EOD")
    db = next(get_db())
    today = date.today()

    for stock in db.query(Stock).all():
        if stock.eod_date == today:
            continue

        stock.eod_price = stock.last_price
        stock.eod_high = stock.current_high
        stock.eod_low = stock.current_low
        stock.eod_date = today

    db.commit()

# ---------- UPDATE PRICES ----------
def update_prices():
    now = datetime.now(IST).time()

    if not time(9, 15) <= now <= time(15, 30):
        return

    db = next(get_db())

    for stock in db.query(Stock).all():
        try:
            ticker = yf.Ticker(stock.symbol)
            data = ticker.history(interval="1m", period="1d")

            if data.empty:
                continue

            last_price = round(float(data["Close"].iloc[-1]), 2)
            stock.last_price = last_price

            # Update live high/low
            stock.current_high = (
                last_price if stock.current_high is None
                else max(stock.current_high, last_price)
            )
            stock.current_low = (
                last_price if stock.current_low is None
                else min(stock.current_low, last_price)
            )

            # Capture 10:30 once
            if stock.high_1030 is None and now >= time(10, 30):
                slice_1030 = data.between_time("09:15", "10:30")
                if not slice_1030.empty:
                    stock.high_1030 = round(slice_1030["High"].max(), 2)
                    stock.low_1030 = round(slice_1030["Low"].min(), 2)
                    stock.current_high = stock.high_1030
                    stock.current_low = stock.low_1030

            # Status logic
            if stock.high_1030 and stock.low_1030:
                P, H, L = stock.last_price, stock.high_1030, stock.low_1030

                if P > H:
                    stock.status = "GREEN"
                elif P < L:
                    stock.status = "RED"
                elif H * (1 - PROXIMITY_PCT) <= P <= H * (1 + PROXIMITY_PCT):
                    stock.status = "AMBER"
                elif L * (1 - PROXIMITY_PCT) <= P <= L * (1 + PROXIMITY_PCT):
                    stock.status = "PINK"
                else:
                    stock.status = "NEUTRAL"

        except Exception as e:
            print(f"⚠️ {stock.symbol} error:", e)

    db.commit()

# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(reset_trading_day, "cron", hour=9, minute=15)
scheduler.add_job(update_prices, "interval", seconds=20)
scheduler.add_job(capture_eod, "cron", hour=15, minute=30)
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

    stock = Stock(symbol=symbol)
    db.add(stock)
    db.commit()
    return {"message": "Added"}

@app.get("/status")
def status():
    return {"status": "ok"}
