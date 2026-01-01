from datetime import datetime, time, date
import pytz
import yfinance as yf
from storage import Stock, SessionLocal

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PROXIMITY_PCT = 0.001


def update_prices():
    db = SessionLocal()
    now = datetime.now(IST)

    try:
        stocks = db.query(Stock).all()

        for stock in stocks:
            try:
                df = yf.download(
                    stock.symbol,
                    interval="1m",
                    period="1d",
                    progress=False,
                    threads=False
                )

                if df.empty:
                    continue

                df.index = df.index.tz_localize("UTC").tz_convert(IST)

                live_df = df[df.index.time <= now.time()]
                if live_df.empty:
                    continue

                last_price = round(float(live_df["Close"].iloc[-1]), 2)
                cur_high = round(float(live_df["High"].max()), 2)
                cur_low = round(float(live_df["Low"].min()), 2)

                stock.last_price = last_price
                stock.current_high = cur_high
                stock.current_low = cur_low

                ref = live_df.between_time("09:15", "10:30")
                stock.high_1030 = round(ref["High"].max(), 2) if not ref.empty else None
                stock.low_1030 = round(ref["Low"].min(), 2) if not ref.empty else None

                if stock.high_1030 and stock.low_1030:
                    H, L, P = stock.high_1030, stock.low_1030, last_price
                    if P > H:
                        stock.status = "GREEN"
                    elif P < L:
                        stock.status = "RED"
                    elif H*(1-PROXIMITY_PCT) <= P <= H*(1+PROXIMITY_PCT):
                        stock.status = "AMBER"
                    elif L*(1-PROXIMITY_PCT) <= P <= L*(1+PROXIMITY_PCT):
                        stock.status = "PINK"
                    else:
                        stock.status = "NEUTRAL"
                else:
                    stock.status = "NEUTRAL"

                if now.time() >= MARKET_CLOSE:
                    stock.eod_price = last_price
                    stock.eod_high = cur_high
                    stock.eod_low = cur_low
                    stock.eod_date = date.today()
                    stock.status = "MARKET_CLOSED"

            except Exception as e:
                print("Stock error:", stock.symbol, e)

        db.commit()

    finally:
        db.close()
