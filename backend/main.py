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
PERSIST_FILE = "hl.json"
INDIA = pytz.timezone("Asia/Kolkata")
POLL_SECONDS = 4   # price refresh speed

state = {}   # dynamic stock state (also used as stock list)


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
    except:
        pass


def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Error saving persist:", e)


# ---------------------------------------------------------
# Fetch High/Low
# ---------------------------------------------------------
def fetch_high_low_for_stock(ticker):
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False)
        if df is None or df.empty:
            return None
        return {
            "high": float(df["High"].max()),
            "low": float(df["Low"].min()),
        }
    except:
        return None


# ---------------------------------------------------------
# Monitor Live Prices
# ---------------------------------------------------------
async def monitor_prices():
    while True:
        for s in list(state.keys()):
            try:
                ticker = yf.Ticker(s)
                hist = ticker.history(period="1d", interval="1m")

                # No data → keep last price
                if hist is None or hist.empty:
                    state[s]["last_price"] = state[s].get("last_price", "N/A")
                    state[s]["status"] = state[s].get("status", "UNKNOWN")
                    state[s]["last_checked"] = datetime.now(INDIA).isoformat()
                    continue

                # Latest price
                latest = float(hist["Close"].iloc[-1])
                state[s]["last_price"] = latest
                state[s]["last_checked"] = datetime.now(INDIA).isoformat()

                hi = state[s].get("high")
                lo = state[s].get("low")
                prev_status = state[s].get("status", "UNKNOWN")

                if hi is None or lo is None:
                    state[s]["status"] = "UNKNOWN"
                else:
                    if latest > hi or latest < lo:
                        state[s]["status"] = "AMBER"
                        if prev_status != "AMBER":
                            state[s]["trigger_time"] = datetime.now(INDIA).strftime("%H:%M:%S")
                            state[s]["trigger_price"] = latest
                    else:
                        state[s]["status"] = "RED"

                if prev_status != state[s]["status"]:
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

    task = asyncio.create_task(monitor_prices())
    yield
    task.cancel()


# ---------------------------------------------------------
# APP INIT
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


# Add new stock dynamically
@app.post("/add_stock")
async def add_stock(request: Request):
    body = await request.json()
    ticker = body.get("ticker", "").upper().strip()

    if not ticker.endswith(".NS"):
        return {"ok": False, "error": "Ticker must end with .NS"}

    if ticker in state:
        return {"ok": False, "error": "Already exists"}

    # initialize empty stock entry
    state[ticker] = {
        "high": None,
        "low": None,
        "status": "UNKNOWN",
        "trigger_time": None,
        "trigger_price": None,
        "last_price": None,
        "last_checked": None
    }

    save_persist()
    return {"ok": True, "added": ticker}


@app.post("/force_hl/{ticker}")
def force_hl(ticker: str):
    hl = fetch_high_low_for_stock(ticker)
    if not hl:
        return {"ok": False}

    state[ticker]["high"] = hl["high"]
    state[ticker]["low"] = hl["low"]
    save_persist()
    return {"ok": True, "hl": hl}


# ---------------------------------------------------------
# UVICORN
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)