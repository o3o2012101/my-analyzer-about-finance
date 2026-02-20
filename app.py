import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="Richart AI Pro", page_icon="💰", layout="wide")

# --- 2. CSS 樣式優化 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .stButton>button { border-radius: 10px; min-height: 50px; }
    [data-testid="stDataEditor"] { border: 2px solid #F0F2F6; border-radius: 10px; }
    h3 { color: #4A90E2; padding-top: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線 ---
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

def load_rules():
    """載入 Sheet1 的分類規則"""
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [str(c).strip() for c in df.columns]
        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

# 預先載入規則
if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 自動分類邏輯 ---
def auto_classify(df):
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            if any(k in desc_lower for k in keywords): return cat
        return "待分類"
    new_df = df.copy()
    new_df['類別'] = new_df['消費明細'].apply(get_cat)
    return new_df

# --- 5. 側邊欄：歷史資料查詢 ---
with st.sidebar:
    st.header("🔍 歷史資料查詢")
    search_month = st.text_input("輸入年份月份 (如: 202601)", placeholder="YYYYMM")
    if st.button("🔎 從雲端載入資料"):
        try:
            old_df = conn.read(worksheet=search_month, ttl="0s")
            if not old_df.empty:
                st.session_state.working_df = old_df
                st.session_state.target_month_name = search_month
                st.success(f"已成功載入 {search_month} 資料！")
                st.rerun()
            else: st.warning("找不到該月份資料。")
        except: st.error("載入失敗，請檢查分頁名稱。")
    
    st.divider()
    if st.button("🔄 同步 Sheet1 最新規則"):
        st.session_state.opts, st.session_state.rules = load_rules()
        st.success("規則已更新！")

# --- 6. 主頁面流程 ---
st.title("💰 Richart 消費分析與自動分類")

# 步驟 1: 上傳 Excel
if 'working_df' not in st.session_state:
    st.info("👋 你好！請先上傳本月 Richart 消費明細 Excel 表。")
    u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
    if u_file:
        raw = pd.read_excel(u_file, header=None)
        h_idx = next(i for i, r in raw.iterrows() if "消費明細" in "".join(map(str, r)))
        df_raw = pd.read_excel(u_file, header=h_idx)
        df_raw.columns = [str(c).strip() for c in df_raw.columns]
        c_d, c_m, c_a = next(c for c in df_raw.columns if "日期" in c), next(c for c in df_raw.columns if "明細" in c), next(c for c in df_raw.columns if "金額" in c)
        
        # 初步整理
        new_df = df_raw[[c_d, c_m, c_a]].copy()
        new_df.columns = ['日期', '消費明細', '金額']
        new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
        
        # 步驟 2: 系統自動跑分類
        st.session_state.working_df = auto_classify(new_df)
        st.rerun()

# 步驟 3 & 4: 手動調整與自動連動圖表
if 'working_df' in st.session_state:
    w_df = st.session_state.working_df
    
    # 🔍 明細管理區 (放在最上方)
    st.markdown("### 🔍 步驟 1：確認與手動調整分類")
    
    col_ctrl1, col_ctrl2 = st.columns([2, 8])
    with col_ctrl1:
        if st.button("🤖 重新套用最新規則", use_container_width=True):
            st.session_state.working_df = auto_classify(st.session_state.working_df)
            st.rerun()
    with col_ctrl2:
        st.caption("💡 修改「分類修正」欄位後，下方的排行榜與圖表會自動更新。")

    display_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
    
    # 使用 data_editor 實現手動調整
    edited_df = st.data_editor(
        w_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=display_opts, width="medium")},
        use_container_width=True, hide_index=True, key="main_editor"
    )
    
    # 這裡實現「自動連動」：直接拿編輯後的資料算圖表
    sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

    # 🏆 排行榜
    st.markdown("### 🏆 步驟 2：支出排行榜 (即時連動)")
    cols = st.columns(6)
    for i, row in sum_df.iterrows():
        with cols[i % 6]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💰"
            st.button(f"{icon} {row['類別']}\n${int(row['金額']):,}", key=f"r_{row['類別']}", use_container_width=True)

    # 🥧 圓餅圖
    st.markdown("### 🥧 步驟 3：支出佔比分析 (即時連動)")
    fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(height=500, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # 步驟 5: 匯出儲存
    st.divider()
    st.markdown("### 💾 步驟 4：儲存本月資料至 Google Sheet")
    save_col1, save_col2 = st.columns([3, 7])
    with save_col1:
        save_name = st.text_input("設定儲存的分頁名稱", value=datetime.now().strftime("%Y%m"), help="建議格式：YYYYMM")
    with save_col2:
        st.write("") # 為了對齊按鈕
        st.write("") 
        if st.button("🚀 確定存入雲端並命名", type="primary"):
            if gc:
                try:
                    sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                    try: sh.worksheet(save_name)
                    except: sh.add_worksheet(title=save_name, rows="1000", cols="20")
                    conn.update(worksheet=save_name, data=edited_df)
                    st.session_state.working_df = edited_df # 更新當前狀態
                    st.success(f"✅ 資料已成功儲存至分頁：{save_name}")
                except Exception as e:
                    st.error(f"儲存失敗：{e}")

    if st.button("🗑️ 清空當前資料重新開始"):
        del st.session_state.working_df
        st.rerun()
