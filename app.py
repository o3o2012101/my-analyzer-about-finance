import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="💰", layout="wide")

# --- 2. 核心 CSS 修復：對齊、藍色字體與按鈕縮放 ---
st.markdown("""
    <style>
    /* 1. 儲存區域對齊：強制底部對齊 */
    [data-testid="column"] {
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
    }
    
    /* 2. 排行榜按鈕：移除藍點，實現藍色金額字體 */
    .stButton > button {
        height: 70px !important;
        border-radius: 12px !important;
        border: 1px solid #E0E0E0 !important;
        background-color: #F8F9FB !important;
        transition: 0.2s;
    }
    .stButton > button:hover {
        background-color: #FFFFFF !important;
        border-color: #4A90E2 !important;
    }
    
    /* 模擬按鈕內的兩行樣式 */
    .cat-name { color: #333333; font-weight: bold; font-size: 14px; }
    .price-blue { color: #4A90E2; font-weight: bold; font-size: 16px; display: block; margin-top: 2px; }

    /* 3. 確定上傳按鈕樣式 */
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

# --- 5. 側邊欄：功能選單 ---
with st.sidebar:
    st.title("📂 功能選單")
    
    # 修改：規則顯示改為 Expander，要看再點開
    with st.expander("📝 查看目前分類規則", expanded=False):
        if st.session_state.opts:
            st.write(", ".join(st.session_state.opts))
        else:
            st.write("尚未載入規則")
        if st.button("🔄 同步雲端規則"):
            st.session_state.opts, st.session_state.rules = load_rules()
            st.rerun()

    st.divider()
    st.subheader("🔎 歷史紀錄查詢")
    search_m = st.text_input("輸入年份月份 (YYYYMM)")
    if st.button("載入歷史紀錄"):
        try:
            st.session_state.working_df = conn.read(worksheet=search_m, ttl="0s")
            st.rerun()
        except: st.error("查無該月分頁")

# --- 6. 彈出對話框 ---
@st.dialog("📋 明細查看", width="large")
def show_detail(cat, data):
    st.subheader(f"類別：{cat}")
    d = data[data['類別'] == cat].sort_values('日期', ascending=False)
    st.dataframe(d[['日期', '消費明細', '金額']], use_container_width=True, hide_index=True)

# --- 7. 主頁面流程 ---
st.title("🤖 Richart AI 自動記帳系統")

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
    # (1) 明細管理
    st.markdown("### 🔍 1. 明細管理與類別修正")
    if st.button("🤖 重新套用最新雲端規則"):
        st.session_state.working_df = perform_auto_classify(st.session_state.working_df)
        st.rerun()
    
    edited_df = st.data_editor(
        st.session_state.working_df,
        column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=st.session_state.opts + ["待分類"])},
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # (2) 排行榜 (移除藍點，四個一列，真正的藍字金額效果)
    st.divider()
    st.markdown("### 🏆 2. 消費支出排行榜 (點擊看明細)")
    sum_df = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    
    num_cols = 4
    for i in range(0, len(sum_df), num_cols):
        batch = sum_df.iloc[i:i+num_cols]
        cols = st.columns(num_cols)
        for idx, (original_idx, row) in enumerate(batch.iterrows()):
            with cols[idx]:
                # 判斷獎牌 (僅前三名)
                medal = "🥇 " if original_idx == 0 else "🥈 " if original_idx == 1 else "🥉 " if original_idx == 2 else ""
                
                # 這裡使用 \n 分行，CSS 會處理視覺效果
                label_text = f"{medal}{row['類別']}\n$ {int(row['金額']):,}"
                
                if st.button(label_text, key=f"r_{row['類別']}", use_container_width=True):
                    show_detail(row['類別'], edited_df)

    # (3) 圓餅圖
    st.divider()
    st.markdown("### 🥧 3. 支出佔比分析")
    fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
    st.plotly_chart(fig, use_container_width=True)

    # (4) 儲存區 (解決對齊問題)
    st.divider()
    st.markdown("### 💾 4. 命名並儲存至雲端")
    
    # 關鍵對齊容器
    save_col_left, save_col_right = st.columns([4, 6])
    with save_col_left:
        target_name = st.text_input("分頁名稱 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    with save_col_right:
        # 按鈕底部會完美對齊輸入框
        if st.button("🚀 確定上傳至 Google Sheet", type="primary", use_container_width=True):
            if gc:
                sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
                try: sh.worksheet(target_name)
                except: sh.add_worksheet(title=target_name, rows="1000", cols="20")
                conn.update(worksheet=target_name, data=edited_df)
                st.success(f"✅ 已成功儲存至分頁：{target_name}")

    st.write("")
    if st.button("🗑️ 清空數據並重新上傳"):
        del st.session_state.working_df
        st.rerun()
