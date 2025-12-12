import os
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import pytz
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
STOCKS = os.getenv("STOCKS", "").split(",")  # NOT USED ANYMORE (dynamic)
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
INDIA = pytz.timezone("Asia/Kolkata")

FETCH_HOUR = int(os.getenv("FETCH_HOUR", "10"))
FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "30"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "4"))

state = {}   # dynamic stock dictionary


# ---------------------------------------------------------
# Persistence
# ---------------------------------------------------------
def load_persist():
    global state
    try:
        if os.path.exists(PERSIST_FILE):
            with open(PERSIST_FILE, "r") as f:
                state = json.load(f)
            print("Loaded persist:", state)
        else:
            state = {}
    except Exception as e:
        print("Error loading persist:", e)


def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Error saving persist:", e)


# ---------------------------------------------------------
# Fetch Intraday High/Low at 10:30
# ---------------------------------------------------------
def fetch_high_low_for_stock(ticker):
    try:
        df = yf.download(
            tickers=ticker,
            period="1d",
            interval="1m",
            progress=False
        )
        if df is None or df.empty:
            return None

        return {
            "high": float(df["High"].max()),
            "low": float(df["Low"].min())
        }

    except Exception as e:
        print(f"HL fetch error for {ticker}: {e}")
        return None


# ---------------------------------------------------------
# Update Current High/Low continuously
# ---------------------------------------------------------
def update_current_high_low(ticker, latest_price):
    if state[ticker].get("current_high") is None:
        state[ticker]["current_high"] = latest_price
        state[ticker]["current_low"] = latest_price
        return

    if latest_price > state[ticker]["current_high"]:
        state[ticker]["current_high"] = latest_price

    if latest_price < state[ticker]["current_low"]:
        state[ticker]["current_low"] = latest_price


# ---------------------------------------------------------
# Scheduled HL Fetch at 10:30
# ---------------------------------------------------------
async def scheduled_fetch():
    while True:
        now = datetime.now(INDIA)

        if now.hour == FETCH_HOUR and now.minute == FETCH_MINUTE:
            print("Running 10:30 HL fetch...")

            for s in state.keys():
                hl = fetch_high_low_for_stock(s)
                if hl:
                    state[s]["high"] = hl["high"]
                    state[s]["low"] = hl["low"]
                    state[s]["status"] = "RED"
                    state[s]["trigger_time"] = None
                    state[s]["trigger_price"] = None

            save_persist()
            await asyncio.sleep(65)

        await asyncio.sleep(5)


# ---------------------------------------------------------
# Live Monitor Prices
# ---------------------------------------------------------
async def monitor_prices():
    while True:
        for s in list(state.keys()):
            try:
                ticker = yf.Ticker(s)
                hist = ticker.history(period="1d", interval="1m")

                # No new data (market closed)
                if hist is None or hist.empty:
                    state[s]["last_price"] = state[s].get("last_price", "N/A")
                    state[s]["last_checked"] = datetime.now(INDIA).isoformat()
                    continue

                latest = float(hist["Close"].iloc[-1])
                state[s]["last_price"] = latest
                state[s]["last_checked"] = datetime.now(INDIA).isoformat()

                # Update dynamic high/low
                update_current_high_low(s, latest)

                hi = state[s].get("high")
                lo = state[s].get("low")
                prev_status = state[s].get("status", "UNKNOWN")

                # If 10:30 levels not fetched yet
                if hi is None or lo is None:
                    state[s]["status"] = "UNKNOWN"

                else:
                    if latest > hi or latest < lo:
                        state[s]["status"] = "AMBER"
                        if prev_status != "AMBER":
                            state[s]["trigger_time"] = datetime.now(INDIA).strftime("%H:%M:%S")
                            state[s]["trigger_price"] = latest
                            save_persist()
                    else:
                        state[s]["status"] = "RED"

                if state[s]["status"] != prev_status:
                    save_persist()

            except Exception as e:
                print("Monitor error:", s, e)

        await asyncio.sleep(POLL_SECONDS)


# ---------------------------------------------------------
# Lifespan
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Backend starting...")
    load_persist()

    # Ensure structure correctness
    for s in list(state.keys()):
        stock = state[s]
        stock.setdefault("high", None)
        stock.setdefault("low", None)
        stock.setdefault("current_high", None)
        stock.setdefault("current_low", None)
        stock.setdefault("status", "UNKNOWN")
        stock.setdefault("trigger_time", None)
        stock.setdefault("trigger_price", None)
        stock.setdefault("last_price", None)
        stock.setdefault("last_checked", None)

    t1 = asyncio.create_task(scheduled_fetch())
    t2 = asyncio.create_task(monitor_prices())

    yield

    t1.cancel()
    t2.cancel()
    try:
        await t1
        await t2
    except:
        pass


# ---------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------
@app.get("/status")
def get_status():
    return {"stocks": state, "time": datetime.now(INDIA).isoformat()}


@app.post("/add_stock")
async def add_stock(request: Request):
    body = await request.json()
    ticker = body.get("ticker", "").strip().upper()

    if not ticker:
        return {"ok": False, "error": "Ticker missing"}

    if ticker not in state:
        state[ticker] = {
            "high": None,
            "low": None,
            "current_high": None,
            "current_low": None,
            "status": "UNKNOWN",
            "trigger_time": None,
            "trigger_price": None,
            "last_price": None,
            "last_checked": None
        }
        save_persist()
        return {"ok": True, "msg": f"{ticker} added"}

    return {"ok": False, "error": "Ticker already exists"}


# ---------------------------------------------------------
# Local Run
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)