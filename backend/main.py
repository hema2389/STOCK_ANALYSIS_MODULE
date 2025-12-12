import os
import json
import asyncio
from datetime import datetime, time
from contextlib import asynccontextmanager

import pytz
import yfinance as yf
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
PERSIST_FILE = "hl.json"
INDIA = pytz.timezone("Asia/Kolkata")
POLL_SECONDS = 4

# Market hours
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Dynamic stock list (no environment variable needed now)
stocks = []         # list of tickers
state = {}          # full live state per stock


# ---------------------------------------------------------
# Persistence
# ---------------------------------------------------------
def load_persist():
    global stocks, state
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                saved = json.load(f)
                stocks = saved.get("stocks", [])
                state = saved.get("state", {})
            print("Loaded persist:", saved)
        except:
            print("Persist file corrupted, starting fresh.")


def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump({"stocks": stocks, "state": state}, f)
    except Exception as e:
        print("Error saving persist:", e)


# ---------------------------------------------------------
# Market helpers
# ---------------------------------------------------------
def is_market_open():
    now = datetime.now(INDIA).time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def is_new_day_reset():
    """Reset every day at 09:15."""
    now = datetime.now(INDIA)
    return now.time() >= MARKET_OPEN and now.strftime("%H:%M") == "09:15"


# ---------------------------------------------------------
# Fetch intraday 1m for live HL
# ---------------------------------------------------------
def get_live_hl(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df is None or df.empty:
            return None

        return {
            "high": float(df["High"].max()),
            "low": float(df["Low"].min()),
            "last_price": float(df["Close"].iloc[-1])
        }

    except Exception as e:
        print("Live HL error:", ticker, e)
        return None


# ---------------------------------------------------------
# Background monitor loop
# ---------------------------------------------------------
async def monitor_loop():
    while True:

        # --- Reset at 9:15 ---
        if is_new_day_reset():
            for s in stocks:
                state[s] = {
                    "open_high": None,
                    "open_low": None,
                    "current_high": None,
                    "current_low": None,
                    "last_price": None,
                    "status": "UNKNOWN",
                    "last_update": None
                }
            save_persist()
            print("RESET 9:15 complete")

        # --- Process each stock ---
        for s in stocks:
            try:
                live = get_live_hl(s)

                if live:
                    last_price = live["last_price"]
                    ch = live["high"]
                    cl = live["low"]

                    now = datetime.now(INDIA).isoformat()

                    # If daytime
                    if is_market_open():
                        # Live high/low update
                        state[s]["current_high"] = ch
                        state[s]["current_low"] = cl

                        # After 10:30 save snapshot (`open_high`/`open_low`)
                        current_time = datetime.now(INDIA).time()
                        if current_time >= time(10, 30) and state[s]["open_high"] is None:
                            state[s]["open_high"] = ch
                            state[s]["open_low"] = cl

                    else:
                        # Market closed → use final summary
                        state[s]["current_high"] = ch
                        state[s]["current_low"] = cl

                    # Status (breakout)
                    oh = state[s]["open_high"]
                    ol = state[s]["open_low"]

                    status = "UNKNOWN"
                    if oh is not None and ol is not None:
                        if last_price > oh or last_price < ol:
                            status = "AMBER"
                        else:
                            status = "RED"

                    state[s]["status"] = status
                    state[s]["last_price"] = last_price
                    state[s]["last_update"] = now

            except Exception as e:
                print("Monitor error:", e)

        save_persist()
        await asyncio.sleep(POLL_SECONDS)


# ---------------------------------------------------------
# Lifespan (startup)
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_persist()

    # Initialize all stocks
    for s in stocks:
        state.setdefault(s, {
            "open_high": None,
            "open_low": None,
            "current_high": None,
            "current_low": None,
            "last_price": None,
            "status": "UNKNOWN",
            "last_update": None
        })

    task = asyncio.create_task(monitor_loop())

    yield

    task.cancel()
    try:
        await task
    except:
        pass


# ---------------------------------------------------------
# FASTAPI APP
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


@app.post("/add_stock/{ticker}")
def add_stock(ticker: str):
    t = ticker.strip().upper()

    if not t.endswith(".NS"):
        t += ".NS"

    if t not in stocks:
        stocks.append(t)
        state[t] = {
            "open_high": None,
            "open_low": None,
            "current_high": None,
            "current_low": None,
            "last_price": None,
            "status": "UNKNOWN",
            "last_update": None
        }
        save_persist()

    return {"ok": True, "stocks": stocks}


# ---------------------------------------------------------
# UVICORN RUN (LOCAL)
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)