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

state = {}   # live data storage


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
    except:
        pass


# ---------------------------------------------------------
# Fetch High/Low at 10:30 AM
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
    except:
        return None


# ---------------------------------------------------------
# Scheduled HL Fetch (10:30 AM IST)
# ---------------------------------------------------------
async def scheduled_fetch():
    while True:
        now = datetime.now(INDIA)

        if now.hour == FETCH_HOUR and now.minute == FETCH_MINUTE:
            print("Running 10:30 AM HL fetch...")

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
            await asyncio.sleep(61)

        await asyncio.sleep(5)


# ---------------------------------------------------------
# Live Monitor (Always updates price + live HL)
# ---------------------------------------------------------
async def monitor_prices():
    while True:
        for s in state.keys():
            try:
                ticker = yf.Ticker(s)
                hist = ticker.history(period="1d", interval="1m")

                # Market closed
                if hist is None or hist.empty:
                    continue

                latest = float(hist["Close"].iloc[-1])
                live_high = float(hist["High"].max())
                live_low = float(hist["Low"].min())

                st = state[s]
                st["last_price"] = latest
                st["current_high"] = live_high
                st["current_low"] = live_low
                st["last_checked"] = datetime.now(INDIA).isoformat()

                hi = st.get("high")    # 10:30 high
                lo = st.get("low")     # 10:30 low
                prev_status = st.get("status", "UNKNOWN")

                # HL not taken yet
                if hi is None or lo is None:
                    st["status"] = "UNKNOWN"
                else:
                    # Breakout
                    if latest > hi or latest < lo:
                        st["status"] = "AMBER"

                        if prev_status != "AMBER":
                            st["trigger_time"] = datetime.now(INDIA).strftime("%H:%M:%S")
                            st["trigger_price"] = latest
                            save_persist()
                    else:
                        st["status"] = "RED"

                if st["status"] != prev_status:
                    save_persist()

            except Exception as e:
                print("Monitor error:", s, e)

        await asyncio.sleep(POLL_SECONDS)


# ---------------------------------------------------------
# Startup Tasks
# ---------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):

    load_persist()

    # Ensure stock entries exist
    for s in STOCKS:
        if s not in state:
            state[s] = {
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

    # start tasks
    task1 = asyncio.create_task(scheduled_fetch())
    task2 = asyncio.create_task(monitor_prices())

    yield

    task1.cancel()
    task2.cancel()


# ---------------------------------------------------------
# API
# ---------------------------------------------------------
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/status")
def get_status():
    return {"stocks": state, "time": datetime.now(INDIA).isoformat()}


# ---------------------------------------------------------
# Local run
# ---------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))