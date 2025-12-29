from sqlalchemy import create_engine, Column, String, Float, Date
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import date

DATABASE_URL = "sqlite:///stocks.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Stock(Base):
    __tablename__ = "stocks"

    symbol = Column(String, primary_key=True)

    high_1030 = Column(Float)
    low_1030 = Column(Float)

    last_price = Column(Float)
    current_high = Column(Float)
    current_low = Column(Float)

    status = Column(String, default="NEUTRAL")

    trading_date = Column(Date, default=date.today)

    # EOD snapshot (FINAL)
    eod_price = Column(Float)
    eod_high = Column(Float)
    eod_low = Column(Float)
    eod_date = Column(Date)

Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
