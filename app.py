import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="🤖", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { 
        padding: 20px; border-radius: 15px; background-color: #F8F9FA; border: 1px solid #E9ECEF; 
        text-align: center; margin-bottom: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .rank-name { font-size: 1.1rem; color: #666; font-weight: 500; }
    .rank-price { font-size: 1.8rem; color: #4A90E2; font-weight: bold; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化 gspread ---
@st.cache_resource
def get_gspread_client():
    creds_info = st.secrets["connections"]["gsheets"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

gc = get_gspread_client()
sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])

# --- 3. 穩定讀取規則 (Sheet1) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def fetch_category_list():
    """強制獲取所有分類名稱清單，確保下拉選單不留白"""
    try:
        rules_df = conn.read(worksheet="Sheet1", ttl="0s") # 禁用快取確保即時
        rules_df.columns = [c.strip() for c in rules_df.columns]
        # 過濾掉空的分類
        cats = rules_df['分類名稱'].dropna().unique().tolist()
        return [str(c).strip() for c in cats if str(c).strip() != 'nan']
    except:
        return []

def load_rules_dict():
    """載入規則字典供自動分類使用"""
    try:
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except: return {}

# 將分類清單存在 session 中防止遺失
if 'category_options' not in st.session_state or not st.session_state.category_options:
    st.session_state.category_options = fetch_category_list()

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules_dict()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    
    st.divider()
    if st.button("🔄 強制更新規則選單"):
        st.session_state.category_options = fetch_category_list()
        st.session_state.category_rules = load_rules_dict()
        st.success("規則清單已重新載入！")
        st.rerun()
        
    with st.expander("🛠️ 目前規則預覽"):
        st.write(st.session_state.category_rules)

st.title(f"📊 {target_month} 消費狀態分析")

# --- 5. 自動讀取/建立分頁 ---
def get_or_create_worksheet(name):
    try: return sh.worksheet(name)
    except: return sh.add_worksheet(title=name, rows="1000", cols="20")

try:
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty:
        if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
            st.session_state.working_df = df_month
            st.session_state.curr_m = target_month
except:
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df
