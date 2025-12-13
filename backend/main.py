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
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "4"))

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
CAPTURE_HOUR = 10
CAPTURE_MINUTE = 30

# dynamic lists / state
stocks: list[str] = []   # list of tickers
state: dict = {}         # mapping ticker -> info dict

# ---------------- Persistence ----------------
def load_persist():
    global stocks, state
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                saved = json.load(f)
                stocks = saved.get("stocks", []) or []
                state = saved.get("state", {}) or {}
            print("Loaded persisted state.")
        except Exception as e:
            print("Failed to load persist file:", e)
            stocks = []
            state = {}
    else:
        stocks = []
        state = {}

def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump({"stocks": stocks, "state": state}, f)
    except Exception as e:
        print("Failed to save persist file:", e)

# ---------------- Helpers ----------------
def now_ist():
    return datetime.now(INDIA)

def is_market_open_now() -> bool:
    t = now_ist().time()
    return MARKET_OPEN <= t <= MARKET_CLOSE

def is_time_equal(hour: int, minute: int) -> bool:
    n = now_ist()
    return n.hour == hour and n.minute == minute

def fetch_intraday_df(ticker: str):
    """
    Returns a pandas DataFrame for period=1d interval=1m, or None on error/empty.
    Uses auto_adjust=False to avoid yfinance future-warning.
    """
    try:
        df = yf.download(ticker, period="1d", interval="1m", progress=False, auto_adjust=False)
        if df is None or df.empty:
            return None
        return df
    except Exception as e:
        print("yfinance download error for", ticker, e)
        return None

def safe_float_from_series_scalar(scalar) -> Optional[float]:
    """
    Accepts a pandas scalar (like Series.iloc[-1]) and returns a float safely.
    """
    try:
        # if it's a numpy scalar or pandas scalar, .item() gives python scalar
        return float(scalar.item()) if hasattr(scalar, "item") else float(scalar)
    except Exception:
        try:
            return float(scalar)
        except Exception:
            return None

# ---------------- Core logic ----------------
def ensure_stock_entry(ticker: str):
    """Initialize state entry for a ticker if not present."""
    if ticker not in stocks:
        stocks.append(ticker)
    state.setdefault(ticker, {
        "open_high": None,      # 10:30 high (freeze)
        "open_low": None,       # 10:30 low (freeze)
        "current_high": None,   # live day high, becomes final after close
        "current_low": None,    # live day low
        "last_price": None,
        "status": "UNKNOWN",    # UNKNOWN / RED / AMBER / MARKET_CLOSED
        "last_update": None,
    })

def compute_live_from_df(ticker: str, df):
    """
    Given df for today at 1m, update last_price, current_high/current_low from df.
    Returns tuple (last_price, day_high, day_low)
    """
    try:
        last_price = safe_float_from_series_scalar(df["Close"].iloc[-1])
        day_high = float(df["High"].max()) if "High" in df.columns else None
        day_low = float(df["Low"].min()) if "Low" in df.columns else None
        return last_price, day_high, day_low
    except Exception as e:
        print("compute_live_from_df error:", ticker, e)
        return None, None, None

