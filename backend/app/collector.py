import requests
import time
from database import ETFHolding, ETFInfo, init_db, SessionLocal
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# ⚠️ 쿠키 만료되면 여기만 새로 붙여넣으면 돼요!
# ─────────────────────────────────────────────
COOKIE = "__smVisitorID=MDKPQng11UM; lang=ko_KR; savedMbrId=pascalee95; JSESSIONID=NMf1nRIxOeyYBj4B2g1UftmFMCgaOaz8RGWWUTnuMF8bEq3eTBr8xS1DgQnCsmCd.bWRjX2RvbWFpbi9tZGNvd2FwMi1tZGNhcHAxMQ==; mdc.client_session=true"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030108",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cookie": COOKIE,
}

DELAY = 0.7

# 제외할 키워드 (해외 ETF, 채권, 파생상품 등)
EXCLUDE = [
    "미국", "중국", "일본", "인도", "베트남", "유럽", "글로벌",
    "선진국", "신흥국", "차이나", "나스닥", "달러", "엔", "라틴",
    "필리핀", "멕시코", "인도네시아", "채권", "국채", "통안채",
    "회사채", "특수채", "하이일드", "선물", "인버스", "레버리지",
    "SOFR", "KOFR", "CD금리", "머니마켓", "단기채", "장기채",
    "국고채", "금리",
]


def get_trading_date():
    """최근 거래일 조회 (주말이면 금요일로)"""
    today = datetime.today()
    if today.weekday() == 5:
        today = today - timedelta(days=1)
    elif today.weekday() == 6:
        today = today - timedelta(days=2)
    return today.strftime("%Y%m%d")


def get_isin_map(trd_dd):
    """전체 ETF 목록 + ISIN 조회"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT04601",
        "locale": "ko_KR",
        "trdDd": trd_dd,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    res = requests.post(url, data=payload, headers=HEADERS, timeout=20)
    result = {}
    for item in res.json().get("output", []):
        code = item.get("ISU_SRT_CD", "").strip()
        result[code] = {
            "isin": item.get("ISU_CD", "").strip(),
            "name": item.get("ISU_ABBRV", "").strip(),
        }
    return result


def get_holdings(isin, code, trd_dd, name=""):
    """ETF 구성종목 조회 - 주식수 + 평가금액 + 비중 포함"""
    url = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
    payload = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT05001",
        "locale": "ko_KR",
        "tboxisuCd_finder_secuprodisu1_0": f"{code}/{name}",
        "isuCd": isin,
        "isuCd2": code,
        "codeNmisuCd_finder_secuprodisu1_0": name,
        "param1isuCd_finder_secuprodisu1_0": "",
        "trdDd": trd_dd,
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    try:
        res = requests.post(url, data=payload, headers=HEADERS, timeout=15)
        rows = res.json().get("output", [])
        result = []
        for r in rows:
            stock_code = r.get("COMPST_ISU_CD", "").strip()
            if not stock_code:
                continue

            # 주식수
            shares_str = r.get("COMPST_ISU_CU1_SHRS", "0") or "0"
            try:
                shares = float(shares_str.replace(",", ""))
            except:
                shares = 0.0

            # 평가금액
            amount_str = r.get("COMPST_AMT", "0") or "0"
            try:
                amount = float(amount_str.replace(",", ""))
            except:
                amount = 0.0

            # 구성비중
            weight_str = r.get("COMPST_RTO", "0") or "0"
            try:
                weight = float(weight_str.replace(",", ""))
            except:
                weight = 0.0

            result.append({
                "stock_code": stock_code,
                "stock_name": r.get("COMPST_ISU_NM", "").strip(),
                "shares": shares,
                "amount": amount,
                "weight": weight,
            })
        return result
    except:
        return []


def collect_and_save(etf_codes: list, trd_dd: str):
    """ETF 구성종목 수집 후 DB 저장"""
    init_db()
    db = SessionLocal()

    print(f"\n🔍 구성종목 수집 시작 ({len(etf_codes)}개)...\n")

    isin_map = get_isin_map(trd_dd)

    for i, code in enumerate(etf_codes):
        info = isin_map.get(code)
        if not info:
            print(f"  [{i+1}/{len(etf_codes)}] {code} → ISIN 없음")
            continue

        print(f"  [{i+1}/{len(etf_codes)}] {code} {info['name']:<35}", end=" ")

        # ETF 기본정보 저장
        try:
            etf = db.query(ETFInfo).filter(ETFInfo.etf_code == code).first()
            if etf:
                etf.etf_name = info["name"]
                etf.date = trd_dd
            else:
                db.add(ETFInfo(
                    etf_code=code,
                    etf_name=info["name"],
                    isin=info["isin"],
                    date=trd_dd,
                ))
        except:
            pass

        # 구성종목 저장
        holdings = get_holdings(info["isin"], code, trd_dd, info["name"])
        print(f"→ {len(holdings)}개" if holdings else "→ 데이터 없음")

        db.query(ETFHolding).filter(ETFHolding.etf_code == code).delete()
        for h in holdings:
            try:
                db.add(ETFHolding(
                    id=f"{code}_{h['stock_code']}",
                    etf_code=code,
                    etf_name=info["name"],
                    stock_code=h["stock_code"],
                    stock_name=h["stock_name"],
                    shares=h["shares"],
                    amount=h["amount"],
                    weight=h["weight"],
                    date=trd_dd,
                ))
            except:
                pass

        db.commit()
        time.sleep(DELAY)

    db.close()
    print("\n✅ 완료!")


if __name__ == "__main__":
    trd_dd = get_trading_date()
    print(f"📅 기준일: {trd_dd}")

    print("📋 ETF 목록 조회 중...")
    isin_map = get_isin_map(trd_dd)
    print(f"   → 전체 {len(isin_map)}개 ETF")

    # 국내 주식형 ETF만 필터링
    stock_codes = []
    for code, info in isin_map.items():
        name = info["name"]
        if not any(kw in name for kw in EXCLUDE):
            stock_codes.append(code)

    print(f"   → 국내 주식형 ETF: {len(stock_codes)}개")
    collect_and_save(stock_codes, trd_dd)