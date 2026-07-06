from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import get_db, ETFHolding, ETFInfo, init_db
from typing import List
from pydantic import BaseModel
app = FastAPI(title="ETF 포트폴리오 계산기 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


# ─────────────────────────────────────────────
# 요청/응답 모델
# ─────────────────────────────────────────────
class ETFInput(BaseModel):
    etf_code: str
    shares: float  # 보유 주식수


class PortfolioRequest(BaseModel):
    etfs: List[ETFInput]


# ─────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "ETF 포트폴리오 계산기 API 🚀"}


@app.get("/etfs")
def get_etf_list(db: Session = Depends(get_db)):
    """ETF 목록 조회"""
    etfs = db.query(ETFInfo).all()
    return [
        {
            "etf_code": e.etf_code,
            "etf_name": e.etf_name,
        }
        for e in etfs
    ]


@app.get("/etfs/search")
def search_etf(q: str, db: Session = Depends(get_db)):
    """ETF 검색"""
    etfs = db.query(ETFInfo).filter(
        ETFInfo.etf_name.contains(q) | ETFInfo.etf_code.contains(q)
    ).all()
    return [
        {
            "etf_code": e.etf_code,
            "etf_name": e.etf_name,
        }
        for e in etfs
    ]


@app.get("/etfs/{etf_code}/holdings")
def get_etf_holdings(etf_code: str, db: Session = Depends(get_db)):
    """ETF 구성종목 조회"""
    holdings = db.query(ETFHolding).filter(
        ETFHolding.etf_code == etf_code
    ).all()
    if not holdings:
        raise HTTPException(status_code=404, detail="ETF를 찾을 수 없어요")

    total_shares = sum(h.shares for h in holdings if h.shares)

    return {
        "etf_code": etf_code,
        "etf_name": holdings[0].etf_name,
        "total_shares": total_shares,
        "holdings": [
            {
                "stock_code": h.stock_code,
                "stock_name": h.stock_name,
                "shares": h.shares,
                "amount": h.amount,
                "weight": h.weight,
            }
            for h in holdings
        ]
    }


@app.post("/portfolio/calculate")
def calculate_portfolio(request: PortfolioRequest, db: Session = Depends(get_db)):
    """
    포트폴리오 계산
    ETF 코드 + 내가 가진 주식수 입력
    → 종목별 보유금액 계산

    계산 방식:
    - ETF 전체 주식수 합계 = DB에서 조회
    - 내 비율 = 내 주식수 / ETF 전체 주식수
    - 종목별 보유금액 = 종목 평가금액 × 내 비율
    """
    result = {}  # stock_code -> {stock_name, holding_amount}

    for etf_input in request.etfs:
        code = etf_input.etf_code
        my_shares = etf_input.shares

        # 구성종목 조회
        holdings = db.query(ETFHolding).filter(ETFHolding.etf_code == code).all()
        if not holdings:
            continue

        # ETF 전체 주식수 합계
        total_shares = sum(h.shares for h in holdings if h.shares)
        if total_shares == 0:
            continue

        # 내 보유 비율
        my_ratio = my_shares / total_shares

        for h in holdings:
            if not h.amount:
                continue

            holding_amount = h.amount * my_ratio

            if h.stock_code in result:
                result[h.stock_code]["holding_amount"] += holding_amount
            else:
                result[h.stock_code] = {
                    "stock_code": h.stock_code,
                    "stock_name": h.stock_name,
                    "holding_amount": holding_amount,
                }

    # 금액 기준 내림차순 정렬
    sorted_result = sorted(
        result.values(),
        key=lambda x: x["holding_amount"],
        reverse=True
    )

    # 전체 비중 계산
    total = sum(r["holding_amount"] for r in sorted_result)
    for r in sorted_result:
        r["portfolio_weight"] = round(r["holding_amount"] / total * 100, 2) if total > 0 else 0
        r["holding_amount"] = round(r["holding_amount"], 0)

    return {
        "total_amount": round(total, 0),
        "stock_count": len(sorted_result),
        "stocks": sorted_result,
    }