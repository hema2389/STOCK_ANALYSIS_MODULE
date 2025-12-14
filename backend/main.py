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

# ---------------- CONFIG ----------------
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
INDIA = pytz.timezone("Asia/Kolkata")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
CAPTURE_HOUR = 10
CAPTURE_MINUTE = 30

# ENV STOCKS (baseline)
ENV_STOCKS = [
    s.strip().upper()
    for s in os.getenv("STOCKS", "").split(",")
    if s.strip()
]

# ---------------- STATE ----------------
stocks: list[str] = []          # master ticker list
state: dict[str, dict] = {}     # ticker → data

# ---------------- HELPERS ----------------
def now_ist():
    return datetime.now(INDIA)

def is_market_open():
    t = now_ist().time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def fetch_df(ticker: str):
    try:
        df = yf.download(
            ticker,
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=False
        )
        return None if df is None or df.empty else df
    except Exception:
        return None

def f(x) -> Optional[float]:
    try:
        return float(x.item()) if hasattr(x, "item") else float(x)
    except Exception:
        return None

# ---------------- PERSISTENCE ----------------
def load_persist():
    global stocks, state

    if os.path.exists(PERSIST_FILE):
        with open(PERSIST_FILE, "r") as f:
            saved = json.load(f)
            stocks = saved.get("stocks", [])
            state = saved.get("state", {})
    else:
        stocks, state = [], {}

    # merge ENV stocks
    for s in ENV_STOCKS:
        if s not in stocks:
            stocks.append(s)

    for s in stocks:
        ensure_stock(s)

def save_persist():
    with open(PERSIST_FILE, "w") as f:
        json.dump({"stocks": stocks, "state": state}, f, indent=2)

# ---------------- CORE ----------------
def ensure_stock(ticker: str):
    state.setdefault(ticker, {
        "open_high": None,      # 10:30 High
        "open_low": None,       # 10:30 Low
        "current_high": None,   # Live / final
        "current_low": None,
        "last_price": None,
        "status": "UNKNOWN",
        "last_update": None,
        "date": str(now_ist().date())
    })

# ---------------- BACKGROUND LOOP ----------------
async def monitor():
    captured_1030 = set()
    last_reset_date = None

    while True:
        try:
            now = now_ist()
            today = str(now.date())

            # 🔁 DAILY RESET @ 9:15
            if now.time() >= MARKET_OPEN and last_reset_date != today:
                for s in stocks:
                    state[s] = {
                        "open_high": None,
                        "open_low": None,
                        "current_high": None,
                        "current_low": None,
                        "last_price": None,
                        "status": "UNKNOWN",
                        "last_update": None,
                        "date": today
                    }
                captured_1030.clear()
                last_reset_date = today
                save_persist()

            for s in list(stocks):
                ensure_stock(s)
                df = fetch_df(s)
                if df is None:
                    continue

                last = f(df["Close"].iloc[-1])
                hi = f(df["High"].max())
                lo = f(df["Low"].min())

                state[s]["last_price"] = last
                state[s]["last_update"] = now.isoformat()

                # 🔴 LIVE HIGH / LOW
                state[s]["current_high"] = hi
                state[s]["current_low"] = lo

                # 🕥 10:30 SNAPSHOT
                if (
                    now.hour == CAPTURE_HOUR
                    and now.minute == CAPTURE_MINUTE
                    and s not in captured_1030
                ):
                    state[s]["open_high"] = hi
                    state[s]["open_low"] = lo
                    state[s]["status"] = "RED"
                    captured_1030.add(s)
                    save_persist()

                # 🟡 STATUS LOGIC
                oh, ol = state[s]["open_high"], state[s]["open_low"]
                if oh and ol and last:
                    if last > oh or last < ol:
                        state[s]["status"] = "AMBER"
                    else:
                        state[s]["status"] = "RED"

                # ⚫ MARKET CLOSED
                if now.time() > MARKET_CLOSE:
                    state[s]["status"] = "MARKET_CLOSED"

            save_persist()

        except Exception as e:
            print("Monitor error:", e)

        await asyncio.sleep(POLL_SECONDS)

# ---------------- FASTAPI ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_persist()
    task = asyncio.create_task(monitor())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------- API ----------------
@app.get("/status")
def status():
    return {"time": now_ist().isoformat(), "stocks": state}

@app.post("/add_stock")
async def add_stock(req: Request):
    data = await req.json()
    t = data.get("ticker", "").strip().upper()
    if not t:
        return {"ok": False}

    if not t.endswith(".NS"):
        t += ".NS"

    if t not in stocks:
        stocks.append(t)

    ensure_stock(t)
    save_persist()

    return {"ok": True, "ticker": t, "stocks": stocks}

# ---------------- LOCAL RUN ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))