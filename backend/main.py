import os
import json
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import pytz
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
STOCKS = os.getenv("STOCKS", "RELIANCE.NS,SBIN.NS").split(",")
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
INDIA = pytz.timezone("Asia/Kolkata")

FETCH_HOUR = int(os.getenv("FETCH_HOUR", "10"))
FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "30"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "4"))

state = {}   # dynamic live state


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
    except Exception as e:
        print("Error loading persist:", e)


def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Error saving persist:", e)


# ---------------------------------------------------------
# Fetch High/Low (proper)
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
# SCHEDULED HL FETCH AT 10:30
# ---------------------------------------------------------
async def scheduled_fetch():
    while True:
        now = datetime.now(INDIA)

        if now.hour == FETCH_HOUR and now.minute == FETCH_MINUTE:
            print("Running 10:30 scheduled HL fetch...")

            for s in STOCKS:
                hl = fetch_high_low_for_stock(s)
                if hl:
                    state[s]["high"] = hl["high"]
                    state[s]["low"] = hl["low"]
                    state[s]["status"] = "RED"
                    state[s]["trigger_time"] = None
                    state[s]["trigger_price"] = None
                    state[s]["last_update"] = now.isoformat()

            save_persist()
            await asyncio.sleep(61)   # prevent double-trigger

        await asyncio.sleep(5)


# ---------------------------------------------------------
# LIVE MONITOR (ALWAYS RETURNS PRICE)
# ---------------------------------------------------------
async def monitor_prices():
    while True:

        for s in list(state.keys()):

            try:
                ticker = yf.Ticker(s)
                hist = ticker.history(period="1d", interval="1m")

                # --- MARKET CLOSED / NO DATA ---
                if hist is None or hist.empty:
                    state[s]["last_price"] = state[s].get("last_price", "N/A")
                    state[s]["last_checked"] = datetime.now(INDIA).isoformat()
                    # Keep previous status or UNKNOWN
                    state[s]["status"] = state[s].get("status", "UNKNOWN")
                    continue

                # --- LATEST PRICE ALWAYS ---
                latest = float(hist["Close"].iloc[-1])
                state[s]["last_price"] = latest
                state[s]["last_checked"] = datetime.now(INDIA).isoformat()

                hi = state[s].get("high")
                lo = state[s].get("low")
                prev_status = state[s].get("status", "UNKNOWN")

                # --- If HL not yet taken (before 10:30) ---
                if hi is None or lo is None:
                    state[s]["status"] = "UNKNOWN"

                else:
                    # --- Check breakout ---
                    if latest > hi or latest < lo:
                        state[s]["status"] = "AMBER"

                        if prev_status != "AMBER":
                            state[s]["trigger_time"] = datetime.now(INDIA).strftime("%H:%M:%S")
                            state[s]["trigger_price"] = latest
                            save_persist()

                    else:
                        state[s]["status"] = "RED"

                # Save if status changed
                if state[s]["status"] != prev_status:
                    save_persist()

            except Exception as e:
                print("Monitor error:", s, e)

        await asyncio.sleep(POLL_SECONDS)


# ---------------------------------------------------------
# LIFESPAN (startup/shutdown tasks)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Backend starting...")
    load_persist()

    for s in STOCKS:
        if s not in state:
            state[s] = {
                "high": None,
                "low": None,
                "status": "UNKNOWN",
                "trigger_time": None,
                "trigger_price": None,
                "last_price": None,
                "last_checked": None
            }

    task1 = asyncio.create_task(scheduled_fetch())
    task2 = asyncio.create_task(monitor_prices())

    yield

    task1.cancel()
    task2.cancel()
    try:
        await task1
        await task2
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------
# APP
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
    return {
        "stocks": state,
        "time": datetime.now(INDIA).isoformat()
    }


@app.get("/status/{ticker}")
def get_single(ticker: str):
    t = ticker.strip()
    return state.get(t, {"error": "Ticker not found"})


@app.post("/force_fetch/{ticker}")
def force_fetch(ticker: str):
    hl = fetch_high_low_for_stock(ticker)
    if not hl:
        return {"ok": False, "error": "Cannot fetch"}

    now = datetime.now(INDIA)
    state[ticker] = {
        "high": hl["high"],
        "low": hl["low"],
        "status": "RED",
        "trigger_time": None,
        "trigger_price": None,
        "last_price": None,
        "last_checked": now.isoformat()
    }
    save_persist()
    return {"ok": True, "data": state[ticker]}


# ---------------------------------------------------------
# UVICORN (local)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))