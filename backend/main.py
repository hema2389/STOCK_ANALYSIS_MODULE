from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi.middleware.cors import CORSMiddleware

from storage import Stock, get_db
from updater import update_prices

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_SCRIPS = [
    "ICICIBANK.NS","VEDL.NS","RECLTD.NS","RELIANCE.NS",
    "TCS.NS","INFY.NS","HDFCBANK.NS","SWANCORP.NS",
    "LT.NS","SBIN.NS","AXISBANK.NS","BHARTIARTL.NS",
    "HINDUNILVR.NS"
]


@app.on_event("startup")
def startup():
    db = next(get_db())

    for s in DEFAULT_SCRIPS:
        if not db.query(Stock).filter_by(symbol=s).first():
            db.add(Stock(symbol=s))

    db.commit()
    update_prices(db)  # ✅ THIS MATCHES updater.py


scheduler = BackgroundScheduler()
scheduler.add_job(
    lambda: update_prices(next(get_db())),
    "interval",
    seconds=30
)
scheduler.start()


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

    update_prices(db)
    return {"msg": "added"}
