import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="🤖", layout="wide")

# --- 2. 初始化 gspread (增加連線偵測) ---
@st.cache_resource
def get_gspread_client():
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"❌ 無法連線至 Google：{e}")
        return None

gc = get_gspread_client()

# --- 3. 穩定讀取規則 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def safe_load_rules():
    """安全載入規則，若失敗則回傳預設值，不卡死畫面"""
    try:
        # 使用 ttl=0 確保不抓舊資料，但若報錯則抓緩存
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        
        # 建立清單與字典
        cats = rules_df['分類名稱'].dropna().unique().tolist()
        cat_list = [str(c).strip() for c in cats if str(c).strip() != 'nan']
        
        rules_dict = {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                      for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
        
        return cat_list, rules_dict
    except Exception as e:
        st.warning(f"⚠️ 規則讀取稍有延遲，請稍後嘗試重整。")
        return [], {}

# 初始化 Session State
if 'category_options' not in st.session_state:
    c_list, r_dict = safe_load_rules()
    st.session_state.category_options = c_list
    st.session_state.category_rules = r_dict

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    
    st.divider()
    if st.button("🔄 強制更新規則選單"):
        c_list, r_dict = safe_load_rules()
        st.session_state.category_options = c_list
        st.session_state.category_rules = r_dict
        st.success("規則已更新！")
        time.sleep(1)
        st.rerun()
        
    with st.expander("🛠️ 目前規則預覽"):
        st.write(st.session_state.category_rules)

st.title(f"📊 {target_month} 消費狀態分析")

# --- 5. 分頁操作 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
        def get_or_create_worksheet(name):
            try: return sh.worksheet(name)
            except: return sh.add_worksheet(title=name, rows="1000", cols="20")

        # 讀取當月資料
        try:
            df_month = conn.read(worksheet=target_month, ttl="0s")
            if not df_month.empty:
                if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
                    st.session_state.working_df = df_month
                    st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        # 上傳邏輯
        if 'working_df' not in st.session_state:
