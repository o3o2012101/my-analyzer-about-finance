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

# --- 2. 深度視覺優化 (包含源泉圓體與按鈕美化) ---
st.markdown("""
    <style>
    /* 引入源泉圓體 (使用類似風格的開源圓體) */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans TC', sans-serif; /* 預設使用 TC 圓體風格 */
    }

    /* 整體背景與標題 */
    .stApp { background-color: #FFFFFF; }
    h1, h2, h3 { color: #333333 !important; font-weight: 800 !important; }

    /* 排行榜卡片美化：縮小高度、強化顏色 */
    .stButton>button {
        border-radius: 12px !important;
        min-height: 50px !important; /* 縮小按鈕高度 */
        background-color: #F0F4F8 !important;
        border: 1px solid #D1D9E6 !important;
        color: #1A1A1A !important; /* 加深字體顏色 */
        font-weight: 700 !important;
        font-size: 15px !important;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        border-color: #4A90E2 !important;
        background-color: #E1E8F0 !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }

    /* 特別強化「儲存儲存」按鈕的對比度 */
    div[data-testid="stFormSubmitButton"] > button, 
    button[kind="primary"] {
        background: #4A90E2 !important;
        color: #FFFFFF !important; /* 確保字體是純白 */
        border: none !important;
    }
    
    /* 修正按鈕內文字過淺的問題 */
    .stButton p {
        color: inherit !important;
        font-weight: 700 !important;
    }

    /* 隱藏預設的 DataEditor 工具列以減少雜訊 */
    [data-testid="stDataEditor"] { border: 1px solid #E0E0E0; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線與規則 ---
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
    st.header("📂 功能選單")
    with st.expander("📝 規則狀態查詢", expanded=False):
        if st.session_state.opts:
            st.success(f"已讀取 {len(st.session_state.opts)} 個分類")
            if st.button("🔄 同步雲端規則"):
                st.session_state.opts, st.session_state.rules = load_rules_from_cloud()
                st.rerun()
    
    st.divider()
    st.subheader("🔎 歷史紀錄查詢")
    search_month = st.text_input("輸入年份月份 (YYYYMM)")
    if st.button("載入歷史明細"):
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

# --- 7. 主程式 (嚴格執行 6 步流程) ---
st.title("🤖 Richart AI 自動記帳系統")

# Step 1: 上傳與自動分類
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
        # 自動分類
        st.session_state.working_df = perform_auto_classify(new_df)
        st.rerun()

# Step 2~5: 編輯、即時圖表、排行榜
if 'working_df' in st.session_state:
    
    # (1) 明細管理與類別修正
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新套用最新規則", key="reclassify_btn"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    all_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=all_opts, width="medium")},
        use_container_width=True, hide_index=True, key="editor"
    )

    # 即時計算數據
    current_sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

    st.divider()

    # (2) 消費排行榜 (縮小版按鈕)
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    cols = st.columns(6)
    for i, row in current_sum_df.iterrows():
        with cols[i % 6]:
            # 按鈕內的文字強制加深
            btn_label = f"{row['類別']}\n${int(row['金額']):,}"
            if st.button(btn_label, key=f"r_{row['類別']}", use_container_width=True):
                show_detail_dialog(row['類別'], edited_df)

    st.divider()

    # (3) 支出比例分析 (圓餅圖)
    st.markdown("### 🥧 3. 支出比例分析")
    fig = px.pie(current_sum_df, values='金額', names='類別', hole=0.5, 
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # (4) 儲存至雲端 (修正按鈕字體淺的問題)
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
                st.success(f"✅ 已成功儲存：{target_name}")

    if st.button("🗑️ 清空並重新上傳"):
        del st.session_state.working_df
        st.rerun()
