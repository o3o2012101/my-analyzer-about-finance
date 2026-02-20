import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="🤖", layout="wide")

# --- 2. 初始化 gspread (用於自動建表) ---
@st.cache_resource
def get_gspread_client():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # 從 Streamlit Secrets 讀取設定
    creds_info = st.secrets["connections"]["gsheets"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

gc = get_gspread_client()
spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
sh = gc.open_by_url(spreadsheet_url)

# --- 3. 雲端規則連線 (用於讀取規則) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    try:
        rules_df = conn.read(worksheet="Sheet1", ttl="1s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except: return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (如 202602)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.rerun()

# --- 5. 核心邏輯：自動讀取或建立分頁 ---
st.title(f"📊 {target_month} 消費狀態分析")

# 檢查分頁是否存在，不存在就建立
def get_or_create_worksheet(name):
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        # 自動建立新分頁，預設 1000 列 26 欄
        new_ws = sh.add_worksheet(title=name, rows="1000", cols="20")
        return new_ws

# 嘗試讀取資料
try:
    # 這裡用 conn.read 讀取，速度較快且有快取優化
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty:
        if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
            st.session_state.working_df = df_month
            st.session_state.curr_m = target_month
except Exception:
    # 如果讀不到，代表分頁可能真的剛建或是空的
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df

# --- 6. 上傳與初始化 ---
if 'working_df' not in st.session_state:
    st.info(f"✨ 準備初始化 {target_month} 的雲端資料...")
    uploaded_file = st.file_uploader(f"📥 上傳 {target_month} 的 Richart Excel", type=["xlsx"])
    
    if uploaded_file:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_idx = next(i for i, row in df_raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        c_desc, c_amt, c_date = next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c), next(c for c in df.columns if "日期" in c)
        df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
        
        def classify(t):
            t = str(t).lower()
            for cat, kws in st.session_state.category_rules.items():
                if any(k in t for k in kws): return cat
            return "待分類"
        df['類別'] = df[c_desc].apply(classify)
        
        new_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
        
        # 【全自動重點】偵測並建立分頁
        get_or_create_worksheet(target_month)
        conn.update(worksheet=target_month, data=new_df)
        
        st.session_state.working_df = new_df
        st.session_state.curr_m = target_month
        st.success(f"✅ 已自動在雲端建立 {target_month} 分頁並同步資料！")
        st.rerun()

# --- 7. 顯示與圖表 (同前版，確保圓餅圖清晰) ---
if 'working_df' in st.session_state:
    w_df = st.session_state.working_df
    all_cats = sorted(w_df['類別'].unique())
    selected_cats = st.multiselect("📂 篩選查看類別：", options=all_cats, default=all_cats)
    mask = w_df['類別'].isin(selected_cats)
    
    edited_df = st.data_editor(
        w_df[mask],
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    if st.session_state.main_editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.main_editor["edited_rows"].items():
            actual_idx = w_df[mask].index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        if st.button("💾 確認修改並儲存"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.success("✅ 雲端已更新！")
            st.rerun()

    # 圓餅圖
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_val = summary['金額'].sum()
    st.divider()
    st.markdown("### 📊 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.add_annotation(text=f"總支出<br><b>${total_val:,.0f}</b>", showarrow=False, font=dict(size=22))
    st.plotly_chart(fig, use_container_width=True)
