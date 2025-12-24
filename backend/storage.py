from sqlalchemy import create_engine, Column, String, Float, Date
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import date

engine = create_engine("sqlite:///stocks.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()

class Stock(Base):
    __tablename__ = "stocks"

    symbol = Column(String, primary_key=True)
    high_1030 = Column(Float)
    low_1030 = Column(Float)
    last_price = Column(Float)
    status = Column(String, default="NEUTRAL")
    trading_date = Column(Date, default=date.today)

Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
