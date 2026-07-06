from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./etf.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ETFInfo(Base):
    """ETF 기본정보"""
    __tablename__ = "etf_info"

    etf_code = Column(String, primary_key=True)
    etf_name = Column(String)
    isin = Column(String)
    date = Column(String)


class ETFHolding(Base):
    """ETF 구성종목"""
    __tablename__ = "etf_holdings"

    id = Column(String, primary_key=True)   # ETF코드_종목코드
    etf_code = Column(String, index=True)
    etf_name = Column(String)
    stock_code = Column(String, index=True)
    stock_name = Column(String)
    shares = Column(Float)                  # 주식수(계약수)
    amount = Column(Float)                  # 평가금액
    weight = Column(Float)                  # 구성비중(%)
    date = Column(String)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()