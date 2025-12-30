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

    update_prices()   # 🔥 FORCE DATA ON WAKE
    print("🚀 Started")

# ---------- UPDATE (STATELESS, SLEEP SAFE) ----------
def update_prices():
    db = next(get_db())
    now = datetime.now(IST)

    for stock in db.query(Stock).all():
        try:
            df = yf.download(
                stock.symbol,
                interval="1m",
                period="1d",
                progress=False,
                threads=False
            )

            if df.empty:
                continue

            df.index = df.index.tz_localize("UTC").tz_convert(IST)

            # all data till now
            live_df = df[df.index.time <= now.time()]
            if live_df.empty:
                continue

            last_price = round(float(live_df["Close"].iloc[-1]), 2)
            cur_high = round(float(live_df["High"].max()), 2)
            cur_low = round(float(live_df["Low"].min()), 2)

            stock.last_price = last_price
            stock.current_high = cur_high
            stock.current_low = cur_low

            # 10:30 levels (RECOMPUTED ALWAYS)
            ref = live_df.between_time("09:15", "10:30")
            stock.high_1030 = round(ref["High"].max(), 2) if not ref.empty else None
            stock.low_1030 = round(ref["Low"].min(), 2) if not ref.empty else None

            # STATUS (DERIVED)
            if stock.high_1030 and stock.low_1030:
                H, L, P = stock.high_1030, stock.low_1030, last_price
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
            else:
                stock.status = "NEUTRAL"

            # EOD SNAPSHOT
            if now.time() > MARKET_CLOSE:
                stock.eod_price = last_price
                stock.eod_high = cur_high
                stock.eod_low = cur_low
                stock.eod_date = date.today()
                stock.status = "MARKET_CLOSED"

        except Exception as e:
            print("ERROR:", stock.symbol, e)

    db.commit()

# ---------- SCHEDULER ----------
scheduler = BackgroundScheduler(timezone=IST)
scheduler.add_job(update_prices, "interval", seconds=30)
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
    update_prices()
    return {"msg": "added"}

@app.get("/status")
def status():
    return {"ok": True}
