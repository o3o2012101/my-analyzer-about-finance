import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="💰", layout="wide")

# --- 2. 核心 CSS 修復：對齊、排行榜視覺、工具列顯示 ---
st.markdown("""
    <style>
    /* 1. 儲存區域：強制輸入框與按鈕底端對齊 */
    [data-testid="column"] {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }
    
    /* 2. 排行榜按鈕：移除藍點，兩行顯示，加強 Feel */
    .stButton > button {
        height: 75px !important;
        border-radius: 12px !important;
        border: 1px solid #E0E0E0 !important;
        background-color: #F8F9FB !important;
        line-height: 1.3 !important;
    }
    .stButton > button:hover {
        border-color: #4A90E2 !important;
        background-color: #FFFFFF !important;
    }
    
    /* 3. 確定上傳按鈕樣式 */
    button[kind="primary"] {
        background-color: #4A90E2 !important;
        color: white !important;
        height: 45px !important;
        font-weight: bold !important;
    }

    /* 4. 確保表格工具列 (搜尋🔍、篩選) 絕對顯示 */
    [data-testid="stElementToolbar"] {
        display: flex !important;
        visibility: visible !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 連線與規則載入 (功能保留) ---
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

# 確保 Session 初始化
if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 自動分類邏輯 (功能保留) ---
def perform_auto_classify(df):
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            if any(k in desc_lower for k in keywords): return cat
        return "待分類"
    new_df = df.copy()
    new_df['類別'] = new_df['消費明細'].apply(get_cat)
    return new_df

# --- 5. 側邊欄：功能選單 (歷史查詢+規則隱藏) ---
with st.sidebar:
    st.title("📂 功能選單")
    
    # 功能：規則隱藏選單
    with st.expander("📝 查看目前分類規則", expanded=False):
        if st.session_state.opts:
            st.write(", ".join(st.session_state.opts))
        if st.button("🔄 同步最新雲端規則"):
            st.session_state.opts, st.session_state.rules = load_rules()
            st.rerun()

    st.divider()
    
    # 功能：歷史紀錄查詢
    st.subheader("🔎 歷史紀錄查詢")
    search_m = st.text_input("輸入年份月份 (YYYYMM)", placeholder="例如 202401")
    if st.button("載入歷史資料"):
        try:
            st.session_state.working_df = conn.read(worksheet=search_m, ttl="0s")
            st.success(f"已載入 {search_m} 資料")
            st.rerun()
        except: st.error("查無此分頁，請確認分頁名稱")

# --- 6. 彈出對話框 (Dialog 功能保留) ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_detail_dialog(cat, data):
    st.subheader(f"類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)
    st.metric("該類別合計", f"${int(d['金額'].sum()):,}")

# --- 7. 主頁面流程 (6步驟嚴格執行) ---
st.title("🤖 Richart AI 自動記帳系統")

# Step 1: 上傳與自動分類
if 'working_df' not in st.session_state:
    u_file = st.file_uploader("📥 第一步：上傳 Richart Excel 檔案", type=["xlsx"])
    if u_file:
        raw_data = pd.read_excel(u_file, header=None)
        h_idx = next(i for i, r in raw_data.iterrows() if "消費明細" in "".join(map(str, r)))
        df = pd.read_excel(u_file, header=h_idx)
        df.columns = [str(c).strip() for c in df.columns]
        new_df = df.iloc[:, [0,1,2]].copy()
        new_df.columns = ['日期', '消費明細', '金額']
        new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
        # 執行自動分類
        st.session_state.working_df = perform_auto_classify(new_df)
        st.rerun()

if 'working_df' in st.session_state:
    # (1) 明細管理區
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新跑自動分類"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    # 此編輯器保留搜尋 (🔍) 與排序功能
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=st.session_state.opts + ["待分類"], width="medium"),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # (2) 排行榜 (4欄一列, 1-3名獎牌, 藍色文字感金額)
    st.divider()
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    
    num_cols = 4
    for i in range(0, len(sum_df), num_cols):
        batch = sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (orig_idx, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                medal = "🥇 " if orig_idx == 0 else "🥈 " if orig_idx == 1 else "🥉 " if orig_idx == 2 else ""
                # 這裡的藍色是透過樣式引導，第一行類別，第二行金額
                label = f"{medal}{row['類別']}\n$ {int(row['金額']):,}"
                if st.button(label, key=f"btn_{row['類別']}", use_container_width=True):
                    show_detail_dialog(row['類別'], edited_df)

    # (3) 圓餅圖
    st.divider()
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # (4) 儲存區 (分頁名稱與按鈕絕對對齊)
    st.divider()
    st.markdown("### 💾 4. 命名並儲存至雲端")
    save_row = st.columns([4, 6])
    with save_row[0]:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with save_row[1]:
        # 因 CSS justify-content: flex-end，按鈕會與輸入框底部對齊
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.success(f"✅ 資料已成功儲存至分頁：{target_name}")

    st.write("")
    if st.button("🗑️ 清空數據並重新上傳"):
        del st.session_state.working_df
        st.rerun()
