import os
import time
import requests
import yfinance as yf

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_API_KEY = os.environ.get("OPENFIGI_API_KEY", "")
# API 키 없이는 요청당 10개, 키가 있으면 100개까지 허용됨
BATCH_SIZE = 100 if OPENFIGI_API_KEY else 10
DELAY_BETWEEN_BATCHES = 0.3 if OPENFIGI_API_KEY else 1.5


def map_isins_to_tickers(isins):
    """ISIN 목록을 야후 파이낸스에서 쓸 수 있는 티커로 변환"""
    unique_isins = list(dict.fromkeys(isins))
    ticker_map = {}
    headers = {"Content-Type": "application/json"}
    if OPENFIGI_API_KEY:
        headers["X-OPENFIGI-APIKEY"] = OPENFIGI_API_KEY

    for i in range(0, len(unique_isins), BATCH_SIZE):
        batch = unique_isins[i:i + BATCH_SIZE]
        if (i // BATCH_SIZE) % 20 == 0:
            print(f"  티커 변환 {i}/{len(unique_isins)}...")
        body = [{"idType": "ID_ISIN", "idValue": isin} for isin in batch]

        res = None
        for attempt in range(3):
            res = requests.post(OPENFIGI_URL, json=body, headers=headers, timeout=20)
            if res.status_code == 429:
                time.sleep(6)
                continue
            break

        if res is None or res.status_code != 200:
            continue

        results = res.json()
        for isin, entry in zip(batch, results):
            candidates = entry.get("data") or []
            if not candidates:
                continue
            best = next((c for c in candidates if c.get("exchCode") == "US"), candidates[0])
            ticker = best.get("ticker")
            if ticker:
                ticker_map[isin] = ticker

        time.sleep(DELAY_BETWEEN_BATCHES)

    return ticker_map


def get_usdkrw_rate():
    data = yf.download(tickers=["KRW=X"], period="5d", progress=False)
    return float(data["Close"]["KRW=X"].dropna().iloc[-1])


PRICE_CHUNK_SIZE = 200


def get_latest_prices_usd(tickers):
    """티커 목록의 최근 종가(달러)를 묶음 단위로 조회 (한 번에 너무 많이 요청하면 실패하기 쉬움)"""
    if not tickers:
        return {}

    prices = {}
    for i in range(0, len(tickers), PRICE_CHUNK_SIZE):
        chunk = tickers[i:i + PRICE_CHUNK_SIZE]
        print(f"  주가 조회 {i + len(chunk)}/{len(tickers)}...")
        try:
            data = yf.download(tickers=chunk, period="5d", progress=False, group_by="column")
        except Exception as e:
            print(f"  주가 조회 실패(묶음 건너뜀): {e}")
            continue

        close = data["Close"]
        if len(chunk) == 1:
            series = close.dropna()
            if not series.empty:
                prices[chunk[0]] = float(series.iloc[-1])
        else:
            for ticker in chunk:
                if ticker not in close.columns:
                    continue
                series = close[ticker].dropna()
                if not series.empty:
                    prices[ticker] = float(series.iloc[-1])

    return prices


def build_price_krw_map(isins):
    """해외종목 ISIN 목록 -> 1주당 원화 환산 가격"""
    ticker_map = map_isins_to_tickers(isins)
    if not ticker_map:
        return {}

    tickers = list(set(ticker_map.values()))
    prices_usd = get_latest_prices_usd(tickers)
    fx_rate = get_usdkrw_rate()

    price_krw = {}
    for isin, ticker in ticker_map.items():
        price = prices_usd.get(ticker)
        if price is not None:
            price_krw[isin] = price * fx_rate
    return price_krw
