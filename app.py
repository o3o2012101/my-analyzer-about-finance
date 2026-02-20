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
    creds_info = st.secrets["connections"]["gsheets"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

gc = get_gspread_client()
spreadsheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
sh = gc.open_by_url(spreadsheet_url)

# --- 3. 雲端規則讀取 (強化版) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    try:
        # 強制讀取第一個分頁，不管它叫什麼名字
        rules_df = conn.read(worksheet="Sheet1", ttl="1s")
        rules_df.columns = [c.strip() for c in rules_df.columns] # 刪除欄位空格
        
        # 檢查關鍵欄位是否存在
        if '分類名稱' not in rules_df.columns or '關鍵字' not in rules_df.columns:
            st.error(f"❌ 規則表格式錯誤！請檢查是否有『分類名稱』與『關鍵字』這兩個標題。目前偵測到：{list(rules_df.columns)}")
            return {}

        rules_dict = {}
        for _, row in rules_df.iterrows():
            cat = str(row['分類名稱']).strip()
            kws = str(row['關鍵字']).strip().lower().split(",")
            if cat != 'nan' and cat != '':
                rules_dict[cat] = [k.strip() for k in kws if k.strip()]
        
        if not rules_dict:
            st.warning("⚠️ 規則表似乎是空的，請檢查 Sheet1 內容。")
        return rules_dict
    except Exception as e:
        st.error(f"❌ 無法讀取規則表：{e}")
        return {}

# 每次重新整理都重新載入規則，確保即時性
category_rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (如 202602)", value=datetime.now().strftime("%Y%m"))
    st.divider()
    with st.expander("🛠️ 目前偵測到的分類規則"):
        st.write(category_rules)

# --- 5. 自動讀取或建立分頁 ---
st.title(f"📊 {target_month} 消費狀態分析")

def get_or_create_worksheet(name):
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=name, rows="1000", cols="20")

# 嘗試讀取資料
try:
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty:
        if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
            # 確保讀入的舊資料也會根據新規則「重新跑一遍分類」 (針對待分類進行修正)
            st.session_state.working_df = df_month
            st.session_state.curr_m = target_month
except Exception:
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df

# --- 6. 上傳與自動分類 (核心修正) ---
if 'working_df' not in st.session_state:
    st.info(f"✨ 準備初始化 {target_month} 資料...")
    uploaded_file = st.file_uploader(f"📥 上傳 Excel", type=["xlsx"])
    
    if uploaded_file:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_idx = next(i for i, row in df_raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        c_desc = next(c for c in df.columns if "明細" in c)
        c_amt = next(c for c in df.columns if "金額" in c)
        c_date = next(c for c in df.columns if "日期" in c)
        
        df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
        
        # 分類邏輯：只要明細包含關鍵字，就分類
        def classify(text):
            text = str(text).lower()
            for cat, keywords in category_rules.items():
                for k in keywords:
                    if k in text:
                        return cat
            return "待分類"
            
        df['類別'] = df[c_desc].apply(classify)
        new_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
        
        get_or_create_worksheet(target_month)
        conn.update(worksheet=target_month, data=new_df)
        st.session_state.working_df = new_df
        st.session_state.curr_m = target_month
        st.success("✅ 初始化成功！")
        st.rerun()

# --- 7. 資料編輯與顯示 ---
if 'working_df' in st.session_state:
    w_df = st.session_state.working_df
    
    # 增加一個「批次重新分類」按鈕，防止規則更新後舊資料沒動
    if st.button("🚀 根據最新規則重新自動分類"):
        def re_classify(text):
            text = str(text).lower()
            for cat, keywords in category_rules.items():
                for k in keywords:
                    if k in text: return cat
            return "待分類"
        st.session_state.working_df['類別'] = st.session_state.working_df['消費明細'].apply(re_classify)
        st.success("重新分類完成！請記得按下方的儲存鈕。")

    all_cats = sorted(w_df['類別'].unique())
    selected_cats = st.multiselect("📂 篩選查看類別：", options=all_cats, default=all_cats)
    mask = w_df['類別'].isin(selected_cats)
    
    edited_df = st.data_editor(
        w_df[mask],
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    if st.session_state.main_editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.main_editor["edited_rows"].items():
            actual_idx = w_df[mask].index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        if st.button("💾 確認修改並儲存至雲端"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.success("✅ 雲端同步成功！")
            st.rerun()

    # 圖表
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_val = summary['金額'].sum()
    st.divider()
    st.markdown("### 📊 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.add_annotation(text=f"總支出<br><b>${total_val:,.0f}</b>", showarrow=False, font=dict(size=22))
    st.plotly_chart(fig, use_container_width=True)
