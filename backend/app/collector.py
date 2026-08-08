import os
import requests
import time
from dotenv import load_dotenv
from database import ETFHolding, ETFInfo, init_db, SessionLocal
from datetime import datetime, timedelta
from pricing import build_price_krw_map

load_dotenv()

# ─────────────────────────────────────────────
# ⚠️ 쿠키 만료되면 .env 파일의 KRX_COOKIE 값만 새로 바꾸면 돼요!
# ─────────────────────────────────────────────
COOKIE = os.environ["KRX_COOKIE"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030108",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cookie": COOKIE,
}

DELAY = 0.7

# 주식 종목을 보유하지 않는(채권/파생 기반) 상품은 "구성종목" 개념이 없어서 제외
# 국가/지역 ETF(미국, 중국 등)는 더 이상 제외하지 않음 - 해외종목도 pricing.py로 비중을 계산함
EXCLUDE = [
    "채권", "국채", "통안채", "회사채", "특수채", "하이일드",
    "선물", "인버스", "레버리지", "SOFR", "KOFR", "CD금리",
    "머니마켓", "단기채", "장기채", "국고채", "금리",
]


def is_domestic_code(stock_code):
    """KRX 국내 종목코드(6자리 숫자) 여부. 아니면 해외종목 ISIN으로 간주"""
    return len(stock_code) == 6 and stock_code.isdigit()


def get_trading_date():
    today = datetime.today()
    if today.weekday() == 5:
        today = today - timedelta(days=1)
    elif today.weekday() == 6:
        today = today - timedelta(days=2)
    return today.strftime("%Y%m%d")


def get_isin_map(trd_dd):
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
            stock_name = r.get("COMPST_ISU_NM", "").strip()
            if not stock_code:
                continue
            # 현금성자산/예금 등 placeholder 항목은 실제 보유 "종목"이 아니라서 제외
            # (해외종목 ETF는 실물 대신 현금으로 설정/환매되는 구조라 스케일이 달라
            #  섞어서 비중을 계산하면 왜곡됨)
            if stock_code.startswith("CASH") or stock_code.startswith("KRD") or "현금" in stock_name or "예금" in stock_name:
                continue

            shares_str = r.get("COMPST_ISU_CU1_SHRS", "0") or "0"
            try:
                shares = float(shares_str.replace(",", ""))
            except:
                shares = 0.0

            amount_str = r.get("COMPST_AMT", "0") or "0"
            try:
                amount = float(amount_str.replace(",", ""))
            except:
                amount = 0.0

            # 비중 키값 여러 개 시도
            weight = 0.0
            for key in ["COMPST_RTO", "COMPST_RT", "compst_rt", "compst_rto", "COMPST_WGHT", "VALU_AMT_WGHT"]:
                val = r.get(key, "")
                if val and val != "":
                    try:
                        weight = float(str(val).replace(",", ""))
                        break
                    except:
                        pass

            result.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "shares": shares,
                "amount": amount,
                "weight": weight,
            })
        return result
    except Exception as e:
        print(f"  오류: {e}")
        return []


def _needs_pricing(h):
    """KRX가 금액/비중을 안 주는 해외종목 보유분인지 확인"""
    return (
        h["shares"] > 0
        and h["amount"] == 0
        and not is_domestic_code(h["stock_code"])
    )


def collect_and_save(etf_codes, trd_dd):
    init_db()
    db = SessionLocal()

    print(f"\n구성종목 수집 시작 ({len(etf_codes)}개)...\n")
    isin_map = get_isin_map(trd_dd)

    # 1단계: 전체 ETF의 구성종목을 먼저 메모리에 모두 모음
    etf_holdings = {}
    for i, code in enumerate(etf_codes):
        info = isin_map.get(code)
        if not info:
            print(f"  [{i+1}/{len(etf_codes)}] {code} → ISIN 없음")
            continue

        holdings = get_holdings(info["isin"], code, trd_dd, info["name"])
        print(f"  [{i+1}/{len(etf_codes)}] {code} {info['name']:<35} → {len(holdings)}개" if holdings else f"  [{i+1}/{len(etf_codes)}] {code} {info['name']:<35} → 데이터 없음")
        etf_holdings[code] = holdings
        time.sleep(DELAY)

    # 2단계: 해외종목(가격 정보 없는 보유분)의 ISIN을 전부 모아 한 번에 시세 조회
    foreign_isins = set()
    for holdings in etf_holdings.values():
        for h in holdings:
            if _needs_pricing(h):
                foreign_isins.add(h["stock_code"])

    price_krw_map = {}
    if foreign_isins:
        print(f"\n해외종목 {len(foreign_isins)}개 시세 조회 중...")
        price_krw_map = build_price_krw_map(list(foreign_isins))
        print(f"시세 확보: {len(price_krw_map)}/{len(foreign_isins)}개")

    # 3단계: 해외종목 금액을 채우고, 필요한 ETF는 비중을 다시 계산해서 저장
    for code, holdings in etf_holdings.items():
        info = isin_map[code]

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

        recompute_weight = False
        for h in holdings:
            if _needs_pricing(h):
                price = price_krw_map.get(h["stock_code"])
                if price is not None:
                    h["amount"] = h["shares"] * price
                    recompute_weight = True

        if recompute_weight:
            total = sum(h["amount"] for h in holdings)
            if total > 0:
                for h in holdings:
                    h["weight"] = round(h["amount"] / total * 100, 4)

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

    db.close()
    print("\n완료!")


if __name__ == "__main__":
    trd_dd = get_trading_date()
    print(f"기준일: {trd_dd}")

    print("ETF 목록 조회 중...")
    isin_map = get_isin_map(trd_dd)
    print(f"전체 {len(isin_map)}개 ETF")

    stock_codes = []
    for code, info in isin_map.items():
        name = info["name"]
        if not any(kw in name for kw in EXCLUDE):
            stock_codes.append(code)

    print(f"국내 주식형 ETF: {len(stock_codes)}개")
    collect_and_save(stock_codes, trd_dd)