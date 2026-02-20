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

# --- 2. 核心 CSS 修復：字體與按鈕對齊 ---
st.markdown("""
    <style>
    /* 引入更接近源泉圓體的 Google 圓體字型 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700&family=ZCOOL+KuaiLe&display=swap');
    
    /* 全域字體強制套用圓體風格 */
    html, body, [class*="css"], .stMarkdown, p, button {
        font-family: 'Noto Sans TC', sans-serif !important;
        letter-spacing: 0.5px;
    }

    /* 標題加重圓體感 */
    h1, h2, h3 {
        font-family: 'Noto Sans TC', sans-serif !important;
        font-weight: 800 !important;
        color: #31333F !important;
    }

    /* --- 排行榜按鈕對齊修復 (強制 Grid) --- */
    .ranking-container {
        display: grid;
        grid-template-columns: repeat(6, 1fr); /* 嚴格 6 欄對齊 */
        gap: 12px;
        margin-bottom: 20px;
    }

    /* 覆蓋 Streamlit 預設按鈕樣式 */
    .stButton > button {
        width: 100% !important;
        border-radius: 12px !important;
        height: 65px !important; /* 固定高度防止行差 */
        background-color: #F0F4F8 !important;
        border: 1px solid #D1D9E6 !important;
        color: #1A1A1A !important;
        font-weight: 700 !important;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 1.2 !important;
    }

    .stButton > button:hover {
        border-color: #4A90E2 !important;
        background-color: #EBF3FF !important;
    }

    /* 儲存按鈕顏色強化 */
    button[kind="primary"] {
        background-color: #4A90E2 !important;
        color: white !important;
        height: 50px !important;
    }
    
    /* 隱藏 DataEditor 多餘空白 */
    [data-testid="stDataEditor"] { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 連線與規則加載 ---
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
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [str(c).strip() for c in df.columns]
        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules_from_cloud()

# --- 4. 自動分類邏輯 ---
def perform_auto_classify(df):
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            if any(k in desc_lower for k in keywords): return cat
        return "待分類"
    new_df = df.copy()
    new_df['類別'] = new_df['消費明細'].apply(get_cat)
    return new_df

# --- 5. 側邊欄 ---
with st.sidebar:
    st.markdown("## 📂 功能選單")
    with st.expander("📝 規則狀態查詢", expanded=False):
        if st.session_state.opts:
            st.success(f"已讀取 {len(st.session_state.opts)} 個分類")
            if st.button("🔄 同步雲端規則"):
                st.session_state.opts, st.session_state.rules = load_rules_from_cloud()
                st.rerun()
    st.divider()
    st.markdown("### 🔎 歷史紀錄查詢")
    search_month = st.text_input("輸入年份月份 (YYYYMM)", key="search_input")
    if st.button("載入歷史明細", key="load_hist"):
        try:
            old_df = conn.read(worksheet=search_month, ttl="0s")
            st.session_state.working_df = old_df
            st.rerun()
        except: st.error("查無資料")

# --- 6. 彈出對話框 ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_detail_dialog(cat, data):
    st.markdown(f"### 類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)
    st.metric("該類別總額", f"${int(d['金額'].sum()):,}")

# --- 7. 主頁面流程 (嚴格 6 步驟) ---
st.markdown("# 🤖 Richart AI 自動記帳系統")

# Step 1: 上傳
if 'working_df' not in st.session_state:
    u_file = st.file_uploader("📥 上傳 Excel 明細開始分析", type=["xlsx"])
    if u_file:
        raw_data = pd.read_excel(u_file, header=None)
        h_idx = next(i for i, r in raw_data.iterrows() if "消費明細" in "".join(map(str, r)))
        df = pd.read_excel(u_file, header=h_idx)
        df.columns = [str(c).strip() for c in df.columns]
        new_df = df.iloc[:, [0,1,2]].copy()
        new_df.columns = ['日期', '消費明細', '金額']
        new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
        st.session_state.working_df = perform_auto_classify(new_df)
        st.rerun()

if 'working_df' in st.session_state:
    # (1) 明細管理 (Step 3 手動調整)
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新套用規則 (全表更新)", key="reclassify_btn"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    all_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=all_opts, width="medium")},
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # (Step 4 連動計算)
    current_sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

    st.divider()

    # (2) 排行榜 (對齊修復版)
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    
    # 解決行差：使用固定欄位數，不足的補空位確保 Grid 完整
    num_cols = 6
    for i in range(0, len(current_sum_df), num_cols):
        batch = current_sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (_, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                label = f"{row['類別']}\n${int(row['金額']):,}"
                if st.button(label, key=f"rank_{row['類別']}", use_container_width=True):
                    show_detail_dialog(row['類別'], edited_df)

    st.divider()

    # (3) 圓餅圖
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(current_sum_df, values='金額', names='類別', hole=0.5, 
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # (4) 命名與匯入 (Step 5)
    st.markdown("### 💾 4. 命名並儲存至雲端")
    s_col1, s_col2 = st.columns([3, 7])
    with s_col1:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with s_col2:
        st.write("") 
        st.write("")
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.success(f"✅ 已儲存至分頁：{target_name}")

    if st.button("🗑️ 清空數據"):
        del st.session_state.working_df
        st.rerun()
