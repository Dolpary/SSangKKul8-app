import streamlit as st
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os

# --- [수정] 한글 폰트 설정 (폰트 파일 직접 로딩 방식) ---
# 1. 먼저 현재 폴더에 'NanumGothic.ttf' 파일이 있는지 확인
font_path = "NanumGothic.ttf"

if os.path.exists(font_path):
    # 폰트 파일이 있으면(서버 배포용) 그걸 등록해서 사용
    fm.fontManager.addfont(font_path)
    font_name = fm.FontProperties(fname=font_path).get_name()
    plt.rcParams['font.family'] = font_name
else:
    # 폰트 파일이 없으면(로컬 윈도우 테스트용) 맑은 고딕 사용
    plt.rcParams['font.family'] = 'Malgun Gothic'

plt.rcParams['axes.unicode_minus'] = False
# ----------------------------------------------------

from pykrx import stock
import pandas as pd
from datetime import datetime, timedelta

# ==========================================
# (기존 데이터 계산 함수들은 그대로 사용)
# ==========================================

@st.cache_data  # 웹 앱 속도를 위해 데이터 계산 결과를 캐시에 저장 (중요!)
def get_data_cached(offset, mode):
    # 기존 함수들을 활용하여 데이터를 가져오는 래퍼 함수
    end_day = get_last_business_day()
    start_day = get_business_day_ago(end_day, offset)
    
    if start_day is None:
        return None, None, None

    top10 = calc_top10_by_strength(start_day, end_day, mode=mode)
    return top10, start_day, end_day

def normalize_netbuy_df(df, value_col):
    if df is None or df.empty:
        return pd.DataFrame(columns=["종목명", value_col])
    df2 = df.copy()
    value_candidates = ["순매수거래대금", "순매수대금", "순매수금액", "순매수거래금액"]
    found_value = None
    for c in value_candidates:
        if c in df2.columns:
            found_value = c
            break
    if found_value is None:
        return pd.DataFrame(columns=["종목명", value_col])
    if "종목명" not in df2.columns:
        try:
            df2["종목명"] = [stock.get_market_ticker_name(t) for t in df2.index]
        except:
            df2 = df2.reset_index()
            ticker_col = df2.columns[0]
            df2 = df2.set_index(ticker_col)
    return df2[["종목명", found_value]].rename(columns={found_value: value_col})

def get_last_business_day():
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
    try:
        df = stock.get_market_ohlcv_by_date(start, end, "005930")
        return df.index[-1].strftime("%Y%m%d")
    except:
        return end

