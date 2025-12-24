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
DEFAULT_SCRIPS = ["ICICIBANK.NS","VEDL.NS","RECLTD.NS",
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "SWANCORP.NS",
    "LT.NS", "SBIN.NS", "AXISBANK.NS", "BHARTIARTL.NS", "HINDUNILVR.NS"
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
        stock.current_high = None
        stock.current_low = None
        stock.status = "NEUTRAL"
        stock.trading_date = today

    db.commit()

# ---------- FETCH & UPDATE ----------
def capture_eod():
    db = next(get_db())
    today = date.today()

    for stock in db.query(Stock).all():
        if stock.eod_date == today:
            continue  # already captured

        stock.eod_price = stock.last_price
        stock.eod_high = stock.current_high
        stock.eod_low = stock.current_low
        stock.eod_date = today

    db.commit()
    
def update_prices():
    if not time(9, 15) <= now <= time(15, 30):
        return
    db = next(get_db())
    now = datetime.now(IST).time()

    for stock in db.query(Stock).all():
        ticker = yf.Ticker(stock.symbol)
        data = ticker.history(interval="1m", period="1d")

        if data.empty:
            continue

        # ---- LAST PRICE ----
        last_price = round(float(data["Close"].iloc[-1]), 2)
        stock.last_price = last_price
        # Update current high / low continuously
        if stock.current_high is None or stock.last_price > stock.current_high:
            stock.current_high = stock.last_price
        
        if stock.current_low is None or stock.last_price < stock.current_low:
            stock.current_low = stock.last_price

        # ---- CAPTURE 10:30 HIGH / LOW (ONCE) ----
        if stock.high_1030 is None and now >= time(10, 30):
            slice_1030 = data.between_time("09:15", "10:30")
            if not slice_1030.empty:
                stock.high_1030 = round(float(slice_1030["High"].max()), 2)
                stock.low_1030 = round(float(slice_1030["Low"].min()), 2)


                # initialize current high/low at 10:30
                stock.current_high = stock.high_1030
                stock.current_low = stock.low_1030

        # ---- UPDATE CURRENT HIGH / LOW (AFTER 10:30) ----
        if stock.high_1030 is not None:
            if stock.current_high is None or last_price > stock.current_high:
                stock.current_high = round(last_price, 2)

            if stock.current_low is None or last_price < stock.current_low:
                stock.current_low = round(last_price, 2)

        # ---- STATUS LOGIC ----
        if stock.high_1030 is not None and stock.low_1030 is not None:
            P = stock.last_price
            H = stock.high_1030
            L = stock.low_1030

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

    db.commit()

@app.post("/add/{symbol}")
def add_stock(symbol: str, db: Session = Depends(get_db)):
    if not symbol.endswith(".NS"):
        symbol += ".NS"

    if db.query(Stock).filter_by(symbol=symbol).first():
        return {"message": "Already exists"}

    stock = Stock(symbol=symbol)
    db.add(stock)
    db.commit()

    # ---- IMMEDIATE DATA FETCH IF AFTER 10:30 ----
    now = datetime.now(IST).time()

    if now >= time(10, 30):
        ticker = yf.Ticker(symbol)
        data = ticker.history(interval="1m", period="1d")

        if not data.empty:
            slice_1030 = data.between_time("09:15", "10:30")

            if not slice_1030.empty:
                stock.high_1030 = round(float(slice_1030["High"].max()), 2)
                stock.low_1030 = round(float(slice_1030["Low"].min()), 2)

                last_price = round(float(data["Close"].iloc[-1]), 2)
                stock.last_price = last_price
                stock.current_high = last_price
                stock.current_low = last_price

    db.commit()
    return {"message": "Added"}

    
# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler(timezone=IST)

# Reset at market open
scheduler.add_job(reset_trading_day, "cron", hour=9, minute=15)

# Update prices
scheduler.add_job(update_prices, "interval", seconds=15)

# 🔒 Freeze EOD at 3:30 PM
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

    db.add(Stock(symbol=symbol))
    db.commit()
    return {"message": "Added"}
@app.get("/status")
def status():
    return {"status": "ok"}
