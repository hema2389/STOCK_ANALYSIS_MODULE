# main.py
import os
import json
import asyncio
from datetime import datetime, time as dtime
from contextlib import asynccontextmanager
from typing import Optional

import pytz
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# ================= CONFIG =================
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
ENV_STOCKS = os.getenv("STOCKS", "")   # e.g. RELIANCE.NS,SBIN.NS
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))

INDIA = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)

CAPTURE_HOUR = 10
CAPTURE_MINUTE = 30

# ================= STATE =================
stocks: list[str] = []
state: dict = {}

# ================= HELPERS =================
def now_ist():
    return datetime.now(INDIA)

def is_market_open():
    t = now_ist().time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def yf_intraday(ticker: str):
    try:
        df = yf.download(
            ticker,
            period="1d",
            interval="1m",
            auto_adjust=False,
            progress=False
        )
        return None if df is None or df.empty else df
    except Exception:
        return None

def fval(v):
    try:
        return float(v.item()) if hasattr(v, "item") else float(v)
    except Exception:
        return None

# ================= PERSIST =================
def load_persist():
    global stocks, state

    if os.path.exists(PERSIST_FILE):
        with open(PERSIST_FILE, "r") as f:
            saved = json.load(f)
            stocks = saved.get("stocks", [])
            state = saved.get("state", {})

    # merge ENV stocks
    if ENV_STOCKS:
        for s in ENV_STOCKS.split(","):
            s = s.strip().upper()
            if s and s not in stocks:
                stocks.append(s)

def save_persist():
    with open(PERSIST_FILE, "w") as f:
        json.dump({"stocks": stocks, "state": state}, f)

def ensure_stock(t):
    if t not in stocks:
        stocks.append(t)

    state.setdefault(t, {
        "open_high": None,
        "open_low": None,
        "current_high": None,
        "current_low": None,
        "last_price": None,
        "status": "UNKNOWN",
        "last_update": None
    })

# ================= MONITOR LOOP =================
async def monitor():
    captured_1030 = set()
    reset_done = False
    prev_date = now_ist().date()

    while True:
        try:
            now = now_ist()

            # -------- NEW DAY RESET --------
            if now.date() != prev_date:
                captured_1030.clear()
                reset_done = False
                prev_date = now.date()

            if not reset_done and now.time() >= MARKET_OPEN:
                for s in stocks:
                    ensure_stock(s)
                    state[s].update({
                        "open_high": None,
                        "open_low": None,
                        "current_high": None,
                        "current_low": None,
                        "last_price": None,
                        "status": "UNKNOWN",
                        "last_update": None
                    })
                save_persist()
                reset_done = True

            market_open = is_market_open()

            for s in list(stocks):
                ensure_stock(s)
                df = yf_intraday(s)
                if df is None:
                    continue

                last_price = fval(df["Close"].iloc[-1])
                day_high = float(df["High"].max())
                day_low = float(df["Low"].min())

                state[s]["last_price"] = last_price
                state[s]["last_update"] = now.isoformat()

                # -------- LIVE HIGH / LOW --------
                if market_open:
                    state[s]["current_high"] = day_high
                    state[s]["current_low"] = day_low

                    # ---- SAFE 10:30 CAPTURE ----
                    capture_time = now.replace(
                        hour=CAPTURE_HOUR,
                        minute=CAPTURE_MINUTE,
                        second=0,
                        microsecond=0
                    )

                    if now >= capture_time and s not in captured_1030:
                        state[s]["open_high"] = day_high
                        state[s]["open_low"] = day_low
                        state[s]["status"] = "RED"
                        captured_1030.add(s)
                        save_persist()

                else:
                    # market closed → final summary
                    state[s]["current_high"] = day_high
                    state[s]["current_low"] = day_low
                    state[s]["status"] = "MARKET_CLOSED"

                # -------- ALERT LOGIC --------
                oh = state[s]["open_high"]
                ol = state[s]["open_low"]

                if oh and ol and last_price:
                    if state[s]["status"] != "MARKET_CLOSED":
                        state[s]["status"] = (
                            "AMBER"
                            if last_price > oh or last_price < ol
                            else "RED"
                        )

            save_persist()

        except Exception as e:
            print("Monitor error:", e)

        await asyncio.sleep(POLL_SECONDS)

# ================= FASTAPI =================
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_persist()
    for s in stocks:
        ensure_stock(s)
    task = asyncio.create_task(monitor())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= API =================
@app.get("/status")
def status():
    return {"stocks": state, "time": now_ist().isoformat()}

@app.post("/add_stock")
async def add_stock(req: Request):
    data = await req.json()
    t = data.get("ticker", "").upper().strip()
    if not t:
        return {"ok": False}
    if not t.endswith(".NS"):
        t += ".NS"
    ensure_stock(t)
    save_persist()
    return {"ok": True, "stocks": stocks}

# ================= LOCAL RUN =================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))