def get_business_day_ago(end_day, n):
    try:
        end_dt = datetime.strptime(end_day, "%Y%m%d")
        start = (end_dt - timedelta(days=400)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv_by_date(start, end_day, "005930")
        days = [d.strftime("%Y%m%d") for d in df.index]
        if end_day not in days: return None
        idx = days.index(end_day)
        return days[idx - n] if idx - n >= 0 else None
    except:
        return None

def calc_top10_by_strength(start_day, end_day, mode="BOTH"):
    inst_df = stock.get_market_net_purchases_of_equities(start_day, end_day, "KOSPI", "기관합계")
    inst_df = normalize_netbuy_df(inst_df, "기관")
    forg_df = stock.get_market_net_purchases_of_equities(start_day, end_day, "KOSPI", "외국인")
    forg_df = normalize_netbuy_df(forg_df, "외인")
    
    try:
        df_cap = stock.get_market_cap_by_ticker(end_day, "KOSPI")[["시가총액"]]
        df = df_cap.join(inst_df[["기관"]], how="inner").join(forg_df[["외인"]], how="inner")
        
        if "종목명" not in df.columns:
            if "종목명" in inst_df.columns: df = df.join(inst_df[["종목명"]], how="left")
            else: df["종목명"] = [stock.get_market_ticker_name(t) for t in df.index]

        if mode == "INST":
            df = df[df["기관"] > 0].copy()
            df["기관강도(%)"] = df["기관"] / df["시가총액"] * 100
            df["외인강도(%)"] = 0.0
            df["쌍끌이강도(%)"] = df["기관강도(%)"]
        elif mode == "FORG":
            df = df[df["외인"] > 0].copy()
            df["외인강도(%)"] = df["외인"] / df["시가총액"] * 100
            df["기관강도(%)"] = 0.0
            df["쌍끌이강도(%)"] = df["외인강도(%)"]
        else:
            both = df[(df["기관"] > 0) & (df["외인"] > 0)].copy()
            df = both if len(both) >= 10 else df[(df["기관"] + df["외인"]) > 0].copy()
            df["기관강도(%)"] = df["기관"] / df["시가총액"] * 100
            df["외인강도(%)"] = df["외인"] / df["시가총액"] * 100
            df["쌍끌이강도(%)"] = (df["기관"] + df["외인"]) / df["시가총액"] * 100

        return df.sort_values("쌍끌이강도(%)", ascending=False).head(10)[["종목명", "기관강도(%)", "외인강도(%)", "쌍끌이강도(%)"]]
    except:
        return pd.DataFrame()

def get_trading_series(ticker, start, end, who):
    try:
        df = stock.get_market_trading_value_by_date(start, end, ticker)
        col_map = {"기관합계": "기관합계", "외국인": "외국인합계"} # pykrx 컬럼명 대응
        target = col_map.get(who, who)
        if target not in df.columns and who == "외국인": target="외국인" # 예외처리
        if target not in df.columns and who == "기관합계": target="기관"
        
        return df[target] if target in df.columns else None
    except:
        return None

# ==========================================
# 웹 앱 UI 구성 (Streamlit)
# ==========================================
def main():
    st.set_page_config(page_title="수급 Top10 분석기", layout="wide")

    # --- 사이드바: 설정 메뉴 ---
    st.sidebar.header("🔍 분석 설정")
    
    offset_days = st.sidebar.selectbox(
        "기간 선택 (영업일 기준)",
        [2, 3, 5, 10, 20, 30, 60],
        index=0,
        format_func=lambda x: f"최근 {x}일"
    )
    
    mode_select = st.sidebar.radio(
        "분석 모드",
        ("BOTH", "INST", "FORG"),
        format_func=lambda x: {"BOTH": "기관+외인(쌍끌이)", "INST": "기관 집중", "FORG": "외인 집중"}[x]
    )

    if st.sidebar.button("데이터 새로고침"):
        st.cache_data.clear()

    # --- 메인 화면 ---
    st.title(f"📊 수급 주도주 Top 10 분석")
    
    # 데이터 로딩
    with st.spinner('데이터를 분석 중입니다... (네이버 금융 연동)'):
        top10, start_day, end_day = get_data_cached(offset_days, mode_select)

    if top10 is None or top10.empty:
        st.error("해당 조건의 종목을 찾을 수 없습니다.")
        return

    st.write(f"**분석 기간:** {start_day} ~ {end_day}")
    
    # 탭으로 종목 선택하게 만들기
    # enumerate를 써서 순서(idx)를 0부터 강제로 만듦
    tabs = st.tabs([f"{idx+1}. {row['종목명']}" for idx, (ticker, row) in enumerate(top10.iterrows())])

    # --- [수정] 탭 내부 내용 채우기 ---
    for idx, tab in enumerate(tabs):
        with tab:
            # top10.iloc[idx]를 통해 순서대로 데이터에 접근
            ticker = top10.index[idx]  # 티커(종목코드)
            row = top10.iloc[idx]      # 데이터 행
            
            # --- 상세 차트 그리기 ---
            draw_detail_chart(ticker, row, start_day, end_day, offset_days)
            
def draw_detail_chart(ticker, row, start, end, offset):
    # 가격 데이터 (120일치 확보)
    graph_start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=180)).strftime("%Y%m%d")
    df_ohlcv = stock.get_market_ohlcv_by_date(graph_start, end, ticker)
    
    if df_ohlcv is None or df_ohlcv.empty:
        st.warning("가격 데이터가 없습니다.")
        return

    # 수급 데이터
    s_inst = get_trading_series(ticker, graph_start, end, "기관합계")
    s_forg = get_trading_series(ticker, graph_start, end, "외국인")

    # Matplotlib 그리기
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), gridspec_kw={'height_ratios': [2, 1, 1]})
    
    # 1. 주가
    ax1.plot(df_ohlcv.index, df_ohlcv['종가'], label='Close')
    ax1.plot(df_ohlcv.index, df_ohlcv['종가'].rolling(20).mean(), label='MA20', alpha=0.7)
    ax1.set_title(f"{row['종목명']} ({ticker}) - 현재가: {df_ohlcv['종가'].iloc[-1]:,}원", fontsize=15, fontweight='bold')
    ax1.legend()
    ax1.grid(alpha=0.3)

    # 2. 기관
    if s_inst is not None:
        colors = ['red' if v > 0 else 'blue' for v in s_inst.values]
        ax2.bar(s_inst.index, s_inst.values, color=colors)
        ax2.set_title(f"기관 일별 순매수 (강도: {row['기관강도(%)']:.2f}%)")
        ax2.grid(alpha=0.3)
    
    # 3. 외인
    if s_forg is not None:
        colors = ['red' if v > 0 else 'blue' for v in s_forg.values]
        ax3.bar(s_forg.index, s_forg.values, color=colors)
        ax3.set_title(f"외국인 일별 순매수 (강도: {row['외인강도(%)']:.2f}%)")
        ax3.grid(alpha=0.3)

    plt.tight_layout()
    st.pyplot(fig) # 웹 앱에 그림 전송

if __name__ == "__main__":

    main()