# ---------------- Background monitor ----------------
async def monitor_loop():
    """
    Main background loop:
    - Reset at 09:15 (clear previous day)
    - During market: update current_high/current_low from intraday df
      - At 10:30 capture open_high/open_low (10:30 snapshot)
    - After market close: ensure current_high/current_low are final and set MARKET_CLOSED status
    - Evaluate status (AMBER/RED) using open_high/open_low (10:30)
    """
    # flags to avoid multiple actions within the same minute
    captured_1030 = set()
    reset_done_today = False
    prev_date = now_ist().date()

    while True:
        try:
            now = now_ist()
            today = now.date()

            # daily reset at 09:15 (run once when date changes and time >= 09:15)
            if today != prev_date:
                # new day started; clear reset flags
                captured_1030.clear()
                reset_done_today = False
                prev_date = today

            if not reset_done_today and now.time() >= MARKET_OPEN:
                # Perform reset exactly once at/after 09:15 (will run as soon as loop sees >= 09:15)
                for s in stocks:
                    state[s] = {
                        "open_high": None,
                        "open_low": None,
                        "current_high": None,
                        "current_low": None,
                        "last_price": None,
                        "status": "UNKNOWN",
                        "last_update": None,
                    }
                save_persist()
                reset_done_today = True
                print(f"[{now.isoformat()}] Daily reset performed.")

            market_open = is_market_open_now()

            for s in list(stocks):
                ensure_stock_entry(s)

                df = fetch_intraday_df(s)
                if df is None:
                    # no data (market closed or fetch issue). If market closed, keep final values.
                    # Do not overwrite existing current_high/current_low.
                    continue

                last_price, day_high, day_low = compute_live_from_df(s, df)

                # update last price & last_update always if available
                if last_price is not None:
                    state[s]["last_price"] = last_price
                    state[s]["last_update"] = now.isoformat()

                # during market hours update current high/low from df
                if market_open:
                    if day_high is not None:
                        state[s]["current_high"] = day_high
                    if day_low is not None:
                        state[s]["current_low"] = day_low

                    # capture 10:30 open_high/open_low once (if not yet captured)
                    if now.hour == CAPTURE_HOUR and now.minute == CAPTURE_MINUTE:
                        if s not in captured_1030:
                            # best to calculate from df: use High/Low up to this minute
                            try:
                                # df already contains up to latest minute; take max/min of df
                                open_h = float(df["High"].max())
                                open_l = float(df["Low"].min())
                                state[s]["open_high"] = open_h
                                state[s]["open_low"] = open_l
                                state[s]["status"] = "RED"  # reset to RED after capture
                                state[s]["last_update"] = now.isoformat()
                                save_persist()
                                print(f"[{now.isoformat()}] Captured 10:30 HL for {s}: {open_h}/{open_l}")
                            except Exception as e:
                                print("10:30 capture error for", s, e)
                            captured_1030.add(s)

                else:
                    # market closed: ensure current_high/current_low reflect final day summary (df covers day)
                    if day_high is not None:
                        state[s]["current_high"] = day_high
                    if day_low is not None:
                        state[s]["current_low"] = day_low

                    # After market close, set status to MARKET_CLOSED (option A)
                    # But keep last AMBER/RED info recorded earlier; now override with MARKET_CLOSED
                    if now.time() > MARKET_CLOSE:
                        if state[s].get("status") != "MARKET_CLOSED":
                            state[s]["status"] = "MARKET_CLOSED"
                            state[s]["last_update"] = now.isoformat()
                            save_persist()

                # Evaluate AMBER/RED during market or before market close if open_high/open_low present
                oh = state[s].get("open_high")
                ol = state[s].get("open_low")
                if oh is not None and ol is not None and state[s].get("last_price") is not None:
                    lp = state[s]["last_price"]
                    prev = state[s].get("status", "UNKNOWN")
                    # if MARKET_CLOSED already set, do not change it further
                    if prev != "MARKET_CLOSED":
                        if lp > oh or lp < ol:
                            state[s]["status"] = "AMBER"
                        else:
                            state[s]["status"] = "RED"
                        # persist on status change
                        if state[s]["status"] != prev:
                            save_persist()

            # save periodically
            save_persist()

        except Exception as e:
            print("Monitor loop error:", e)

        await asyncio.sleep(POLL_SECONDS)

# ---------------- FastAPI Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    load_persist()
    # ensure entries exist for loaded stocks
    for t in stocks:
        ensure_stock_entry(t)

    # start background monitor
    task = asyncio.create_task(monitor_loop())
    yield
    task.cancel()
    try:
        await task
    except Exception:
        pass

# ---------------- FastAPI app ----------------
app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------------- API Endpoints ----------------
@app.get("/status")
def get_status():
    return {"stocks": state, "time": now_ist().isoformat()}

@app.post("/add_stock")
async def add_stock_json(req: Request):
    body = await req.json()
    tick = (body.get("ticker") or "").strip().upper()
    if not tick:
        return {"ok": False, "error": "Ticker missing"}
    if not tick.endswith(".NS"):
        tick = tick + ".NS"
    if tick not in stocks:
        stocks.append(tick)
    ensure_stock_entry(tick)
    save_persist()
    return {"ok": True, "ticker": tick, "stocks": stocks}

@app.post("/add_stock/{ticker}")
def add_stock_path(ticker: str):
    tick = (ticker or "").strip().upper()
    if not tick:
        return {"ok": False, "error": "Ticker missing"}
    if not tick.endswith(".NS"):
        tick = tick + ".NS"
    if tick not in stocks:
        stocks.append(tick)
    ensure_stock_entry(tick)
    save_persist()
    return {"ok": True, "ticker": tick, "stocks": stocks}

# ---------------- Run locally ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))