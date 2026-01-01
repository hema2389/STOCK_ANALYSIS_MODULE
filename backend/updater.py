import yfinance as yf
from datetime import date
from storage import Stock
from market import now_ist, market_open, after_1030

PROXIMITY_PCT = 0.001

def update_prices(db):
    now = now_ist()

    for stock in db.query(Stock).all():
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

            df.index = df.index.tz_localize("UTC").tz_convert(now.tzinfo)

            live_df = df[df.index.time <= now.time()]
            if live_df.empty:
                continue

            last_price = round(float(live_df["Close"].iloc[-1]), 2)
            cur_high = round(float(live_df["High"].max()), 2)
            cur_low = round(float(live_df["Low"].min()), 2)

            stock.last_price = last_price
            stock.current_high = cur_high
            stock.current_low = cur_low

            if after_1030():
                ref = live_df.between_time("09:15", "10:30")
                if not ref.empty:
                    stock.high_1030 = round(ref["High"].max(), 2)
                    stock.low_1030 = round(ref["Low"].min(), 2)

            # STATUS
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

            if not market_open():
                stock.status = "MARKET_CLOSED"
                stock.eod_price = last_price
                stock.eod_high = cur_high
                stock.eod_low = cur_low
                stock.eod_date = date.today()

        except Exception as e:
            print("ERROR:", stock.symbol, e)

    db.commit()
