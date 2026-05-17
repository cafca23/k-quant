import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import google.generativeai as genai
import re
import requests
import time
from bs4 import BeautifulSoup

# 💡 [초강력 방어 로직] 스트림릿 uv 엔진의 대소문자 버그를 강제 초기화
import sys
import subprocess

try:
    import OpenDartReader
except ModuleNotFoundError:
    try:
        # uv가 소문자로 폴더를 풀었을 경우를 대비한 우회 접속
        import opendartreader as OpenDartReader
    except ModuleNotFoundError:
        # 그래도 못 찾으면, 꼬여있는 기존 설치 파일을 싹 밀어버리고 순정 pip로 강제 재설치 (--force-reinstall)
        print("🚨 OpenDartReader 꼬임 감지: 순정 pip로 강제 재설치를 시작합니다...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "--no-cache-dir", "OpenDartReader"])
        import OpenDartReader

st.set_page_config(page_title="국장 All 퀀트 스캐너", layout="wide", page_icon="📊", initial_sidebar_state="expanded")

# --- Custom Premium CSS ---
st.markdown("""
<style>
    [data-testid="stMetricValue"] { font-size: 26px !important; font-weight: 700 !important; color: #e6edf3; }
    [data-testid="stMetricLabel"] { color: #8b949e !important; font-weight: 600 !important; text-transform: uppercase; font-size: 0.85rem !important; letter-spacing: 0.05em; }
    .banner { padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; box-shadow: 0 4px 15px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: space-between; }
    .buy-banner { background: linear-gradient(135deg, #0d47a1 0%, #1976d2 100%); color: white; border: 1px solid #1565c0; } 
    .hold-banner { background: linear-gradient(135deg, #052e16 0%, #166534 100%); color: white; border: 1px solid #15803d; }
    .sell-banner { background: linear-gradient(135deg, #450a0a 0%, #991b1b 100%); color: white; border: 1px solid #b91c1c; } 
    .banner-left { flex: 1; text-align: left; padding-right: 20px; border-right: 1px solid rgba(255,255,255,0.2); }
    .banner-right { flex: 1; text-align: center; padding-left: 20px; }
    .banner h2 { margin: 0; padding: 0; font-size: 2.2rem; text-shadow: 0 2px 4px rgba(0,0,0,0.4); }
    .banner p { margin: 8px 0 0 0; font-size: 1.15rem; opacity: 0.95; font-weight: 500;}
    .checklist-box { background-color: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; height: 100%; display: flex; flex-direction: column; justify-content: space-between; }
    .badge { padding: 5px 10px; border-radius: 5px; font-weight: bold; font-size: 0.9rem; margin-bottom: 10px; display: inline-block; }
    .badge-growth { background-color: rgba(162, 28, 175, 0.2); color: #e879f9; border: 1px solid #c026d3; }
    .badge-value { background-color: rgba(3, 105, 161, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
    .badge-cyclical { background-color: rgba(245, 158, 11, 0.2); color: #fcd34d; border: 1px solid #d97706; }
    .peer-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.95rem; }
    .peer-table th { background-color: #161b22; color: #8b949e; padding: 12px 8px; text-align: right; border-bottom: 2px solid #30363d; font-weight: 600; cursor: help; }
    .peer-table th:first-child { text-align: left; }
    .peer-table td { padding: 10px 8px; text-align: right; border-bottom: 1px solid #21262d; color: #e6edf3; }
    .peer-table td:first-child { text-align: left; font-weight: bold; }
    .peer-main-row { background-color: rgba(56, 189, 248, 0.1); border-left: 4px solid #38bdf8; }
    .peer-median-row { background-color: #21262d; font-weight: bold; color: #8b949e; border-top: 2px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# 💡 신규 추가: 클린 서플러스 데이터 추출용 엔진
@st.cache_data(ttl=86400, show_spinner="DART 원본 재무 데이터를 조회하여 클린 서플러스를 계산 중입니다... 🔍")
def get_clean_surplus_data(symbol, dart_api_key):
    """
    DART API를 통해 과거 2개년 자본총계와 배당금을 추출하여 클린 서플러스 ROE를 계산합니다.
    """
    try:
        dart = OpenDartReader(dart_api_key)
        target_year = datetime.today().year - 1 
        
        fs_current = dart.finstate(symbol, target_year, reprt_code='11011') 
        fs_prev = dart.finstate(symbol, target_year - 1, reprt_code='11011')
        
        if fs_current is None or fs_prev is None or fs_current.empty or fs_prev.empty:
            return None
            
        def get_equity(fs_df):
            eq = fs_df.loc[(fs_df['account_nm'] == '자본총계') & (fs_df['fs_div'] == 'CFS'), 'thstrm_amount']
            if eq.empty:
                eq = fs_df.loc[(fs_df['account_nm'] == '자본총계') & (fs_df['fs_div'] == 'OFS'), 'thstrm_amount']
            if eq.empty: return None
            return float(eq.values[0].replace(',', ''))
            
        bv_t = get_equity(fs_current)
        bv_t1 = get_equity(fs_prev)
        
        if bv_t is None or bv_t1 is None or bv_t1 == 0: return None
        
        div_t = 0
        div_data = dart.dividend(symbol, target_year, reprt_code='11011')
        if div_data is not None and not div_data.empty:
            div_row = div_data.loc[div_data['se'] == '현금배당금총액(백만원)']
            if not div_row.empty:
                div_val = div_row['thstrm'].values[0]
                if pd.notna(div_val) and str(div_val).strip() != '-':
                    div_t = float(str(div_val).replace(',', '')) * 1000000 
                    
        clean_surplus_profit = bv_t - bv_t1 + div_t
        cs_roe = clean_surplus_profit / bv_t1
        
        return {
            'CS_ROE': cs_roe,
            'BV_T': bv_t,
            'BV_T1': bv_t1,
            'DIV_T': div_t
        }
    except Exception as e:
        st.sidebar.error(f"DART 엔진 오류: {e}") # 사이드바에 빨간색으로 에러 표시
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_macro_data():
    try: tnx = yf.Ticker("^TNX").history(period="1d")['Close'].iloc[-1]
    except: tnx = 3.5  
    return 1.0, float(tnx)

@st.cache_data(ttl=86400, show_spinner=False)
def get_krx_list():
    for attempt in range(3):
        try:
            return fdr.StockListing('KRX')
        except Exception as e:
            time.sleep(1)
            
    try:
        kospi_df = fdr.StockListing('KOSPI')
        kosdaq_df = fdr.StockListing('KOSDAQ')
        combined_df = pd.concat([kospi_df, kosdaq_df], ignore_index=True)
        return combined_df
    except Exception as e:
        st.error("🚨 현재 한국거래소(KRX) 서버와 통신이 원활하지 않아 종목 리스트를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return pd.DataFrame(columns=['Code', 'Name', 'Market'])

@st.cache_data(ttl=86400, show_spinner=False)
def get_search_options(df):
    options = []
    if df.empty: return options 
    
    for _, row in df.iterrows():
        code = row['Code']
        name = str(row['Name'])
        aliases = []
        up_name = name.upper()
        
        if "LG" in up_name: aliases.append("엘지")
        if "SK" in up_name: aliases.append("에스케이")
        if "KT" in up_name: aliases.append("케이티")
        if "CJ" in up_name: aliases.append("씨제이")
        if "HD" in up_name: aliases.append("에이치디")
        if "HL" in up_name: aliases.append("에이치엘")
        if "GS" in up_name: aliases.append("지에스")
        if "LS" in up_name: aliases.append("엘에스")
        if "KCC" in up_name: aliases.append("케이씨씨")
        if "KG" in up_name: aliases.append("케이지")
        
        if code == "373220": aliases.append("엘지엔솔")
        if code == "207940": aliases.append("삼바")
        if code == "005930": aliases.append("삼전")
        
        alias_str = f" ({', '.join(aliases)})" if aliases else ""
        options.append(f"[{code}] {name}{alias_str}")
    return options

@st.cache_data(ttl=300, show_spinner=False)
def get_naver_finance_fundamentals(symbol, current_price):
    url = f"https://finance.naver.com/item/main.naver?code={symbol}"
    data = {'PER': np.nan, 'EPS': np.nan, 'PBR': np.nan, 'BPS': np.nan, 'DIV': np.nan, 'ROE': np.nan, 'FOREIGN_RATIO': np.nan, 'SUMMARY': ''}
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        soup = BeautifulSoup(r.text, 'html.parser')
        
        per = soup.find('em', id='_per')
        if per: data['PER'] = float(per.text.replace(',', ''))
        
        eps = soup.find('em', id='_eps')
        if eps: data['EPS'] = float(eps.text.replace(',', ''))
        
        pbr = soup.find('em', id='_pbr')
        if pbr: data['PBR'] = float(pbr.text.replace(',', ''))
        
        dvr = soup.find('em', id='_dvr')
        if dvr: data['DIV'] = float(dvr.text.replace(',', '')) / 100.0
        
        if pd.notna(data['PBR']) and current_price > 0:
            data['BPS'] = current_price / data['PBR']
            
        if pd.notna(data['PBR']) and pd.notna(data['PER']) and data['PER'] > 0:
            data['ROE'] = data['PBR'] / data['PER']
            
        for tag in soup.find_all(['th', 'dt']):
            if '외국인소진율' in tag.text or '외국인비율' in tag.text:
                sibling = tag.find_next_sibling(['td', 'dd'])
                if sibling:
                    try:
                        raw_val = sibling.text.strip().replace('%', '').replace(',', '')
                        data['FOREIGN_RATIO'] = float(raw_val) / 100.0
                        break
                    except:
                        pass
        
        summary_p = soup.select_one('.summary_info p')
        if summary_p:
            data['SUMMARY'] = summary_p.get_text(separator=' ', strip=True)
            
    except: pass
    return data

@st.cache_data(ttl=300, show_spinner=False)
def get_investor_trend(symbol):
    url = f"https://finance.naver.com/item/frgn.naver?code={symbol}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    trend_data = {"inst_5d": 0, "frgn_5d": 0, "frgn_hold": "N/A"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'type2'})
        
        if len(tables) >= 2:
            rows = tables[1].find_all('tr')
            i_sum = 0
            f_sum = 0
            cnt = 0
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 9 and cols[0].text.strip():
                    date_str = cols[0].text.strip()
                    if '.' in date_str: 
                        try:
                            i_val = int(cols[5].text.replace(',', '').strip())
                            f_val = int(cols[6].text.replace(',', '').strip())
                            i_sum += i_val
                            f_sum += f_val
                            
                            if cnt == 0:
                                trend_data['frgn_hold'] = cols[8].text.strip()
                                
                            cnt += 1
                            if cnt >= 5: 
                                break
                        except:
                            pass
                            
            trend_data['inst_5d'] = i_sum
            trend_data['frgn_5d'] = f_sum
    except Exception as e:
        pass
    return trend_data

@st.cache_data(ttl=86400, show_spinner="네이버 금융 동일업종 데이터를 스캔 중입니다... 🕵️‍♂️")
def get_dynamic_peers(symbol, ticker_name, sector):
    peers = []
    try:
        url = f"https://finance.naver.com/item/main.naver?code={symbol}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        
        compare_div = soup.find('div', class_='trade_compare')
        if compare_div:
            links = compare_div.find_all('a')
            for link in links:
                href = link.get('href', '')
                if 'code=' in href:
                    code = href.split('code=')[1][:6]
                    if code != symbol and code not in peers and len(code) == 6:
                        peers.append(code)
            if peers:
                return ', '.join(peers[:3]) 
    except Exception as e: pass

    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"temperature": 0.1})
        prompt = f"한국 주식 애널리스트입니다. '{ticker_name}'({sector} 산업)와 가장 밀접한 한국(KRX) 상장사 경쟁사 3곳의 6자리 종목코드를 쉼표로 구분해서 출력하세요. (예: 000660, 005380, 035420). 다른 텍스트 없이 오직 숫자 6자리 3개만 쉼표로 연결하세요."
        res = model.generate_content(prompt)
        matches = re.findall(r'\d{6}', res.text)
        return ', '.join(matches)
    except: return ""

@st.cache_data(ttl=300, show_spinner="경쟁사 펀더멘털 데이터를 수집 중입니다...")
def get_peers_data(target_symbol, peer_str, krx_df):
    peer_list = re.findall(r'\d{6}', peer_str)
    if target_symbol not in peer_list:
        peer_list = [target_symbol] + peer_list
    data = []
    if krx_df.empty: return pd.DataFrame(data) 
    
    for p in peer_list:
        try:
            matched = krx_df[krx_df['Code'] == p]
            if not matched.empty:
                p_name = matched.iloc[0]['Name']
                
                try:
                    raw_close = str(matched.iloc[0]['Close']).replace(',', '')
                    current_price = float(raw_close)
                except:
                    current_price = 0
                    
                naver_data = get_naver_finance_fundamentals(p, current_price)
                
                yf_pe = np.nan; yf_pb = np.nan; yf_roe = np.nan; yf_eps = np.nan; ps_val = np.nan
                try:
                    yf_p = p + (".KS" if matched.iloc[0]['Market'] in ["KOSPI", "KOSPI200"] else ".KQ")
                    info = yf.Ticker(yf_p).info
                    yf_pe = info.get('forwardPE', np.nan)
                    yf_pb = info.get('priceToBook', np.nan)
                    yf_roe = info.get('returnOnEquity', np.nan)
                    yf_eps = info.get('trailingEps', np.nan)
                    ps_val = info.get('priceToSalesTrailing12Months', np.nan) 
                except:
                    pass 
                
                data.append({
                    "Ticker": p_name,
                    "Price": current_price,
                    "P/E": naver_data.get('PER') if pd.notna(naver_data.get('PER')) else yf_pe,
                    "P/B": naver_data.get('PBR') if pd.notna(naver_data.get('PBR')) else yf_pb,
                    "ROE": naver_data.get('ROE') if pd.notna(naver_data.get('ROE')) else yf_roe,
                    "EPS": naver_data.get('EPS') if pd.notna(naver_data.get('EPS')) else yf_eps,
                    "P/S": ps_val
                })
        except Exception as e: pass
    return pd.DataFrame(data)

@st.cache_data(ttl=300, show_spinner="주가 차트 및 재무 데이터를 융합 중입니다...")
def get_stock_market_data(symbol, yf_symbol):
    stock = yf.Ticker(yf_symbol)
    try: info = stock.info
    except: info = {} 
        
    end_date = datetime.today()
    start_date_10y = end_date.replace(year=end_date.year - 10)
    
    try: hist_daily = fdr.DataReader(symbol, start_date_10y, end_date)
    except: hist_daily = pd.DataFrame()
        
    if hist_daily.empty: return info, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    hist = hist_daily.tail(504).copy() 
    hist_10y = hist_daily.resample('ME').last().copy() 
    hist_weekly = hist_daily.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
    
    return info, hist, hist_10y, hist_weekly

ex_rate, risk_free_rate = get_macro_data()
krx_df = get_krx_list()

with st.sidebar:
    st.markdown("### ⚙️ 국장 4차원 분석 설정")
    
    # 💡 신규 추가: 사이드바 DART API 입력
    _default_dart = st.secrets["DART_API_KEY"] if "DART_API_KEY" in st.secrets else ""
    dart_api_key = st.text_input("🔑 DART API KEY (클린 서플러스용)", 
                                 value=_default_dart, 
                                 type="password",
                                 help="DART API 키를 입력하면 S-RIM 계산 시 더티 서플러스를 걷어낸 '진짜 적정주가'를 산출합니다.")
    st.divider()
    
    if 'target_symbol' not in st.session_state:
        st.session_state.target_symbol = "005930" 

    def update_search():
        if st.session_state.search_input:
            st.session_state.target_symbol = st.session_state.search_input.split("]")[0].replace("[", "").strip()
            st.session_state.search_input = None

    search_options = get_search_options(krx_df)
    
    st.selectbox(
        "🔍 종목명 자동완성 검색", 
        options=search_options, 
        index=None,
        placeholder="종목명 또는 코드를 입력하세요...",
        key='search_input',
        on_change=update_search,
        help="종목을 선택하면 분석이 시작되며, 검색창은 다음 검색을 위해 자동으로 비워집니다."
    )
    
    ticker_input = st.session_state.target_symbol
    
    st.divider()
    
    symbol = ""; yf_symbol = ""; company_name = ""; default_peers = ""; default_g = 15.0
    sgr_caption = "💡 AI 추천 성장률: 대기 중"
    stock_tier = "분석 중..."
    guide_text = "종목을 입력하면 최적의 밸류에이션 트랙을 판독합니다."
    market_type = "KOSPI" 
    
    if ticker_input:
        symbol = ticker_input
        if not krx_df.empty:
            matched_row = krx_df[krx_df['Code'] == symbol]
            if not matched_row.empty:
                market_type = matched_row.iloc[0]['Market']
                company_name = matched_row.iloc[0]['Name']
            else:
                market_type = "KOSPI"
                company_name = symbol
        else:
            market_type = "KOSPI"
            company_name = symbol
            
        st.success(f"🎯 현재 분석 타깃: **{company_name}**")
        
        if symbol:
            yf_symbol = f"{symbol}.KS" if market_type in ["KOSPI", "KOSPI200"] else f"{symbol}.KQ"
            try:
                info_sb, hist_sb, _, _ = get_stock_market_data(symbol, yf_symbol)
                sector = str(info_sb.get('sector', '')).lower()
                industry_sb = str(info_sb.get('industry', '')).lower()
                
                auto_peers = get_dynamic_peers(symbol, company_name, sector)
                if auto_peers: 
                    default_peers = auto_peers
                    
                payout_sb = info_sb.get('payoutRatio', 0) if info_sb.get('payoutRatio') else 0
                temp_pbr = info_sb.get('priceToBook', 0)
                fcf_sb = info_sb.get('freeCashflow', 0)
                
                is_cyclical = any(s in sector for s in ['chemical', 'steel', 'basic materials', 'marine']) or any(s in industry_sb for s in ['shipbuilding', 'chemicals'])
                is_value = any(s in sector for s in ['financial', 'utilities', 'energy', 'consumer defensive', 'real estate']) or payout_sb >= 0.40
                is_hyper_growth = any(s in sector for s in ['healthcare', 'technology']) and (fcf_sb is None or fcf_sb < 0 or (pd.notna(temp_pbr) and isinstance(temp_pbr, (int,float)) and temp_pbr > 3.0))
                
                if is_cyclical:
                    stock_tier = "🔄 경기 순환 / 턴어라운드주"
                    guide_text = "업황 사이클을 타는 국장 굴뚝주입니다. 적자라도 턴어라운드 시 PBR 밴드 하단에서 강력한 시세가 나옵니다."
                    default_g = 7.0
                elif is_hyper_growth:
                    stock_tier = "🔥 초고성장 / 적자/투자주"
                    guide_text = "당장 피(현금)를 흘리며 미래를 사는 종목입니다. P/S 및 EV/EBITDA 등 상대가치 매출 프리미엄으로 덮어씁니다."
                    default_g = 25.0
                elif is_value:
                    stock_tier = "🏛️ 전통 가치주 / 배당주"
                    guide_text = "성장은 둔화됐으나 자산과 배당이 든든합니다. S-RIM(잔여이익모델)과 보수적인 3~5% 성장률을 권장합니다."
                    default_g = 5.0
                else:
                    stock_tier = "🚀 우량 테크 / 성장주"
                    guide_text = "돈도 잘 벌고 성장도 하는 코어 종목입니다. K-DCF(할인) 모델이 주력으로 가동됩니다."
                    default_g = 15.0
                    
                sgr_caption = f"💡 4차원 매트릭스 자동 세팅: {default_g}%"
            except: pass

    st.markdown("### 🤝 동종 업계 (Peer) 설정")
    peer_input = st.text_input("경쟁사 6자리 코드 (쉼표로 구분)", value=default_peers, help="네이버 증권 기반 자동 탐색 결과입니다.")

    if 'last_ticker_state' not in st.session_state or st.session_state.last_ticker_state != ticker_input or st.session_state.get('app_version') != 'v_k_quant_fix_indent':
        st.session_state.g_slider = default_g
        st.session_state.last_ticker_state = ticker_input
        st.session_state.app_version = 'v_k_quant_fix_indent'
        
    st.divider()
    
    st.markdown("### 🌐 거시경제(매크로) 연동")
    st.info(f"실시간 무위험 지표 금리: **{risk_free_rate:.2f}%**")
    
    if market_type == "KOSDAQ":
        discount_rate = round(risk_free_rate + 7.0, 1) 
        st.caption(f"💡 코스닥 타겟 할인율: **{discount_rate}%** (금리 + 리스크 5% + 🚨**코스닥 패널티 2%**)")
    else:
        discount_rate = round(risk_free_rate + 5.0, 1) 
        st.caption(f"💡 코스피 타겟 할인율: **{discount_rate}%** (금리 + 시장리스크 5%)")
    
    st.divider()
    
    st.markdown("### 🌱 성장률(g) 세팅 가이드")
    st.markdown(f"**🤖 자동 4차원 체급 판독:** `{stock_tier}`")
    st.info(guide_text)
        
    def set_g(val): st.session_state.g_slider = val

    g = st.slider("예상 성장률 (g) %", min_value=0.0, max_value=50.0, step=0.5, key="g_slider", help="기업의 향후 5~10년 기대 성장률")
    c1, c2, c3, c4 = st.columns(4)
    c1.button("5", on_click=set_g, args=(5.0,), width="stretch")
    c2.button("10", on_click=set_g, args=(10.0,), width="stretch")
    c3.button("20", on_click=set_g, args=(20.0,), width="stretch")
    c4.button("30", on_click=set_g, args=(30.0,), width="stretch")
    st.button("🔄 자동 추천", on_click=set_g, args=(default_g,), width="stretch")
    st.caption(sgr_caption)

def fmt_price(val):
    if pd.isna(val) or val == "N/A" or val is None: return "N/A"
    return f"₩{val:,.0f}"

def fmt_multi(val):
    if pd.isna(val) or val == "N/A" or val is None: return "-"
    return f"{val:.2f}배"

def fmt_pct(val):
    if pd.isna(val) or val == "N/A" or val is None: return "N/A"
    return f"{val * 100:.2f}%"

# --- 메인 로직 ---
col_header1, col_header2 = st.columns([3, 1])
with col_header1:
    st.markdown("<h1 style='margin-bottom: 0; font-size: 2.0rem;'>1. 국장 All 퀀트 스캐너</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #8b949e; font-size: 1.05rem; margin-top: 5px;'>대한민국 주식 시장(KRX) 맞춤형 4차원 밸류에이션 매트릭스</p>", unsafe_allow_html=True)

if symbol and yf_symbol:
    try:
        info, hist, hist_10y, hist_weekly = get_stock_market_data(symbol, yf_symbol)
        
        if hist.empty or len(hist) < 20:
            st.error(f"'{company_name}'의 데이터가 부족합니다. (신규 상장 종목은 최소 20일의 거래 데이터가 필요합니다.)")
        else:
            hist['SMA50'] = hist['Close'].rolling(window=50).mean()
            hist['SMA200'] = hist['Close'].rolling(window=200).mean()
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss
            hist['RSI'] = 100 - (100 / (1 + rs))
            hist['OBV'] = (np.sign(hist['Close'].diff()) * hist['Volume']).fillna(0).cumsum()

            current_price = int(hist['Close'].iloc[-1])
            sma50_val = hist['SMA50'].iloc[-1] if len(hist) >= 50 else np.nan
            sma200_val = hist['SMA200'].iloc[-1] if len(hist) >= 200 else np.nan
            rsi_val = hist['RSI'].iloc[-1]
            
            naver_data = get_naver_finance_fundamentals(symbol, current_price)
            investor_trend = get_investor_trend(symbol) 
            
            company_summary = naver_data.get('SUMMARY', '')
            if company_summary:
                if "다." in company_summary:
                    company_summary = company_summary.split("다.")[0] + "다."
                else:
                    company_summary = company_summary.split(".")[0] + "."
            else:
                company_summary = "기업 요약 정보를 불러올 수 없습니다."
            
            eps = naver_data['EPS'] if pd.notna(naver_data['EPS']) else info.get('trailingEps', np.nan)
            pbr = naver_data['PBR'] if pd.notna(naver_data['PBR']) else info.get('priceToBook', np.nan)
            bps = naver_data['BPS'] if pd.notna(naver_data['BPS']) else (current_price / pbr if pd.notna(pbr) and isinstance(pbr, (int,float)) and pbr > 0 else np.nan)
            roe = naver_data['ROE'] if pd.notna(naver_data['ROE']) else info.get('returnOnEquity', np.nan)
            forward_pe = naver_data['PER'] if pd.notna(naver_data['PER']) else info.get('forwardPE', np.nan)
            payout_ratio = naver_data['DIV'] if pd.notna(naver_data['DIV']) else info.get('payoutRatio', 0)
            foreign_ratio = naver_data['FOREIGN_RATIO'] if pd.notna(naver_data['FOREIGN_RATIO']) else info.get('heldPercentInstitutions', 0)
            
            debt_to_equity = info.get('debtToEquity', None)
            peg_ratio = info.get('pegRatio', None)
            shares = krx_df[krx_df['Code'] == symbol].iloc[0]['Stocks'] if not krx_df.empty and not krx_df[krx_df['Code'] == symbol].empty else info.get('sharesOutstanding', None)
            sector = str(info.get('sector', '')).lower()
            industry = str(info.get('industry', '')).lower()
            
            ev_ebitda = info.get('enterpriseToEbitda', None)
            ps_ratio = info.get('priceToSalesTrailing12Months', None)
            
            peer_df = get_peers_data(symbol, peer_input, krx_df)
            
            # 💡 신규 추가: 클린 서플러스 ROE 획득
            cs_roe = np.nan
            if dart_api_key and len(dart_api_key) > 30: 
                cs_data = get_clean_surplus_data(symbol, dart_api_key)
                if cs_data:
                    cs_roe = cs_data['CS_ROE']

            # 💡 수정됨: S-RIM 공식에 클린 서플러스 ROE 우선 적용
            rim_value = "N/A"
            applied_roe = cs_roe if pd.notna(cs_roe) else roe 
            
            if pd.notna(bps) and pd.notna(applied_roe):
                req_return = discount_rate / 100
                rim_value = bps * (applied_roe / req_return) if applied_roe > 0 else bps * 0.5 
            
            fcf = info.get('freeCashflow', None)
            dcf_value = "N/A"
            if fcf is not None and fcf > 0 and shares is not None:
                wacc = discount_rate / 100
                g_dec = g / 100
                term_g = 0.025 
                pv_fcf = sum([(fcf * ((1 + g_dec) ** i)) / ((1 + wacc) ** i) for i in range(1, 6)])
                tv = (fcf * ((1 + g_dec) ** 5) * (1 + term_g)) / max((wacc - term_g), 0.001)
                pv_tv = tv / ((1 + wacc) ** 5)
                raw_dcf = (pv_fcf + pv_tv) / shares
                dcf_value = raw_dcf * 0.80 

            relative_target = "N/A"
            if not peer_df.empty:
                median_pe = peer_df['P/E'].median()
                median_ps = peer_df['P/S'].median() if 'P/S' in peer_df.columns else np.nan
                median_pb = peer_df['P/B'].median()
                
                applied_pe = max(median_pe, forward_pe * 0.7 if pd.notna(forward_pe) else 0) if pd.notna(median_pe) else forward_pe
                applied_ps = max(median_ps, ps_ratio * 0.7 if pd.notna(ps_ratio) else 0) if pd.notna(median_ps) else ps_ratio
                applied_pb = max(median_pb, pbr * 0.7 if pd.notna(pbr) else 0) if pd.notna(median_pb) else pbr
                
                if "초고성장" in stock_tier:
                    if pd.notna(ps_ratio) and ps_ratio > 0 and pd.notna(applied_ps):
                        relative_target = (current_price / ps_ratio) * applied_ps
                    elif pd.notna(eps) and eps > 0 and pd.notna(applied_pe):
                        relative_target = eps * applied_pe
                elif "순환" in stock_tier or "가치" in stock_tier:
                    if pd.notna(bps) and bps > 0 and pd.notna(applied_pb):
                        relative_target = bps * applied_pb
                else: 
                    if pd.notna(eps) and eps > 0 and pd.notna(applied_pe):
                        relative_target = eps * applied_pe

            final_fair_value = "N/A"
            model_used = ""
            badge_html = ""
            
            if "순환" in stock_tier:
                final_fair_value = relative_target if relative_target != "N/A" else (rim_value if rim_value != "N/A" else "N/A")
                model_used = "경기순환 상대가치 (Peer P/B)" if relative_target != "N/A" else "S-RIM 보조모델"
                badge_html = f"<div class='badge badge-cyclical'>🔄 4차원 엔진: 경기순환/턴어라운드 사이클 덮어쓰기 완료</div>"
            elif "초고성장" in stock_tier:
                final_fair_value = relative_target if relative_target != "N/A" else dcf_value
                model_used = "초고성장 상대가치 (Peer P/S, EV 프리미엄)" if relative_target != "N/A" else "K-DCF (할인)"
                badge_html = f"<div class='badge badge-growth'>🔥 4차원 엔진: 초고성장/투자주 상대가치 프리미엄 덮어쓰기 완료</div>"
            elif "가치" in stock_tier:
                if rim_value == "N/A" or (isinstance(rim_value, (int, float)) and rim_value < current_price * 0.5):
                    final_fair_value = relative_target
                    model_used = "가치주 우회 트랙 (Peer 자산 상대가치)"
                else:
                    final_fair_value = rim_value
                    model_used = "한국형 S-RIM (잔여이익모델)"
                badge_html = f"<div class='badge badge-value'>🏛️ 4차 엔진: S-RIM 가치 기반 적정주가 산출 완료</div>"
            else: 
                if dcf_value == "N/A" or (isinstance(dcf_value, (int, float)) and dcf_value < current_price * 0.5):
                    final_fair_value = relative_target if relative_target != "N/A" else rim_value
                    model_used = "우량주 우회 트랙 (Peer 수익 상대가치)"
                else:
                    final_fair_value = dcf_value
                    model_used = "한국형 DCF (20% K-디스카운트)"
                badge_html = f"<div class='badge badge-growth'>🚀 4차원 엔진: 현금흐름 기반 우량성장주 타겟팅 완료</div>"
                
            margin_of_safety = "N/A"
            if final_fair_value != "N/A":
                margin_of_safety = ((final_fair_value - current_price) / abs(final_fair_value)) * 100

            hist_1y = hist.tail(252).copy()
            high_1y = hist_1y['High'].max()
            low_1y = hist_1y['Low'].min()
            drawdown = ((current_price - high_1y) / high_1y) * 100
            mdd = (hist_1y['Close'] / hist_1y['Close'].cummax() - 1.0).min() * 100
            
            df_wk = pd.DataFrame()
            if not hist_weekly.empty:
                df_wk = hist_weekly.copy()
                df_wk['MA10'] = df_wk['Close'].rolling(window=10).mean()
                df_wk['MA20'] = df_wk['Close'].rolling(window=20).mean()
                df_wk['MA60'] = df_wk['Close'].rolling(window=60).mean()
                df_wk['MA120'] = df_wk['Close'].rolling(window=120).mean()
                df_wk['Prev_Close'] = df_wk['Close'].shift(1)
                tr1 = df_wk['High'] - df_wk['Low']
                tr2 = (df_wk['High'] - df_wk['Prev_Close']).abs()
                tr3 = (df_wk['Low'] - df_wk['Prev_Close']).abs()
                df_wk['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                df_wk['ATR_22'] = df_wk['TR'].ewm(alpha=1/22, adjust=False).mean()
                df_wk['High_22'] = df_wk['High'].rolling(window=22).max()
                df_wk['Calc_Stop'] = df_wk['High_22'] - (df_wk['ATR_22'] * 3.0)
                
                atr_stop = np.zeros(len(df_wk))
                atr_stop[:] = np.nan
                calc_val = df_wk['Calc_Stop'].values
                close_val = df_wk['Close'].values
                for i in range(1, len(df_wk)):
                    if np.isnan(calc_val[i]): continue
                    prev_c, prev_s, cur_c = close_val[i-1], atr_stop[i-1], calc_val[i]
                    if np.isnan(prev_s): atr_stop[i] = cur_c
                    elif prev_c > prev_s: atr_stop[i] = max(cur_c, prev_s)
                    else: atr_stop[i] = cur_c
                df_wk['ATR_Stop'] = atr_stop
                
                ma_stack = df_wk[['MA10', 'MA20', 'MA60']]
                df_wk['Converged'] = ((ma_stack.max(axis=1) - ma_stack.min(axis=1)) / ma_stack.min(axis=1)).round(4) <= 0.0700
                df_wk['Signal_Main'] = (df_wk['Converged'] & (df_wk['Close'] > df_wk['MA20']) & (df_wk['Close'] > df_wk['MA60']) & (df_wk['MA60'] >= df_wk['MA120']) & (df_wk['Close'] > df_wk['ATR_Stop']))
                df_wk['Signal_Main'] = df_wk['Signal_Main'] & (~df_wk['Signal_Main'].shift(1).fillna(False))
                df_wk['Signal_Reentry'] = ((df_wk['Close'] > df_wk['MA60']) & ((df_wk['Prev_Close'] <= df_wk['MA10'].shift(1)) & (df_wk['Close'] > df_wk['MA10'])) & (df_wk['Close'] > df_wk['Open']) & (df_wk['MA20'] > df_wk['MA20'].shift(1)) & (df_wk['Close'] > df_wk['ATR_Stop']) & (~df_wk['Signal_Main']))
                df_wk['Signal_Sell'] = (df_wk['Prev_Close'] >= df_wk['ATR_Stop'].shift(1)) & (df_wk['Close'] < df_wk['ATR_Stop'])

            # 💡 수정됨: 퀀트 스코어 체계에 '회계적 투명성(클린 서플러스)' 지표 추가
            score = 0; checklist = []
            
            # 1. 가치
            if margin_of_safety != "N/A":
                if margin_of_safety > 20: score += 2; checklist.append({"status": "pass", "category": "가치", "desc": f"적정주가 대비 안전마진 {margin_of_safety:.1f}%", "score": "+2"})
                elif margin_of_safety > 0: score += 1; checklist.append({"status": "pass", "category": "가치", "desc": f"적정주가 대비 안전마진 {margin_of_safety:.1f}%", "score": "+1"})
                else: checklist.append({"status": "fail", "category": "가치", "desc": "고평가 상태 (안전마진 부족)", "score": "0"})
            else: checklist.append({"status": "info", "category": "가치", "desc": "적정 주가 산출 불가", "score": "-"})
                
            # 2. 수익성 (클린 서플러스 로직으로 강화)
            if pd.notna(applied_roe) and applied_roe > 0.15: 
                score += 2
                roe_label = "클린 ROE" if pd.notna(cs_roe) else "일반 ROE"
                checklist.append({"status": "pass", "category": "수익성", "desc": f"{roe_label} 15% 초과 ({applied_roe*100:.1f}%)", "score": "+2"})
            else: 
                checklist.append({"status": "fail", "category": "수익성", "desc": f"ROE 15% 미달", "score": "0"})
            
            # 3. 🚨 회계 투명성 필터 (더티 서플러스 감점 시스템)
            if pd.notna(cs_roe) and pd.notna(roe):
                roe_diff = roe - cs_roe # HTS 표면적 ROE와 진짜 ROE의 차이
                if roe_diff > 0.05: # 장부상 ROE가 클린 ROE보다 5%p 이상 뻥튀기 되어 있다면
                    score -= 1 # 1점 감점 (페널티)
                    checklist.append({"status": "fail", "category": "회계 주의", "desc": f"더티 서플러스 포착 (일회성 이익/착시 {roe_diff*100:.1f}%p)", "score": "-1"})
                else:
                    checklist.append({"status": "pass", "category": "회계 투명", "desc": "순수 영업 기반의 클린 자본 변동 확인", "score": "+0"})
                
            # 4. 건전성
            if debt_to_equity is not None and debt_to_equity < 100: score += 2; checklist.append({"status": "pass", "category": "건전성", "desc": f"안정적인 부채비율 ({debt_to_equity:.1f}%)", "score": "+2"})
            else: checklist.append({"status": "fail", "category": "건전성", "desc": f"부채비율 높음", "score": "0"})
                
            # 5. 일봉 추세
            if pd.notna(sma50_val) and pd.notna(sma200_val):
                if current_price > sma50_val and sma50_val > sma200_val: score += 3; checklist.append({"status": "pass", "category": "일봉 추세", "desc": "정배열 상승", "score": "+3"})
                elif current_price > sma50_val and sma50_val <= sma200_val: score += 1; checklist.append({"status": "info", "category": "일봉 추세", "desc": "바닥 반등 시작", "score": "+1"})
                elif current_price <= sma50_val and current_price > sma200_val: score += 1; checklist.append({"status": "info", "category": "일봉 추세", "desc": "장기 상승장 속 조정 (눌림목)", "score": "+1"})
                else: checklist.append({"status": "fail", "category": "일봉 추세", "desc": "역배열 하락세", "score": "0"})
            else: checklist.append({"status": "fail", "category": "일봉 추세", "desc": "추세 판독 불가 (신규 상장 데이터 부족)", "score": "0"})
                
            # 6. 단기 수급
            if pd.notna(rsi_val) and rsi_val < 70: score += 1; checklist.append({"status": "pass", "category": "단기 수급", "desc": f"RSI 과열 아님 ({rsi_val:.1f})", "score": "+1"})
            else: checklist.append({"status": "fail", "category": "단기 수급", "desc": "RSI 단기 과열", "score": "0"})

            if score >= 8: judgment = "🌟 강력 매수 (Strong Buy)"; banner_class = "buy-banner"; prog_color = "#1976d2"
            elif score >= 5: judgment = "🟢 분할 매수 / 관망 (Accumulate/Hold)"; banner_class = "hold-banner"; prog_color = "#166534"
            else: judgment = "🔴 매도 / 주의 (Sell/Warning)"; banner_class = "sell-banner"; prog_color = "#b91c1c"
            
            st.markdown(f"""
<div class="banner {banner_class}">
<div class="banner-left">
<h2 style="margin-bottom: 5px; font-size: 2.2rem;">{company_name} <span style="font-size:1.2rem; color:#8b949e; font-weight:normal;">한국 · {symbol} · {market_type}</span></h2>
<p style="font-size: 1.05rem; color: #c9d1d9; margin-top: 10px; margin-bottom: 0; font-weight: 400; background-color: rgba(255,255,255,0.05); padding: 10px; border-radius: 5px; display: inline-block;">💡 {company_summary}</p>
</div>
<div class="banner-right">
<p style="margin-bottom: 5px; color: rgba(255,255,255,0.8); font-size: 1rem;">퀀트 시스템 최종 평가</p>
<p style="font-size: 1.4rem; margin-top: 0;">등급: <b>{judgment}</b> &nbsp;|&nbsp; 스코어: <b style="font-size: 1.6rem;">{score}점</b></p>
</div>
</div>
""", unsafe_allow_html=True)
            
            items_html = "".join([f'''<div style="display: flex; justify-content: space-between; align-items: center; padding: 15px 18px; margin-bottom: 10px; background-color: #161b22; border-radius: 6px; border-left: 4px solid {'#3fb950' if item["status"] == 'pass' else ('#f85149' if item["status"] == 'fail' else '#d29922')}; border: 1px solid #30363d;">
<div style="display: flex; align-items: center; gap: 15px; flex: 1;">
<span style="font-size: 1.3rem;">{'✅' if item["status"] == 'pass' else ('❌' if item["status"] == 'fail' else '💡')}</span>
<span style="color: {'#3fb950' if item["status"] == 'pass' else ('#f85149' if item["status"] == 'fail' else '#d29922')}; font-weight: bold; font-size: 1.0rem; min-width: 60px; text-align: center;">{item["category"]}</span>
<span style="color: #c9d1d9; font-size: 1.15rem;">{item["desc"]}</span>
</div>
<div style="font-weight: bold; color: {'#3fb950' if item["status"] == 'pass' else ('#f85149' if item["status"] == 'fail' else '#d29922')}; font-size: 1.25rem;">{item["score"]}점</div>
</div>''' for item in checklist])
            
            st.markdown(f"""
<div style="display: grid; grid-template-columns: 1fr 1.8fr; gap: 20px; align-items: stretch; margin-bottom: 20px;">
<div style="background-color: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; margin: 0;">
<h3 style='margin:0 0 10px 0; color:#8b949e;'>TOTAL SCORE</h3>
<h1 style='font-size: 5.5rem; margin:10px 0; color:{prog_color};'>{score}<span style='font-size: 2.5rem; color:#8b949e;'> / 10</span></h1>
</div>
<div style="background-color: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; display: flex; flex-direction: column; justify-content: center; margin: 0;">
<h3 style='margin:0 0 15px 0; color:#8b949e; font-size: 1.4rem;'>평가 내용</h3>{items_html}
</div>
</div>
""", unsafe_allow_html=True)
            
            st.markdown(badge_html, unsafe_allow_html=True)
            
            st.markdown("### 2. 주요 기술지표")
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(label="현재 주가", value=fmt_price(current_price), delta=f"{drawdown:.2f}% (최고가대비)")
                c2.metric(label=f"적정 주가 ({model_used})", value=fmt_price(final_fair_value) if final_fair_value != "N/A" else "N/A", 
                                   delta=f"{margin_of_safety:.2f}% (안전마진)" if margin_of_safety != "N/A" else None,
                                   help="테크/성장주는 현금흐름할인(DCF) 모델로, 가치/배당주는 그레이엄 모델로 자동 산출됩니다.")
                c3.metric(label="1년 MDD (최대 낙폭)", value=f"{mdd:.2f}%", delta="Max Drawdown", delta_color="inverse")
                c4.metric(label="EPS (주당순이익)", value=fmt_price(eps) if pd.notna(eps) else "N/A", 
                                   help="1주당 회사가 벌어들인 순이익을 의미해요. 숫자가 클수록 회사의 기업 가치가 크고, 배당 줄 수 있는 여유가 늘어났다고 볼 수 있어요.")
                    
            with st.container(border=True):
                c5, c6, c7, c8 = st.columns(4)
                c5.metric(label="PBR", value=f"{pbr:.2f}배" if pd.notna(pbr) and pbr != 'N/A' else "N/A", 
                                   help="주가가 1주당 장부상 순자산가치의 몇 배로 거래되는지 나타냅니다. 1 미만이면 회사를 다 팔아도 남는 돈보다 주가가 싸다는 뜻(저평가)입니다.")
                c6.metric(label="ROE", value=f"{roe*100:.2f}%" if pd.notna(roe) else "N/A", 
                                   help="회사가 주주의 돈(자본)을 굴려서 1년간 얼마를 벌었는지 보여주는 핵심 수익성 지표입니다. (통상 15% 이상이면 우량 기업으로 평가)")
                c7.metric(label="52주 최고가", value=fmt_price(high_1y))
                c8.metric(label="52주 최저가", value=fmt_price(low_1y))
            
            fund_status = "2. 주요 기술지표 브리핑"
            fund_color = "#29b6f6" 
            fund_bg = "41, 182, 246"
            
            fund_desc = ""
            if final_fair_value != "N/A":
                is_undervalued = margin_of_safety > 0
                if is_undervalued:
                    fund_desc += f"현재 주가({fmt_price(current_price)})는 계산된 적정 주가({fmt_price(final_fair_value)})보다 **싸게(저평가)** 거래 중임.<br><br>"
                    fund_color = "#3fb950"; fund_bg = "63, 185, 80"
                else:
                    fund_desc += f"현재 주가({fmt_price(current_price)})는 계산된 적정 주가({fmt_price(final_fair_value)})보다 **비싸게(고평가)** 거래 중임.<br><br>"
                    fund_color = "#f85149"; fund_bg = "248, 81, 73"
            else:
                fund_desc += f"현재 적자이거나 남는 현금(FCF)이 부족해 정확한 적정 주가를 계산하기 어려움.<br><br>"
                
            if pd.notna(roe):
                if roe > 0.15: fund_desc += "가진 돈(자본) 대비 수익 내는 능력(ROE)이 15%를 넘어 매우 우수함.<br><br>"
                else: fund_desc += "가진 돈(자본) 대비 수익 내는 능력(ROE)이 15% 아래라 평범하거나 다소 아쉬움.<br><br>"
            fund_desc += f"최근 1년 동안 가장 비쌌을 때보다 최대 {mdd:.1f}% 떨어진 적이 있음."
            
            st.markdown(f"""
<div style="padding: 15px; border-radius: 5px; margin-top: 10px; margin-bottom: 20px; border-left: 4px solid {fund_color}; background-color: rgba({fund_bg}, 0.1);">
<h4 style="margin-top: 0; color: {fund_color};">{fund_status}</h4>
<p style="margin-bottom: 0; font-size: 0.95rem; color: #c9d1d9; line-height: 1.6;">{fund_desc}</p>
</div>
""", unsafe_allow_html=True)
            
            st.markdown("<br><h3 style='margin-bottom: 10px;'>🕵️‍♂️ 3. 외국인/기관 수급 동향</h3>", unsafe_allow_html=True)
            
            frgn_hold_str = investor_trend['frgn_hold'] if investor_trend['frgn_hold'] != "N/A" else f"{foreign_ratio * 100:.2f}%"
            frgn_5d = investor_trend['frgn_5d']
            inst_5d = investor_trend['inst_5d']
            
            f_delta = "매집 중 (순매수)" if frgn_5d > 0 else ("이탈 중 (순매도)" if frgn_5d < 0 else "중립")
            f_color = "normal" if frgn_5d > 0 else ("inverse" if frgn_5d < 0 else "off")
            
            i_delta = "매집 중 (순매수)" if inst_5d > 0 else ("이탈 중 (순매도)" if inst_5d < 0 else "중립")
            i_color = "normal" if inst_5d > 0 else ("inverse" if inst_5d < 0 else "off")
            
            with st.container(border=True):
                mc1, mc2, mc3 = st.columns(3)
                mc1.metric("외국인 보유율 (소진율)", frgn_hold_str, help="현재 외국인이 전체 주식 중 얼마나 쥐고 있는지 나타냅니다. 한국 시장은 13F 공시 같은 기관 전체 보유율은 공개되지 않으므로 외인 비중 추적이 핵심입니다.")
                mc2.metric("최근 5거래일 외국인 순매매", f"{frgn_5d:,.0f}주" if frgn_5d != 0 else "N/A", delta=f_delta, delta_color=f_color, help="최근 5일 동안 외국인이 이 주식을 순수하게 사모았는지(매집), 팔았는지(이탈) 1주 단위로 보여줍니다.")
                mc3.metric("최근 5거래일 기관 순매매", f"{inst_5d:,.0f}주" if inst_5d != 0 else "N/A", delta=i_delta, delta_color=i_color, help="최근 5일 동안 연기금, 투신 등 기관투자자들이 이 주식을 순수하게 매집했는지 이탈했는지 보여줍니다.")
            
            st.markdown("<br><h3 style='margin-bottom: 10px;'>🚨 4. 밸류업 & 잠재 리스크 지표</h3>", unsafe_allow_html=True)
            with st.container(border=True):
                kc1, kc2, kc3 = st.columns(3)
                
                div_val = f"{payout_ratio * 100:.2f}%" if pd.notna(payout_ratio) and payout_ratio > 0 else "미배당/무환원"
                div_delta = "기업 밸류업 수혜" if pd.notna(payout_ratio) and payout_ratio >= 0.04 else ("주주환원 미흡" if not pd.notna(payout_ratio) or payout_ratio < 0.02 else "보통")
                div_color = "normal" if pd.notna(payout_ratio) and payout_ratio >= 0.04 else ("inverse" if not pd.notna(payout_ratio) or payout_ratio < 0.02 else "off")
                
                overhang_val = "안전" if market_type == "KOSPI" and current_price > 50000 else "주의 요망"
                overhang_delta = "코스피 대형주" if overhang_val == "안전" else "코스닥 잠재 물량폭탄 위험"
                overhang_color = "normal" if overhang_val == "안전" else "inverse"
                
                margin_val = "안전" if market_type == "KOSPI" and current_price > 50000 else "경고 구간"
                margin_delta = "대형주 신용 면제" if margin_val == "안전" else "단기 빚투/반대매매 위험"
                margin_color = "normal" if margin_val == "안전" else "inverse"
                
                kc1.metric(label="총 주주환원율 (배당 등)", value=div_val, delta=div_delta, delta_color=div_color, help="회사가 벌어들인 돈을 주주에게 얼마나 돌려주는지(배당수익률 포함) 나타냅니다. 코리아 디스카운트 해소의 핵심 열쇠입니다.")
                kc2.metric(label="CB/BW 오버행 (잠재매도) 리스크", value=overhang_val, delta=overhang_delta, delta_color=overhang_color, help="코스닥 소형주의 경우, 주가가 오를 때마다 전환사채(CB)나 신주인수권부사채(BW)가 주식으로 변환되어 매물 폭탄으로 쏟아질 위험을 경고합니다.")
                kc3.metric(label="신용잔고 경고 (빚투 비율)", value=margin_val, delta=margin_delta, delta_color=margin_color, help="개미들이 증권사에 빚을 내서(신용) 산 물량입니다. 이 비율이 높으면 세력들이 반대매매를 유도하기 위해 주가를 의도적으로 폭락시킬 위험이 매우 큽니다.")
                
                st.caption("※ CB/BW 오버행 및 신용잔고 수치는 종목의 시총과 소속 시장(코스닥)을 기반으로 한 1차 AI 위험 판독 결과입니다. 정확한 수치는 HTS 수급 탭을 병행 확인하십시오.")
            
            risk_status = "리스크 종합 브리핑"
            risk_color = "#29b6f6"
            risk_bg = "41, 182, 246"
            
            risk_desc = ""
            if frgn_5d > 0 and inst_5d > 0:
                risk_desc += "최근 5일간 외국인과 기관이 **함께 사들이며(쌍끌이 매수)** 돈이 강하게 몰리는 중임.<br><br>"
            elif frgn_5d < 0 and inst_5d < 0:
                risk_desc += "최근 5일간 외국인과 기관이 **함께 팔고 있어(쌍끌이 매도)** 주가 하락 변동성에 극도로 주의해야 함.<br><br>"
            else:
                risk_desc += "외국인과 기관의 사고파는 방향이 엇갈리며 치열한 눈치싸움 중임.<br><br>"
                
            if pd.notna(payout_ratio) and payout_ratio >= 0.04:
                risk_desc += f"주주에게 이익을 돌려주는 비율({payout_ratio*100:.1f}%)도 우수해 주가 방어력이 단단함.<br><br>"
            else:
                risk_desc += "주주에게 이익을 돌려주는 비율은 다소 부족함.<br><br>"
                
            if market_type == "KOSPI" and current_price > 50000:
                risk_desc += "우량 대형주로 분류되어 갑작스러운 주식 변환 매물(CB/BW)이나 빚투 강제 청산(반대매매) 위험은 적음."
                risk_color = "#3fb950"
                risk_bg = "63, 185, 80"
            else:
                risk_desc += "중소형주 특성상 갑작스러운 주식 변환 매물(CB/BW) 폭탄과 빚투 개미털기 위험을 항상 주의해야 함."
                risk_color = "#f85149"
                risk_bg = "248, 81, 73"

            st.markdown(f"""
<div style="padding: 15px; border-radius: 5px; margin-top: 10px; margin-bottom: 20px; border-left: 4px solid {risk_color}; background-color: rgba({risk_bg}, 0.1);">
<h4 style="margin-top: 0; color: {risk_color};">{risk_status}</h4>
<p style="margin-bottom: 0; font-size: 0.95rem; color: #c9d1d9; line-height: 1.6;">{risk_desc}</p>
</div>
""", unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.markdown("### 5. 동종 업계 비교")
            if not peer_df.empty:
                q_mark = "<span style='display:inline-block; width:14px; height:14px; border:1.5px solid #8b949e; color:#8b949e; border-radius:50%; text-align:center; line-height:11px; font-size:10px; font-weight:bold; cursor:help; vertical-align:middle; margin-left:4px;' title='{0}'>?</span>"
                table_html = "<table class='peer-table'><tr>" \
                             "<th>Company (기업명)</th>" \
                             f"<th>Price (현재 주가) {q_mark.format('현재 거래되는 주식의 가격입니다.')}</th>" \
                             f"<th>PER (주가/수익) {q_mark.format('주가수익비율. 1주당 수익 대비 주가가 몇 배인지 나타냅니다. 낮을수록 저평가.')}</th>" \
                             f"<th>PBR (주가/순자산) {q_mark.format('주가순자산비율. 1주당 순자산 대비 주가가 몇 배인지 나타냅니다. 1 미만이면 장부상 청산가치보다 저렴하다는 뜻입니다.')}</th>" \
                             f"<th>ROE (자기자본이익률) {q_mark.format('자기자본이익률. 주주가 투자한 돈으로 1년간 얼마나 이익을 냈는지 나타냅니다. 15% 이상이면 우수.')}</th>" \
                             f"<th>EPS (주당순이익) {q_mark.format('주당순이익. 1주가 1년 동안 벌어들인 순이익입니다.')}</th>" \
                             f"<th>P/S (주가/매출액) {q_mark.format('주가매출비율. 1주당 매출액 대비 주가가 몇 배인지 나타냅니다. 이익이 없는 적자 성장주 평가에 유용합니다.')}</th>" \
                             "</tr>"
                for _, row in peer_df.iterrows():
                    is_main = row['Ticker'] == company_name
                    row_class = "peer-main-row" if is_main else ""
                    table_html += f"<tr class='{row_class}'><td>{row['Ticker']}</td><td>{fmt_price(row['Price'])}</td><td>{fmt_multi(row['P/E'])}</td><td>{fmt_multi(row['P/B'])}</td><td>{fmt_pct(row['ROE'])}</td><td>{fmt_price(row['EPS'])}</td><td>{fmt_multi(row['P/S'])}</td></tr>"
                
                median_pe = peer_df['P/E'].median()
                median_pb = peer_df['P/B'].median()
                median_roe = peer_df['ROE'].median()
                median_eps = peer_df['EPS'].median()
                median_ps = peer_df['P/S'].median() if 'P/S' in peer_df.columns else np.nan
                
                table_html += f"<tr class='peer-median-row'><td>산업 중앙값 (Median)</td><td>-</td><td>{fmt_multi(median_pe)}</td><td>{fmt_multi(median_pb)}</td><td>{fmt_pct(median_roe)}</td><td>{fmt_price(median_eps)}</td><td>{fmt_multi(median_ps)}</td></tr></table>"
                
                with st.container(border=True): st.markdown(table_html, unsafe_allow_html=True)
            else:
                st.warning("경쟁사 데이터를 불러올 수 없습니다.")
                
            st.markdown("<br>", unsafe_allow_html=True)

            if not hist_10y.empty and final_fair_value != "N/A":
                df_10y = hist_10y[['Close']].copy()
                df_10y.rename(columns={'Close': 'Price'}, inplace=True)
                latest_date = df_10y.index[-1]
                years_diff = (latest_date - df_10y.index).days / 365.25
                df_10y['Value'] = final_fair_value / ((1 + g/100) ** years_diff)
                df_10y['Over_Top'] = np.maximum(df_10y['Price'], df_10y['Value'])
                df_10y['Under_Bottom'] = np.minimum(df_10y['Price'], df_10y['Value'])

                fig_val = go.Figure()
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Value'], line=dict(width=0), showlegend=False, hoverinfo='skip'))
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Over_Top'], fill='tonexty', fillcolor='rgba(239, 83, 80, 0.3)', line=dict(width=0), showlegend=False, hoverinfo='skip'))
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Under_Bottom'], line=dict(width=0), showlegend=False, hoverinfo='skip'))
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Value'], fill='tonexty', fillcolor='rgba(102, 187, 106, 0.3)', line=dict(width=0), showlegend=False, hoverinfo='skip'))
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Price'], mode='lines', line=dict(color='#29b6f6', width=2), name='실제 주가 (Price)'))
                fig_val.add_trace(go.Scatter(x=df_10y.index, y=df_10y['Value'], mode='lines', line=dict(color='#ffa726', width=2, dash='dot'), name=f'추정 적정가치 ({model_used})'))

                fig_val.update_layout(
                    title=dict(text="📊 10 YR Price to Intrinsic Value Variance Analysis", font=dict(size=20), x=0.5, xanchor='center'),
                    hovermode="x unified", height=550, margin=dict(l=0, r=0, t=50, b=0),
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d'),
                    yaxis=dict(showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d', side='right', tickprefix="₩"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                with st.container(border=True): st.plotly_chart(fig_val, use_container_width=True)

            plot_hist_1y = hist_1y.copy()

            st.markdown("<br>### 📉 6. 최근 1년 주가 일봉 차트 & 세력 매집(OBV) 지표", unsafe_allow_html=True)
            
            with st.expander("🪄 차트 화면이 줌인/줌아웃으로 틀어졌을 때 1초 복구 팁"):
                st.markdown("""
                * **마우스 더블클릭 (가장 추천):** 차트 안쪽 빈 공간을 마우스 왼쪽 버튼으로 **'따닥!'** 더블클릭하시면 틀어졌던 캔들이 즉시 처음 화면(Auto-scale)으로 깔끔하게 정렬됩니다.
                * **홈(Home) 버튼 누르기:** 차트 우측 상단 모서리에 마우스를 올리면 나타나는 반투명 메뉴에서 **집 모양 아이콘(Reset axes)**을 누르셔도 완벽하게 복구됩니다.
                """)
            
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])
            fig.add_trace(go.Candlestick(x=plot_hist_1y.index, open=plot_hist_1y['Open'], high=plot_hist_1y['High'], low=plot_hist_1y['Low'], close=plot_hist_1y['Close'], increasing_line_color='#ef5350', decreasing_line_color='#42a5f5', name=f"{company_name} 캔들"), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_hist_1y.index, y=plot_hist_1y['SMA50'], mode='lines', line=dict(color='#ffd600', width=1.5), name='50일 이동평균'), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_hist_1y.index, y=plot_hist_1y['SMA200'], mode='lines', line=dict(color='#00b0ff', width=1.5), name='200일 이동평균'), row=1, col=1)
            fig.add_trace(go.Scatter(x=plot_hist_1y.index, y=plot_hist_1y['OBV'], mode='lines', line=dict(color='#e879f9', width=2), name='OBV (매집량)'), row=2, col=1)
            
            fig.update_layout(
                xaxis_rangeslider_visible=False, height=750, margin=dict(l=0, r=0, t=10, b=0),
                template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            fig.update_yaxes(title_text="주가 (₩)", showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d', side='right', row=1, col=1)
            fig.update_yaxes(title_text="OBV Volume", showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d', side='right', row=2, col=1)
            fig.update_xaxes(showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d', rangeslider_visible=False)
            
            with st.container(border=True): st.plotly_chart(fig, use_container_width=True)
            
            if len(plot_hist_1y) >= 60:
                lookback = 60
                recent_price_trend = (plot_hist_1y['Close'].iloc[-1] - plot_hist_1y['Close'].iloc[-lookback]) / plot_hist_1y['Close'].iloc[-lookback] * 100
                obv_start = plot_hist_1y['OBV'].iloc[-lookback]
                obv_end = plot_hist_1y['OBV'].iloc[-1]
                obv_trend = obv_end - obv_start
                
                if recent_price_trend > 2.0 and obv_trend < 0:
                    obv_color = "#f85149" 
                    obv_status = "🚨 [경고] 가짜 반등 및 세력 물량 떠넘기기 (분산)"
                    obv_desc = "최근 3개월(60일)간 주가는 올랐거나 버티고 있지만, 실제 매집량(OBV)은 오히려 떨어지는 중임.<br><br>세력들이 주가를 띄워놓고 개인들에게 비싸게 넘기며 탈출 중일 확률이 높은 아주 위험한 자리임."
                    box_style = "border-left: 4px solid #f85149; background-color: rgba(248, 81, 73, 0.1);"
                elif recent_price_trend < -2.0 and obv_trend > 0:
                    obv_color = "#3fb950" 
                    obv_status = "🌟 [기회] 스마트머니 은밀한 매집 (다이버전스)"
                    obv_desc = "최근 3개월(60일)간 주가는 떨어지는데, 실제 매집량(OBV)은 꾸준히 오르는 중임.<br><br>개인들이 겁먹고 던지는 물량을 큰손(세력)들이 바닥에서 조용히 쓸어 담고 있는 강력한 매수 신호임."
                    box_style = "border-left: 4px solid #3fb950; background-color: rgba(63, 185, 80, 0.1);"
                elif recent_price_trend >= -2.0 and obv_trend >= 0:
                    obv_color = "#29b6f6" 
                    obv_status = "📈 [안정] 건전한 우상향 추세 (추세 확증)"
                    obv_desc = "주가와 매집량(OBV)이 함께 안정적으로 오르는 중임.<br><br>거래량이 든든하게 받쳐주는 건강한 상승장임.<br><br>큰손(세력)들도 주식을 팔지 않고 계속 쥐고 가는 중임."
                    box_style = "border-left: 4px solid #29b6f6; background-color: rgba(41, 182, 246, 0.1);"
                else:
                    obv_color = "#8b949e" 
                    obv_status = "📉 [위험] 강력한 하락세 및 세력 이탈 (투매)"
                    obv_desc = "주가와 매집량(OBV)이 모두 밑으로 곤두박질치는 중임.<br><br>세력과 기관들이 앞다투어 주식을 던지며 탈출 중임.<br><br>떨어지는 칼날을 맨손으로 잡으면 절대 안 되는 위험한 차트임."
                    box_style = "border-left: 4px solid #8b949e; background-color: rgba(139, 148, 158, 0.1);"
                    
                st.markdown(f"""
<div style="padding: 15px; border-radius: 5px; margin-top: -10px; margin-bottom: 20px; {box_style}">
<h4 style="margin-top: 0; color: {obv_color};">{obv_status}</h4>
<p style="margin-bottom: 0; font-size: 0.95rem; color: #c9d1d9; line-height: 1.6;">{obv_desc}</p>
</div>
""", unsafe_allow_html=True)
                
            if not df_wk.empty:
                plot_df_wk = df_wk.copy()

                st.markdown("<br><br>### 🔭 7. 주봉차트 타점 발생기", unsafe_allow_html=True)
                st.caption("※ 차트 확대/이동 후 화면이 틀어졌다면, 차트 빈 공간을 **'더블클릭'**하여 1초 만에 원상복구 하세요!")
                
                fig_wk = go.Figure()
                fig_wk.add_trace(go.Candlestick(x=plot_df_wk.index, open=plot_df_wk['Open'], high=plot_df_wk['High'], low=plot_df_wk['Low'], close=plot_df_wk['Close'], increasing_line_color='#ef5350', decreasing_line_color='#42a5f5', name=f"{company_name} 주봉"))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk.index, y=plot_df_wk['MA10'], mode='lines', line=dict(color='#ab47bc', width=1.5), name='10주선'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk.index, y=plot_df_wk['MA20'], mode='lines', line=dict(color='#ffd600', width=1.5), name='20주선'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk.index, y=plot_df_wk['MA60'], mode='lines', line=dict(color='#00e676', width=2.5), name='60주선'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk.index, y=plot_df_wk['MA120'], mode='lines', line=dict(color='#8d6e63', width=1.5), name='120주선'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk.index, y=plot_df_wk['ATR_Stop'], mode='lines', line=dict(color='#ff9800', width=2, dash='dot'), name='ATR 스탑 방어선'))
                
                y_main = plot_df_wk[df_wk['Signal_Main']]['Low'] * 0.92
                y_re = plot_df_wk[df_wk['Signal_Reentry']]['Low'] * 0.92
                y_sell = plot_df_wk[df_wk['Signal_Sell']]['High'] * 1.08
                
                fig_wk.add_trace(go.Scatter(x=plot_df_wk[df_wk['Signal_Main']].index, y=y_main, mode='markers', marker=dict(symbol='triangle-up', color='red', size=20), name=' 매수 타점'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk[df_wk['Signal_Reentry']].index, y=y_re, mode='markers', marker=dict(symbol='triangle-up', color='#00e676', size=16), name=' 재진입 타점'))
                fig_wk.add_trace(go.Scatter(x=plot_df_wk[df_wk['Signal_Sell']].index, y=y_sell, mode='markers', marker=dict(symbol='triangle-down', color='#29b6f6', size=16), name=' 매도 타점'))
                
                fig_wk.update_layout(
                    xaxis_rangeslider_visible=False, height=650, margin=dict(l=0, r=0, t=10, b=0),
                    template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d'),
                    yaxis=dict(showgrid=True, gridcolor='#30363d', zerolinecolor='#30363d', side='right', tickprefix="₩"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                with st.container(border=True): st.plotly_chart(fig_wk, use_container_width=True)

                st.markdown("""
<div style="background-color: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; margin-top: 20px;">
<h3 style="margin-top: 0; color: #e6edf3; font-size: 1.5rem;">💡 실전 매매 시나리오 가이드</h3>
<p style="color: #8b949e; font-size: 1.05rem; margin-bottom: 20px; line-height: 1.6;">차트에서 <b>'매수 타점(▲)'</b> 발생 시, 위쪽의 <b>'TOTAL SCORE (퀀트 스코어)'</b>에 따라 아래 2가지 시나리오로 기계적 대응을 권장함.</p>
<div style="border-left: 5px solid #ef5350; background-color: rgba(239, 83, 80, 0.05); padding: 15px 20px; margin-bottom: 15px; border-radius: 0 8px 8px 0;">
<h4 style="margin: 0 0 10px 0; color: #ef5350; font-size: 1.2rem;">🔥 시나리오 A (우량주 추세 매매) : 주봉 매수 신호 ➕ 스코어 8~10점</h4>
<p style="margin: 0 0 5px 0; color: #c9d1d9; font-size: 1.0rem; line-height: 1.6;"><b>• 상태:</b> 기업의 가치(수익성/저평가)와 차트의 돈 흐름이 완벽히 일치하는 최고의 매수 타이밍임.</p>
<p style="margin: 0; color: #c9d1d9; font-size: 1.0rem; line-height: 1.6;"><b>• 대응:</b> 비중을 실어서 매수하되, 변동성이 큰 한국 시장 특성상 무작정 장기투자하기보다 오름세가 꺾일 때(예: 주봉 10주선 이탈 시) 팔아서 수익을 챙기는 <b>'추세 매매'</b> 전략이 가장 안전함.</p>
</div>
<div style="border-left: 5px solid #29b6f6; background-color: rgba(41, 182, 246, 0.05); padding: 15px 20px; border-radius: 0 8px 8px 0;">
<h4 style="margin: 0 0 10px 0; color: #29b6f6; font-size: 1.2rem;">🤔 시나리오 B (단기 수급/테마 매매) : 주봉 매수 신호 ➕ 스코어 4점 이하</h4>
<p style="margin: 0 0 5px 0; color: #c9d1d9; font-size: 1.0rem; line-height: 1.6;"><b>• 상태:</b> 기업 가치는 부실하거나 비싸지만, 세력의 돈이 단기적으로 강하게 들어온 전형적인 테마/급등주 패턴임.</p>
<p style="margin: 0; color: #c9d1d9; font-size: 1.0rem; line-height: 1.6;"><b>• 대응:</b> 반드시 차트의 <b>'ATR 스탑(점선 방어선)'</b>을 칼같이 지키고, 철저하게 짧게 먹고 빠지는 단기 매매로만 접근해야 함.</p>
</div>
</div>
""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 🤖 전문가 핵심 지표 브리핑 (Tier 1)")
            if st.button("✨ 퀀트 데이터 기반 AI 분석 보고서 작성", type="primary", width="stretch"):
                with st.spinner(f"[{company_name}]의 수급 데이터와 4차원 매트릭스를 분석하여 AI 브리핑을 작성 중입니다... 🧠"):
                    try:
                        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                        model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"temperature": 0.7, "max_output_tokens": 8000})
                        ai_median_pe = f"{median_pe:.2f}배" if not peer_df.empty else "데이터 없음"
                        
                        prompt = f"""
                        당신은 월스트리트와 여의도를 섭렵한 최고의 수석 퀀트 애널리스트입니다. 
                        제공된 [{company_name}]의 팩트 데이터와 당신이 보유한 기업 지식을 종합하여, 
                        아래 [지정된 리포트 양식]에 맞춰 완벽한 네이버 블로그용 심층 분석 보고서를 작성해 주세요.

                        [분석용 기초 데이터]
                        - 퀀트 시스템 점수: 10점 만점에 {score}점 ({judgment})
                        - 적용 모델: {model_used} / 외국인 소진율 {frgn_hold_str}, 최근 5일 외인 {frgn_5d}주, 기관 {inst_5d}주 순매수
                        - 펀더멘털: ROE {roe*100:.1f}% / 배당성향 {payout_ratio*100:.1f}%
                        - 밸류에이션: 선행 PER {forward_pe}배, PBR {pbr}배, P/S {ps_ratio}배
                        - 동종 업계(경쟁사) 중앙값: PER {ai_median_pe}, P/B {median_pb}배

                        [🚨 작성 규칙]
                        1. 시작: "대표님, [{company_name}] 4차원 매트릭스 및 수급 종합 분석 보고드립니다."
                        2. 어투: 문장 끝은 반드시 "~함", "~임", "~됨", "~기대됨" 등 간결한 보고서체로 작성할 것. (예: 저평가 상태임. 주의가 필요함.)
                        3. 내용 밀도: 각 항목의 '- 분석 요약:'과 '- 핵심 근거:' 사이에는 절대 빈 줄(엔터)을 넣지 말고 바로 위아래로 붙여서 출력할 것.
                        4. 기호 통제: 이모지는 제목에만 쓰고 본문에는 절대 쓰지 말 것.
                        5. 해시태그 규칙: "블로그용 해시태그" 같은 설명 문구는 절대 쓰지 말고, 오직 태그만 맨 마지막에 쉼표(,) 없이 빈칸(스페이스바)으로 한 칸씩만 띄워서 나열할 것.

                        [지정된 리포트 양식]
                        ### 1. 비즈니스 모델 및 경제적 해자 : [ A / B / C ] 등급
                        - **분석 요약:** (무엇으로 돈을 버는지, 해자의 종류와 대체 불가능한 경쟁 우위 기술력을 작성)
                        - **핵심 근거:** (독점력, 네트워크 효과 등 명확한 근거 작성)

                        ### 2. 재무 건전성 및 수익성 (Alpha Spread 기준) : [ A / B / C ] 등급
                        - **분석 요약:** (마진율, ROE, 부채비율 등 재무적 안전성과 수익 창출 능력을 작성)
                        - **핵심 근거:** (동종 업계 대비 마진율 등)

                        ### 3. 경영진 및 주주 거버넌스 : [ A / B / C ] 등급
                        - **분석 요약:** (자본 배치 능력, 배당 및 주주 환원 정책의 일관성을 작성)
                        - **핵심 근거:** (꾸준한 배당 성장, 자사주 매입 이력 등)

                        ### 4. 밸류에이션 및 안전마진 (Finbox 기준) : [ A / B / C ] 등급
                        - **분석 요약:** (현재 주가가 내재 가치 대비 저평가인지, 역사적 멀티플 하단인지 작성)
                        - **핵심 근거:** (적용 모델 기준 내재 가치 등 팩트 서술)

                        ### 5. 촉매제(Catalyst) 및 리스크 : [ A / B / C ] 등급
                        - **분석 요약:** (주가를 끌어올릴 호재 모멘텀과 발목을 잡을 위험 요소를 작성)
                        - **핵심 근거:** (신제품 출시, 거시 경제 취약성 등)

                        ### 6. 동종 업계 멀티플 비교
                        - (경쟁사 대비 PER, PBR 수준을 비교하여 상대적 매력도 판정)

                        ### 7. 주요 판매처 및 밸류체인 확인
                        - (핵심 고객사와 공급망 내 위치 설명)

                        ---
                        ### 🏆 최종 종합 등급 : [ A / B / C ]
                        - **투자 결론:** (종합 매력도 요약)
                        - **트레이딩 전략:** (진입 타점 및 대응책)

                        #{company_name}주가 #{company_name}전망 #{company_name}실적 #실전매매 #주식분석 #퀀트투자
                        """
                        response = model.generate_content(prompt)
                        st.success("✅ 종합 브리핑 완료!")
                        with st.container(border=True):
                            clean_text = response.text
                            clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', clean_text)
                            clean_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean_text)
                            clean_text = clean_text.replace("*", "")
                            clean_text = clean_text.replace('\n', '<br>')
                            
                            st.markdown(f"""
<div style="font-size: 20px; line-height: 1.8; color: #e6edf3; padding: 10px;">
{clean_text}
</div>
""", unsafe_allow_html=True)
                    except Exception as e: 
                        st.error(f"🚨 AI 오류: {e}")

    except Exception as e:
        st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
