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

# --- 2. 核心 CSS 修復：字體、按鈕對齊、藍字金額 ---
st.markdown("""
    <style>
    /* 引入強效圓體字型 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@500;700;900&family=ZCOOL+KuaiLe&display=swap');
    
    html, body, [class*="css"], p, span, button {
        font-family: 'Noto Sans TC', 'ZCOOL KuaiLe', sans-serif !important;
    }

    /* 標題樣式 */
    h1, h2, h3 { font-family: 'ZCOOL KuaiLe', sans-serif !important; color: #31333F !important; }

    /* --- 排行榜卡片美化 --- */
    .stButton > button {
        width: 100% !important;
        border-radius: 20px !important;
        height: 100px !important; 
        background-color: #E8EEF9 !important; /* 淡淡的藍色背景增加 Feel */
        border: 2px solid #D1D9E6 !important;
        transition: all 0.3s ease;
        display: block !important;
        padding: 10px !important;
    }
    
    .stButton > button:hover {
        border-color: #4A90E2 !important;
        background-color: #FFFFFF !important;
        transform: translateY(-3px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }

    /* 強制按鈕內第一行為類別，第二行為藍字金額 */
    .stButton > button div p {
        margin: 0 !important;
        line-height: 1.4 !important;
    }

    /* --- 儲存區域對齊修復 --- */
    /* 強制讓 Row 內部的所有組件底部對齊 */
    [data-testid="column"] {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }

    /* 確定上傳按鈕樣式 */
    button[kind="primary"] {
        background: linear-gradient(90deg, #4A90E2, #63A4FF) !important;
        color: white !important;
        font-weight: 700 !important;
        border: none !important;
        height: 45px !important; /* 固定高度以利對齊 */
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線與規則載入 (保留所有原功能) ---
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
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [str(c).strip() for c in df.columns]
        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

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

# --- 5. 側邊欄 ---
with st.sidebar:
    st.markdown("## 📂 功能選單")
    if st.button("🔄 同步雲端規則"):
        st.session_state.opts, st.session_state.rules = load_rules()
        st.rerun()
    st.divider()
    search_m = st.text_input("🔎 歷史紀錄查詢 (YYYYMM)")
    if st.button("載入歷史"):
        try:
            st.session_state.working_df = conn.read(worksheet=search_m, ttl="0s")
            st.rerun()
        except: st.error("查無資料")

# --- 6. 彈出對話框 ---
@st.dialog("📋 明細查看", width="large")
def show_detail(cat, data):
    st.markdown(f"### 類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)

# --- 7. 主頁面 (嚴格執行所有功能) ---
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
        st.session_state.working_df = auto_classify(new_df)
        st.rerun()

# 顯示與操作區
if 'working_df' in st.session_state:
    
    # (1) 明細管理
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新跑自動分類"):
        st.session_state.working_df = auto_classify(st.session_state.working_df)
        st.rerun()
    
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=st.session_state.opts + ["待分類"])},
        use_container_width=True, hide_index=True, key="editor"
    )

    # (2) 排行榜 (名次標籤 + 藍字金額)
    st.divider()
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    
    sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    num_cols = 6
    
    for i in range(0, len(sum_df), num_cols):
        batch = sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (original_idx, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                # 名次判斷：僅 1-3 名顯示獎牌
                rank_icon = ""
                if original_idx == 0: rank_icon = "🥇 "
                elif original_idx == 1: rank_icon = "🥈 "
                elif original_idx == 2: rank_icon = "🥉 "
                
                # 類別與金額分行顯示 (金額使用顏色符號或在標籤中加重)
                # 註：按鈕標籤不支援 HTML 顏色，我們用特殊符號與格式強化視覺
                btn_label = f"{rank_icon}{row['類別']}\n$ {int(row['金額']):,}"
                
                if st.button(btn_label, key=f"rank_{row['類別']}", use_container_width=True):
                    show_detail(row['類別'], edited_df)

    # (3) 圓餅圖
    st.divider()
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # (4) 儲存區 (絕對對齊版)
    st.divider()
    st.markdown("### 💾 4. 命名並儲存至雲端")
    
    # 建立一個容器確保內部組件對齊
    save_row = st.columns([4, 6])
    with save_row[0]:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with save_row[1]:
        # 這裡會因為 CSS 設定與輸入框底端對齊
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.success(f"✅ 已成功儲存至：{target_name}")

    st.write("")
    if st.button("🗑️ 清空所有數據"):
        del st.session_state.working_df
        st.rerun()
