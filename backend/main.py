import os
import json
import threading
import time
from datetime import datetime
import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import uvicorn

# ---------- CONFIG ----------
STOCKS = os.getenv("STOCKS", "RELIANCE.NS,SBIN.NS").split(",")  # comma separated list
PERSIST_FILE = os.getenv("PERSIST_FILE", "hl.json")
INDIA = pytz.timezone("Asia/Kolkata")
FETCH_HOUR = int(os.getenv("FETCH_HOUR", "10"))   # 10 for 10 AM IST
FETCH_MINUTE = int(os.getenv("FETCH_MINUTE", "30"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "4"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

state = {
    # will hold { 'RELIANCE.NS': {"high": float, "low": float, "status": "RED"}, ... }
}

# ---------- Persistence helpers ----------

def load_persist():
    global state
    try:
        if os.path.exists(PERSIST_FILE):
            with open(PERSIST_FILE, "r") as f:
                data = json.load(f)
                state = data
                print("Loaded persisted high/low from", PERSIST_FILE)
    except Exception as e:
        print("Failed to load persist file:", e)


def save_persist():
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print("Failed to save persist file:", e)

# ---------- Fetch today's high/low at scheduled time ----------

def fetch_high_low_for_stock(ticker):
    """Fetch intraday 1m data for today and compute high/low."""
    try:
        df = yf.download(tickers=ticker, period="1d", interval="1m", progress=False)
        if df is None or df.empty:
            return None
        hi = float(df["High"].max())
        lo = float(df["Low"].min())
        return {"high": hi, "low": lo}
    except Exception as e:
        print(f"Error fetching HL for {ticker}: {e}")
        return None


def scheduled_fetch():
    """Thread that wakes up and fetches HL at FETCH_HOUR:FETCH_MINUTE IST daily."""
    while True:
        now = datetime.now(INDIA)
        # Wait until the next minute boundary for reduced CPU
        if now.hour == FETCH_HOUR and now.minute == FETCH_MINUTE:
            print(f"Running scheduled HL fetch at {now.isoformat()}")
            for s in STOCKS:
                try:
                    result = fetch_high_low_for_stock(s)
                    if result:
                        state[s] = {"high": result["high"], "low": result["low"], "status": "RED", "last_updated": now.isoformat()}
                        print(f"Set HL for {s}: {result}")
                except Exception as e:
                    print("Error in scheduled fetch for", s, e)
            save_persist()
            # sleep 61 seconds to avoid double-run within the same minute
            time.sleep(61)
        time.sleep(5)

# ---------- Live monitor thread ----------

def monitor_prices():
    """Continuously poll live price and update status per stock."""
    while True:
        # if no HL values available, skip
        if not state:
            time.sleep(2)
            continue

        for s in list(state.keys()):
            try:
                ticker = yf.Ticker(s)
                hist = ticker.history(period="1m")
                if hist is None or hist.empty:
                    continue
                latest = float(hist["Close"].iloc[-1])
                hi = state[s].get("high")
                lo = state[s].get("low")

                prev = state[s].get("status", "RED")
                if hi is None or lo is None:
                    state[s]["status"] = "UNKNOWN"
                elif latest > hi or latest < lo:
                    state[s]["status"] = "AMBER"
                else:
                    state[s]["status"] = "RED"

                state[s]["last_price"] = latest
                state[s]["last_checked"] = datetime.now(INDIA).isoformat()

                if state[s]["status"] != prev:
                    # persist when status changes
                    save_persist()

            except Exception as e:
                print("Error monitoring", s, e)

        time.sleep(POLL_SECONDS)

# ---------- Startup: load persisted file and start threads ----------

@app.on_event("startup")
def startup_event():
    print("Starting Stock Alert backend...")
    load_persist()
    # make sure state contains initial stocks
    for s in STOCKS:
        if s not in state:
            state[s] = {"high": None, "low": None, "status": "UNKNOWN"}

    # Start the scheduler and monitor threads
    threading.Thread(target=scheduled_fetch, daemon=True).start()
    threading.Thread(target=monitor_prices, daemon=True).start()

# ---------- API endpoints ----------

@app.get("/status")
def status():
    """Return status for all stocks."""
    return {"stocks": state, "time": datetime.now(INDIA).isoformat()}

@app.get("/status/{ticker}")
def status_ticker(ticker: str):
    t = ticker.strip()
    if t in state:
        return {t: state[t]}
    return {"error": "ticker not found"}

@app.post("/force_fetch/{ticker}")
def force_fetch(ticker: str):
    """Force compute HL immediately for ticker (manual trigger)."""
    t = ticker.strip()
    result = fetch_high_low_for_stock(t)
    if result:
        now = datetime.now(INDIA)
        state[t] = {"high": result["high"], "low": result["low"], "status": "RED", "last_updated": now.isoformat()}
        save_persist()
        return {"ok": True, t: state[t]}
    return {"ok": False, "error": "failed to fetch"}

# ---------- Run if main ----------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)