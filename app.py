import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面設定 ---
st.set_page_config(page_title="個人月消費分析系統", page_icon="💰", layout="wide")

# --- 2. 核心 CSS 修復 ---
st.markdown("""
    <style>
    /* 儲存區域底部對齊 */
    [data-testid="column"] {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }
    
    /* 排行榜按鈕樣式 (兩行顯示) */
    .stButton > button {
        height: 75px !important;
        border-radius: 12px !important;
        border: 1px solid #E0E0E0 !important;
        background-color: #F8F9FB !important;
    }
    
    /* 確定上傳按鈕樣式 */
    button[kind="primary"] {
        background-color: #4A90E2 !important;
        color: white !important;
        height: 45px !important;
        font-weight: bold !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線與規則載入 ---
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
    st.title("📂 功能選單")
    with st.expander("📝 查看目前分類規則", expanded=False):
        if st.session_state.opts:
            st.write(", ".join(st.session_state.opts))
        if st.button("🔄 同步雲端規則"):
            st.session_state.opts, st.session_state.rules = load_rules()
            st.rerun()
    st.divider()
    search_m = st.text_input("輸入年份月份 (YYYYMM)")
    if st.button("載入歷史紀錄"):
        try:
            st.session_state.working_df = conn.read(worksheet=search_m, ttl="0s")
            st.rerun()
        except: st.error("查無資料")

# --- 6. 彈出對話框 ---
@st.dialog("📋 明細查看", width="large")
def show_detail(cat, data):
    st.subheader(f"類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)

# --- 7. 主頁面流程 ---
st.title("📊 個人月消費分析系統")

if 'working_df' not in st.session_state:
    u_file = st.file_uploader("📥 第一步：上傳 Richart Excel 明細", type=["xlsx"])
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
    st.markdown("### 🔍 1. 明細管理與類別修正")
    
    # 【重要回歸：篩選功能】
    all_current_cats = sorted(st.session_state.working_df['類別'].unique())
    selected_cats = st.multiselect("📂 勾選欲查看的類別：", options=all_current_cats, default=all_current_cats)
    
    # 建立過濾後的視圖
    mask = st.session_state.working_df['類別'].isin(selected_cats)
    filtered_df = st.session_state.working_df[mask]

    if st.button("🤖 重新套用最新規則"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    # 【重要回歸：編輯功能】
    edited_display_df = st.data_editor(
        filtered_df,
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=st.session_state.opts + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # 💡 重要：同步回原始 session_state，確保排行榜計算正確
    st.session_state.working_df.update(edited_display_df)

    # (2) 排行榜 (四個一列)
    st.divider()
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    # 使用完整數據計算排行榜，不受篩選器影響
    sum_df = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    
    num_cols = 4
    for i in range(0, len(sum_df), num_cols):
        batch = sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (original_idx, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                medal = "🥇 " if original_idx == 0 else "🥈 " if original_idx == 1 else "🥉 " if original_idx == 2 else ""
                label_text = f"{medal}{row['類別']}\n$ {int(row['金額']):,}"
                if st.button(label_text, key=f"r_{row['類別']}", use_container_width=True):
                    show_detail(row['類別'], st.session_state.working_df)

    # (3) 圖表
    st.divider()
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # (4) 儲存區 (絕對對齊)
    st.divider()
    st.markdown("### 💾 4. 命名並儲存至雲端")
    save_col_left, save_col_right = st.columns([4, 6])
    with save_col_left:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with save_col_right:
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                # 儲存完整的 working_df (含修改後的內容)
                conn.update(worksheet=target_name, data=st.session_state.working_df)
                st.success(f"✅ 已成功儲存：{target_name}")

    st.write("")
    if st.button("🗑️ 清空數據"):
        del st.session_state.working_df
        st.rerun()
