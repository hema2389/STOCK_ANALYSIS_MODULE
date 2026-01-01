from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

from storage import Stock, get_db
from updater import update_prices

app = FastAPI()

# ------------------ CORS ------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ DEFAULT STOCKS ------------------
DEFAULT_SCRIPS = [
    "ICICIBANK.NS","VEDL.NS","RECLTD.NS","RELIANCE.NS",
    "TCS.NS","INFY.NS","HDFCBANK.NS","SWANCORP.NS",
    "LT.NS","SBIN.NS","AXISBANK.NS","BHARTIARTL.NS",
    "HINDUNILVR.NS"
]

scheduler = BackgroundScheduler()


# ------------------ STARTUP ------------------
@app.on_event("startup")
def startup():
    # create DB session safely
    db_gen = get_db()
    db = next(db_gen)

    try:
        # insert default stocks
        for s in DEFAULT_SCRIPS:
            if not db.query(Stock).filter_by(symbol=s).first():
                db.add(Stock(symbol=s))

        db.commit()

        # initial price load
        update_prices(db)

    finally:
        db.close()

    # start scheduler AFTER app is ready
    scheduler.add_job(run_price_update, "interval", seconds=30)
    scheduler.start()


# ------------------ SHUTDOWN ------------------
@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()


# ------------------ SCHEDULER TASK ------------------
def run_price_update():
    db_gen = get_db()
    db = next(db_gen)

    try:
        update_prices(db)
    finally:
        db.close()


# ------------------ API ROUTES ------------------
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
