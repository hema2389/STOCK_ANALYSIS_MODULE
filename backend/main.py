import os
import json
import asyncio
from datetime import datetime, time as dt_time
from contextlib import asynccontextmanager

import pytz
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ----------------- CONFIG -----------------
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
INDIA = pytz.timezone("Asia/Kolkata")
FETCH_HOUR = 10
FETCH_MINUTE = 30
POLL_SECONDS = 5

MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

state = {}  # dynamic stock dictionary

# ----------------- PERSISTENCE -----------------
def load_persist():
    global state
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                state = json.load(f)
            print("Loaded persisted data")
        except:
            state = {}
    else:
        state = {}

def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Error saving persist:", e)

# ----------------- HELPER -----------------
def fetch_intraday(ticker):
    try:
        df = yf.download(tickers=ticker, period="1d", interval="1m", progress=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        print("Error fetching", ticker, e)
        return None

def update_current_high_low(ticker, latest_price):
    if state[ticker].get("current_high") is None:
        state[ticker]["current_high"] = latest_price
        state[ticker]["current_low"] = latest_price
        return
    if latest_price > state[ticker]["current_high"]:
        state[ticker]["current_high"] = latest_price
    if latest_price < state[ticker]["current_low"]:
        state[ticker]["current_low"] = latest_price

# ----------------- DAILY RESET -----------------
async def reset_daily():
    while True:
        now = datetime.now(INDIA)
        if now.time() >= dt_time(9,15) and now.time() < dt_time(9,16):
            for s in state.keys():
                state[s]["hl_high"] = None
                state[s]["hl_low"] = None
                state[s]["current_high"] = None
                state[s]["current_low"] = None
                state[s]["status"] = "UNKNOWN"
                state[s]["trigger_time"] = None
                state[s]["trigger_price"] = None
            save_persist()
            await asyncio.sleep(61)
        await asyncio.sleep(10)

# ----------------- SCHEDULED HL FETCH -----------------
async def scheduled_hl():
    while True:
        now = datetime.now(INDIA)
        if now.hour == FETCH_HOUR and now.minute == FETCH_MINUTE:
            for s in state.keys():
                df = fetch_intraday(s)
                if df is not None:
                    state[s]["hl_high"] = float(df["High"].max())
                    state[s]["hl_low"] = float(df["Low"].min())
                    state[s]["status"] = "RED"
                    state[s]["trigger_time"] = None
                    state[s]["trigger_price"] = None
            save_persist()
            await asyncio.sleep(61)
        await asyncio.sleep(5)

# ----------------- MONITOR LIVE -----------------
async def monitor_prices():
    while True:
        now = datetime.now(INDIA)
        market_open = MARKET_OPEN <= now.time() <= MARKET_CLOSE
        for s in list(state.keys()):
            df = fetch_intraday(s)
            if df is None or df.empty:
                continue
            latest = float(df["Close"].iloc[-1])
            state[s]["last_price"] = latest
            state[s]["last_checked"] = now.isoformat()

            # Update current day high/low only during market hours
            if market_open:
                update_current_high_low(s, latest)

            # Breakout check based on 10:30 HL
            hl_high = state[s].get("hl_high")
            hl_low = state[s].get("hl_low")
            prev_status = state[s].get("status", "UNKNOWN")
            if hl_high is not None and hl_low is not None:
                if latest > hl_high or latest < hl_low:
                    state[s]["status"] = "AMBER"
                    if prev_status != "AMBER":
                        state[s]["trigger_time"] = now.strftime("%H:%M:%S")
                        state[s]["trigger_price"] = latest
                        save_persist()
                else:
                    state[s]["status"] = "RED"

            if state[s]["status"] != prev_status:
                save_persist()
        await asyncio.sleep(POLL_SECONDS)

# ----------------- LIFESPAN -----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_persist()
    for s in list(state.keys()):
        state[s].setdefault("hl_high", None)
        state[s].setdefault("hl_low", None)
        state[s].setdefault("current_high", None)
        state[s].setdefault("current_low", None)
        state[s].setdefault("status", "UNKNOWN")
        state[s].setdefault("trigger_time", None)
        state[s].setdefault("trigger_price", None)
        state[s].setdefault("last_price", None)
        state[s].setdefault("last_checked", None)

    t1 = asyncio.create_task(scheduled_hl())
    t2 = asyncio.create_task(monitor_prices())
    t3 = asyncio.create_task(reset_daily())

    yield

    t1.cancel()
    t2.cancel()
    t3.cancel()
    try:
        await t1
        await t2
        await t3
    except:
        pass

# ----------------- FASTAPI -----------------
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ----------------- API -----------------
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
            "hl_high": None,
            "hl_low": None,
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

# ----------------- LOCAL RUN -----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)