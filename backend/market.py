from datetime import datetime, time
import pytz

IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def now_ist():
    return datetime.now(IST)


def market_open():
    now = now_ist().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def after_1030():
    return now_ist().time() >= time(10, 30)
