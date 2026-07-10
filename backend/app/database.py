import os
from sqlalchemy import create_engine, Column, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres.hhbgcfnvroubdthjppfr:dltmddus123@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ETFInfo(Base):
    __tablename__ = "etf_info"

    etf_code = Column(String, primary_key=True)
    etf_name = Column(String)
    isin = Column(String)
    date = Column(String)


class ETFHolding(Base):
    __tablename__ = "etf_holdings"

    id = Column(String, primary_key=True)
    etf_code = Column(String, index=True)
    etf_name = Column(String)
    stock_code = Column(String, index=True)
    stock_name = Column(String)
    shares = Column(Float)
    amount = Column(Float)
    weight = Column(Float)
    date = Column(String)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()