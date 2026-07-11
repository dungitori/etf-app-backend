import requests
import time
from database import ETFHolding, ETFInfo, init_db, SessionLocal
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# ⚠️ 쿠키 만료되면 여기만 새로 붙여넣으면 돼요!
# ─────────────────────────────────────────────
COOKIE = "__smVisitorID=MDKPQng11UM; lang=ko_KR; savedMbrId=pascalee95; npPfsHost=127.0.0.1; npPfsPort=14440; _ga=GA1.1.257228273.1783735204; JSESSIONID=xo1SlZe1gnYaOmmEbWcHq001OyaEyzYZXecRzWpMuMBJZNIGT7nAG9m9VVQLUyO9.bWRjX2RvbWFpbi9tZGNvd2FwMS1tZGNhcHAxMQ==; _ga_Z6N0DBVT2W=GS2.1.s1783735204$o1$g0$t1783735214$j50$l0$h0; mdc.client_session=true"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201030108",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Cookie": COOKIE,
}

DELAY = 0.7

EXCLUDE = [
    "미국", "중국", "일본", "인도", "베트남", "유럽", "글로벌",
    "선진국", "신흥국", "차이나", "나스닥", "달러", "엔", "라틴",
    "필리핀", "멕시코", "인도네시아", "채권", "국채", "통안채",
    "회사채", "특수채", "하이일드", "선물", "인버스", "레버리지",
    "SOFR", "KOFR", "CD금리", "머니마켓", "단기채", "장기채",
    "국고채", "금리",
]


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

        # 첫 번째 row의 키값 확인 (디버깅용)
        if rows and code == "069500":
            print(f"\n  [디버그] 키값: {list(rows[0].keys())}")
            print(f"  [디버그] 첫번째 row: {rows[0]}")

        result = []
        for r in rows:
            stock_code = r.get("COMPST_ISU_CD", "").strip()
            if not stock_code:
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
                "stock_name": r.get("COMPST_ISU_NM", "").strip(),
                "shares": shares,
                "amount": amount,
                "weight": weight,
            })
        return result
    except Exception as e:
        print(f"  오류: {e}")
        return []


def collect_and_save(etf_codes, trd_dd):
    init_db()
    db = SessionLocal()

    print(f"\n구성종목 수집 시작 ({len(etf_codes)}개)...\n")
    isin_map = get_isin_map(trd_dd)

    for i, code in enumerate(etf_codes):
        info = isin_map.get(code)
        if not info:
            print(f"  [{i+1}/{len(etf_codes)}] {code} → ISIN 없음")
            continue

        print(f"  [{i+1}/{len(etf_codes)}] {code} {info['name']:<35}", end=" ")

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