import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="💰", layout="wide")

# --- 2. 質感 CSS 控制 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    /* 排行榜按鈕樣式：限制大小，整齊排列 */
    .stButton>button {
        border-radius: 12px;
        min-height: 70px;
        background: #F8F9FA;
        border: 1px solid #E0E0E0;
        transition: 0.2s;
    }
    .stButton>button:hover { border-color: #4A90E2; background: #FFFFFF; }
    /* 編輯器邊框 */
    [data-testid="stDataEditor"] { border: 2px solid #F0F2F6; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 連線與規則加載 (確保規則可見) ---
@st.cache_resource
def get_gc():
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials)
    except: return None

gc = get_gc()
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules_from_cloud():
    """強制從雲端抓取最新規則並返回"""
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [str(c).strip() for c in df.columns]
        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

# 初始加載規則
if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules_from_cloud()

# --- 4. 核心自動分類函數 ---
def perform_auto_classify(df):
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            if any(k in desc_lower for k in keywords): return cat
        return "待分類"
    new_df = df.copy()
    new_df['類別'] = new_df['消費明細'].apply(get_cat)
    return new_df

# --- 5. 側邊欄：規則狀態與歷史搜尋 ---
with st.sidebar:
    st.title("📂 功能選單")
    
    with st.expander("📝 目前抓取規則狀態", expanded=True):
        if st.session_state.opts:
            st.success(f"已讀取 {len(st.session_state.opts)} 個分類")
            st.write("類別清單：", st.session_state.opts)
        else:
            st.error("⚠️ 抓不到分類！請檢查 Sheet1")
        if st.button("🔄 同步 Sheet1 最新規則"):
            st.session_state.opts, st.session_state.rules = load_rules_from_cloud()
            st.rerun()

    st.divider()
    
    st.subheader("🔎 歷史資料查詢")
    search_month = st.text_input("輸入年份月份 (YYYYMM)", placeholder="例如: 202601")
    if st.button("載入歷史明細"):
        try:
            old_df = conn.read(worksheet=search_month, ttl="0s")
            st.session_state.working_df = old_df
            st.success(f"成功載入 {search_month}！")
            st.rerun()
        except: st.error("找不到該分頁資料。")

# --- 6. 彈出視窗對話框 (Dialog) ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_detail_dialog(cat, data):
    st.subheader(f"類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)
    st.metric("該類別總額", f"${int(d['金額'].sum()):,}")

# --- 7. 主頁面流程 ---
st.title("🤖 Richart AI 全自動記帳系統")

# 步驟 1: 上傳與自動分類
if 'working_df' not in st.session_state:
    st.info("👋 請上傳本月消費明細 Excel 檔開始作業")
    u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
    if u_file:
        raw_data = pd.read_excel(u_file, header=None)
        h_idx = next(i for i, r in raw_data.iterrows() if "消費明細" in "".join(map(str, r)))
        df = pd.read_excel(u_file, header=h_idx)
        df.columns = [str(c).strip() for c in df.columns]
        c_d, c_m, c_a = next(c for c in df.columns if "日期" in c), next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c)
        
        # 整理基礎表格
        init_df = df[[c_d, c_m, c_a]].copy()
        init_df.columns = ['日期', '消費明細', '金額']
        init_df['日期'] = pd.to_datetime(init_df['日期']).dt.strftime('%Y-%m-%d')
        
        # 系統自動分類
        st.session_state.working_df = perform_auto_classify(init_df)
        st.rerun()

# 步驟 2~4: 編輯、即時連動、排行榜、圓餅圖
if 'working_df' in st.session_state:
    
    # 🔍 (1) 明細管理與類別修正 (置頂)
    st.markdown("### 🔍 1. 明細管理與類別修正")
    c_btn1, c_btn2 = st.columns([2, 8])
    with c_btn1:
        if st.button("🤖 重新套用最新規則", use_container_width=True):
            st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
            st.rerun()
    
    # 手動編輯器
    all_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=all_opts, width="medium")},
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # 重要：即時連動下方的數據來源
    current_sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

    st.divider()

    # 🏆 (2) 排行榜 (點擊看明細)
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊卡片看明細)")
    cols = st.columns(6)
    for i, row in current_sum_df.iterrows():
        with cols[i % 6]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💰"
            # 點擊按鈕觸發 Dialog
            if st.button(f"{icon} {row['類別']}\n${int(row['金額']):,}", key=f"rank_{row['類別']}", use_container_width=True):
                show_detail_dialog(row['類別'], edited_df)

    st.divider()

    # 🥧 (3) 圓餅圖 (置底獨佔一行)
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(current_sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(height=500)
    st.plotly_chart(fig, use_container_width=True)

    # 💾 (4) 匯出儲存
    st.divider()
    st.markdown("### 💾 4. 命名並儲存至雲端")
    s_col1, s_col2 = st.columns([3, 7])
    with s_col1:
        target_name = st.text_input("分頁名稱 (預設當前月份)", value=datetime.now().strftime("%Y%m"))
    with s_col2:
        st.write("") # 對齊
        st.write("")
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.session_state.working_df = edited_df # 儲存完保持當前狀態
                st.success(f"✅ 已成功儲存至分頁：{target_name}")

    if st.button("🗑️ 清空並重新上傳"):
        del st.session_state.working_df
        st.rerun()
