import os
import requests
import streamlit as st

try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except Exception:
    BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="ETF 포트폴리오 계산기", page_icon="📊")
st.title("📊 ETF 포트폴리오 계산기")
st.caption("여러 ETF에 투자한 금액을 입력하면, 실제로 어떤 종목을 얼마나 들고 있는지 계산해드려요.")

st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"] { gap: 0.5rem; margin-bottom: -18px; align-items: center; }
    div[data-testid="stNumberInput"] input { padding: 2px 8px; height: 30px; }
    div[data-testid="stButton"] button { padding: 0px 10px; height: 30px; }
    </style>
    """,
    unsafe_allow_html=True,
)

if "portfolio" not in st.session_state:
    st.session_state.portfolio = []

st.subheader("1. ETF 검색해서 추가하기")
query = st.text_input("ETF 이름 또는 코드로 검색 (예: kodex, 200, TIGER)")

if query:
    try:
        res = requests.get(f"{BACKEND_URL}/etfs/search", params={"q": query}, timeout=60)
        results = res.json()
    except Exception:
        results = []
        st.error("백엔드 서버에 연결할 수 없어요. (서버가 잠들어 있었다면 깨어나는 중일 수 있어요, 잠시 후 다시 검색해보세요)")

    if not results:
        st.info("검색 결과가 없어요.")

    for etf in results[:20]:
        col1, col2, col3 = st.columns([3, 2, 1], gap="small")
        col1.markdown(
            f"<div style='font-size:14px; line-height:30px;'>{etf['etf_name']} "
            f"<span style='color:gray; font-size:12px;'>({etf['etf_code']})</span></div>",
            unsafe_allow_html=True,
        )
        amount = col2.number_input(
            "매수금액(원)",
            min_value=0,
            step=10000,
            key=f"amount_{etf['etf_code']}",
            label_visibility="collapsed",
        )
        if col3.button("추가", key=f"add_{etf['etf_code']}"):
            if amount > 0:
                st.session_state.portfolio.append({
                    "etf_code": etf["etf_code"],
                    "etf_name": etf["etf_name"],
                    "amount": amount,
                })
                st.rerun()
            else:
                st.warning("매수금액을 먼저 입력해주세요.")

st.subheader("2. 내가 담은 ETF 목록")
if not st.session_state.portfolio:
    st.write("아직 추가한 ETF가 없어요.")
else:
    for i, item in enumerate(st.session_state.portfolio):
        col1, col2, col3 = st.columns([3, 2, 1])
        col1.write(f"{item['etf_name']} ({item['etf_code']})")
        col2.write(f"{item['amount']:,}원")
        if col3.button("삭제", key=f"remove_{i}"):
            st.session_state.portfolio.pop(i)
            st.rerun()

    if st.button("📈 포트폴리오 계산하기", type="primary"):
        payload = {
            "etfs": [
                {"etf_code": item["etf_code"], "amount": item["amount"]}
                for item in st.session_state.portfolio
            ]
        }
        try:
            res = requests.post(f"{BACKEND_URL}/portfolio/calculate", json=payload, timeout=60)
            result = res.json()
        except Exception:
            result = None
            st.error("계산 요청이 실패했어요. (서버가 잠들어 있었다면 깨어나는 중일 수 있어요, 잠시 후 다시 시도해보세요)")

        if result:
            st.subheader("3. 결과: 내가 실제로 들고 있는 종목")
            col1, col2 = st.columns(2)
            col1.metric("총 투자금액", f"{result['total_amount']:,.0f}원")
            col2.metric("보유 종목 수", f"{result['stock_count']}개")
            st.dataframe(
                [
                    {
                        "종목명": s["stock_name"],
                        "종목코드": s["stock_code"],
                        "보유금액(원)": f"{s['holding_amount']:,.0f}",
                        "비중(%)": s["portfolio_weight"],
                    }
                    for s in result["stocks"]
                ],
                use_container_width=True,
                hide_index=True,
            )
