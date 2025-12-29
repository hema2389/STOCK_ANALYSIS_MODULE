from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from storage import Stock, get_db
from datetime import datetime, time, date
import yfinance as yf
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.middleware.cors import CORSMiddleware

IST = pytz.timezone("Asia/Kolkata")
PROXIMITY_PCT = 0.001

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

DEFAULT_SCRIPS = [
    "ICICIBANK.NS","VEDL.NS","RECLTD.NS","RELIANCE.NS",
    "TCS.NS","INFY.NS","HDFCBANK.NS","SWANCORP.NS",
    "LT.NS","SBIN.NS","AXISBANK.NS","BHARTIARTL.NS",
    "HINDUNILVR.NS"
]

app = FastAPI(title="NSE Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- STARTUP ----------
@app.on_event("startup")
def startup():
    db = next(get_db())
    for s in DEFAULT_SCRIPS:
        if not db.query(Stock).filter_by(symbol=s).first():
            db.add(Stock(symbol=s))
    db.commit()
    print("🚀 Started")

# ---------- RESET DAY ----------
def reset_trading_day():
    db = next(get_db())
    today = date.today()

    for s in db.query(Stock).all():
        s.high_1030 = None
        s.low_1030 = None
        s.last_price = None
        s.current_high = None
        s.current_low = None
        s.status = "NEUTRAL"
        s.trading_date = today

    db.commit()
    print("🔄 New trading day")

# ---------- EOD FREEZE ----------
def capture_eod():
    db = next(get_db())
    today = date.today()

    for s in db.query(Stock).all():
        if s.eod_date == today:
            continue

        s.eod_price = s.last_price
        s.eod_high = s.current_high
        s.eod_low = s.current_low
        s.eod_date = today
        s.status = "MARKET_CLOSED"

    db.commit()
    print("🔒 EOD Captured")

# ---------- UPDATE ----------
def update_prices():
    now = datetime.now(IST).time()
    today = date.today()

    if date.today().weekday() >= 5:
        return

    db = next(get_db())
    symbols = [s.symbol for s in db.query(Stock).all()]

    if not symbols:
        return

    data = yf.download(
        symbols,
        interval="1m",
        period="1d",
        group_by="ticker",
        threads=True
    )

    for stock in db.query(Stock).all():

        # If market closed → keep EOD values
        # -------- MARKET CLOSED BOOTSTRAP --------
        if now > MARKET_CLOSE:
        
            # If EOD already captured, just show it
            if stock.eod_date == today:
                stock.last_price = stock.eod_price
                stock.current_high = stock.eod_high
                stock.current_low = stock.eod_low
                stock.status = "MARKET_CLOSED"
                continue
        
            # First run AFTER market close (deployment case)
            try:
                df = yf.download(
                    stock.symbol,
                    period="1d",
                    interval="1d"
                )
        
                if not df.empty:
                    close = round(float(df["Close"].iloc[-1]), 2)
                    high = round(float(df["High"].iloc[-1]), 2)
                    low = round(float(df["Low"].iloc[-1]), 2)
        
                    stock.last_price = close
                    stock.current_high = high
                    stock.current_low = low
        
                    stock.eod_price = close
                    stock.eod_high = high
                    stock.eod_low = low
                    stock.eod_date = today
        
                    stock.status = "MARKET_CLOSED"
        
            except Exception as e:
                print("EOD bootstrap error:", stock.symbol, e)
        
            continue


        try:
            df = data[stock.symbol] if len(symbols) > 1 else data
            if df.empty:
                continue

            df.index = df.index.tz_localize("UTC").tz_convert(IST)

            last_price = round(float(df["Close"].iloc[-1]), 2)
            stock.last_price = last_price

            stock.current_high = (
                last_price if stock.current_high is None
                else max(stock.current_high, last_price)
            )
            stock.current_low = (
                last_price if stock.current_low is None
                else min(stock.current_low, last_price)
            )

            # Capture 10:30 exactly once
            if stock.high_1030 is None and now >= time(10, 30):
                ref = df.between_time("09:15", "10:30")
                if not ref.empty:
                    stock.high_1030 = round(ref["High"].max(), 2)
                    stock.low_1030 = round(ref["Low"].min(), 2)
                    stock.current_high = stock.high_1030
                    stock.current_low = stock.low_1030

            if stock.high_1030 and stock.low_1030:
                P, H, L = stock.last_price, stock.high_1030, stock.low_1030
                if P > H:
                    stock.status = "GREEN"
                elif P < L:
                    stock.status = "RED"
                elif H*(1-PROXIMITY_PCT) <= P <= H*(1+PROXIMITY_PCT):
                    stock.status = "AMBER"
                elif L*(1-PROXIMITY_PCT) <= P <= L*(1+PROXIMITY_PCT):
                    stock.status = "PINK"
                else:
                    stock.status = "NEUTRAL"

        except Exception as e:
            print(stock.symbol, e)

    db.commit()

# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(reset_trading_day, "cron", hour=9, minute=15)
scheduler.add_job(update_prices, "interval", seconds=30)
scheduler.add_job(capture_eod, "cron", hour=15, minute=30)
scheduler.start()

# ---------- API ----------
@app.get("/stocks")
def stocks(db: Session = Depends(get_db)):
    return db.query(Stock).all()

@app.post("/add/{symbol}")
def add(symbol: str, db: Session = Depends(get_db)):
    if not symbol.endswith(".NS"):
        symbol += ".NS"
    if db.query(Stock).filter_by(symbol=symbol).first():
        return {"msg": "exists"}
    db.add(Stock(symbol=symbol))
    db.commit()
    return {"msg": "added"}

@app.get("/status")
def status():
    return {"ok": True}
