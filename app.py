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

# --- 2. 核心視覺與對齊修復 (CSS) ---
st.markdown("""
    <style>
    /* 1. 強制導入圓體字型 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700;900&display=swap');
    
    html, body, [class*="css"], p, span, button {
        font-family: 'Noto Sans TC', sans-serif !important;
    }

    /* 2. 排行榜按鈕美化 (名次與金額藍字) */
    .stButton > button {
        width: 100% !important;
        border-radius: 15px !important;
        height: 85px !important; 
        background-color: #FFFFFF !important;
        border: 2px solid #E8EEF5 !important;
        color: #333333 !important;
        transition: all 0.3s ease;
        padding: 10px !important;
    }
    .stButton > button:hover {
        border-color: #4A90E2 !important;
        background-color: #F8FBFF !important;
        transform: translateY(-2px);
    }
    
    /* 藍字金額樣式 (透過 markdown 注入或直接設定按鈕內文字) */
    .blue-price {
        color: #4A90E2;
        font-weight: 900;
        font-size: 1.1em;
    }

    /* 3. 儲存區域對齊修復 (關鍵：讓 Row 內元素底端對齊) */
    [data-testid="stHorizontalBlock"] {
        align-items: flex-end !important;
    }

    /* 儲存按鈕文字顏色強化 (純白) */
    button[kind="primary"] {
        background-color: #4A90E2 !important;
        color: white !important;
        font-weight: 700 !important;
        border: none !important;
    }
    
    /* 側邊欄圓角化 */
    [data-testid="stSidebar"] {
        background-color: #F9FAFB;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 連線與規則加載 (保留現有功能) ---
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

# --- 4. 自動分類邏輯 (保留現有功能) ---
def perform_auto_classify(df):
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            if any(k in desc_lower for k in keywords): return cat
        return "待分類"
    new_df = df.copy()
    new_df['類別'] = new_df['消費明細'].apply(get_cat)
    return new_df

# --- 5. 側邊欄：歷史查詢 ---
with st.sidebar:
    st.markdown("## 📂 功能選單")
    if st.button("🔄 同步雲端規則"):
        st.session_state.opts, st.session_state.rules = load_rules_from_cloud()
        st.rerun()
    st.divider()
    st.markdown("### 🔎 歷史紀錄查詢")
    search_month = st.text_input("輸入年份月份 (YYYYMM)")
    if st.button("載入歷史明細"):
        try:
            old_df = conn.read(worksheet=search_month, ttl="0s")
            st.session_state.working_df = old_df
            st.rerun()
        except: st.error("查無資料")

# --- 6. 彈出對話框 (Dialog) ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_detail_dialog(cat, data):
    st.markdown(f"### 類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)
    st.metric("該類別總額", f"${int(d['金額'].sum()):,}")

# --- 7. 主頁面流程 (按順序排列) ---
st.markdown("# 🤖 Richart AI 全自動記帳系統")

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
        st.session_state.working_df = perform_auto_classify(new_df)
        st.rerun()

if 'working_df' in st.session_state:
    # (1) 明細管理與類別修正 (置頂欄位)
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新套用最新規則"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    all_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=all_opts, width="medium")},
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # 連動數據
    current_sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

    st.divider()

    # (2) 排行榜 (對齊 + 名次 + 藍字金額)
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    num_cols = 6
    for i in range(0, len(current_sum_df), num_cols):
        batch = current_sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (idx_df, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                rank_num = idx_df + 1 # 名次從 1 開始
                # 這裡透過 Markdown 模擬藍字視覺效果 (按鈕標籤不支援 HTML，故直接用符號與金額組合)
                btn_label = f"No.{rank_num} {row['類別']}\n💰 {int(row['金額']):,}"
                if st.button(btn_label, key=f"r_{row['類別']}", use_container_width=True):
                    show_detail_dialog(row['類別'], edited_df)

    st.divider()

    # (3) 圓餅圖
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(current_sum_df, values='金額', names='類別', hole=0.5, 
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # (4) 命名並儲存至雲端 (完全對齊修復)
    st.markdown("### 💾 4. 命名並儲存至雲端")
    s_col1, s_col2 = st.columns([4, 6]) # 調整比例讓對齊更美觀
    with s_col1:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with s_col2:
        # 下方按鈕將會因為 CSS 中的 align-items: flex-end 而自動與輸入框底端對齊
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.success(f"✅ 已成功儲存：{target_name}")

    st.write("") # 增加一點間距
    if st.button("🗑️ 清空數據"):
        del st.session_state.working_df
        st.rerun()
