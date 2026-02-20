import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="🤖", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { 
        padding: 20px; 
        border-radius: 15px; 
        background-color: #F8F9FA; 
        border: 1px solid #E9ECEF; 
        text-align: center; 
        margin-bottom: 15px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .rank-name { font-size: 1.1rem; color: #666; font-weight: 500; }
    .rank-price { font-size: 1.8rem; color: #4A90E2; font-weight: bold; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化 gspread (自動建表用) ---
@st.cache_resource
def get_gspread_client():
    creds_info = st.secrets["connections"]["gsheets"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(credentials)

gc = get_gspread_client()
sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])

# --- 3. 讀取規則 (Sheet1) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    try:
        rules_df = conn.read(worksheet="Sheet1", ttl="1s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        rules_dict = {}
        for _, row in rules_df.iterrows():
            cat = str(row['分類名稱']).strip()
            kws = str(row['關鍵字']).strip().lower().split(",")
            if cat != 'nan' and cat != '':
                rules_dict[cat] = [k.strip() for k in kws if k.strip()]
        return rules_dict
    except: return {}

category_rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (如 202602)", value=datetime.now().strftime("%Y%m"))
    st.divider()
    with st.expander("🛠️ 目前偵測到的分類規則"):
        st.write(category_rules)

# --- 5. 核心邏輯：自動讀取或初始化 ---
st.title(f"📊 {target_month} 消費狀態分析")

def get_or_create_worksheet(name):
    try: return sh.worksheet(name)
    except: return sh.add_worksheet(title=name, rows="1000", cols="20")

# 讀取雲端分頁資料
try:
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty:
        if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
            st.session_state.working_df = df_month
            st.session_state.curr_m = target_month
except:
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df

# 上傳流程
if 'working_df' not in st.session_state:
    st.info(f"✨ 雲端尚未偵測到 {target_month} 分頁。")
    uploaded_file = st.file_uploader("📥 上傳 Excel 初始化雲端資料", type=["xlsx"])
    if uploaded_file:
        df_raw = pd.read_excel(uploaded_file, header=None)
        h_idx = next(i for i, row in df_raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
        df = pd.read_excel(uploaded_file, header=h_idx)
        df.columns = [str(c).strip() for c in df.columns]
        c_desc, c_amt, c_date = next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c), next(c for c in df.columns if "日期" in c)
        
        def classify(text):
            text = str(text).lower()
            for cat, kws in category_rules.items():
                if any(k in text for k in kws): return cat
            return "待分類"
            
        df['類別'] = df[c_desc].apply(classify)
        st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
        st.session_state.curr_m = target_month
        get_or_create_worksheet(target_month) # 自動建分頁
        conn.update(worksheet=target_month, data=st.session_state.working_df)
        st.rerun()

# --- 6. 資料編輯與顯示 (關鍵：包含篩選與編輯選單) ---
if 'working_df' in st.session_state:
    w_df = st.session_state.working_df
    
    # 功能按鈕
    if st.button("🚀 根據最新規則重新自動分類"):
        def re_classify(t):
            t = str(t).lower()
            for cat, kws in category_rules.items():
                if any(k in t for k in kws): return cat
            return "待分類"
        st.session_state.working_df['類別'] = st.session_state.working_df['消費明細'].apply(re_classify)
        st.rerun()

    # 【重要回歸：篩選功能】
    st.markdown("### 🔍 明細管理與修正")
    all_cats = sorted(w_df['類別'].unique())
    selected_cats = st.multiselect("📂 勾選欲查看的類別：", options=all_cats, default=all_cats)
    
    # 建立過濾後的視圖
    mask = w_df['類別'].isin(selected_cats)
    filtered_df = w_df[mask]

    # 【重要回歸：編輯功能】
    edited_df = st.data_editor(
        filtered_df,
        column_config={
            "類別": st.column_config.SelectboxColumn(
                "分類修正", 
                options=list(category_rules.keys()) + ["待分類"],
                help="直接從下拉選單修正類別"
            ),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, 
        hide_index=True, 
        key="main_editor"
    )

    # 儲存變動
    if st.session_state.main_editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.main_editor["edited_rows"].items():
            # 找到過濾後對應原始 DataFrame 的正確索引
            actual_idx = filtered_df.index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        if st.button("💾 確認修改並同步至雲端"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.success("✅ 雲端資料同步更新！")
            st.rerun()

    # --- 7. 排行榜與圖表 ---
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_val = summary['金額'].sum()

    st.divider()
    st.markdown("### 🏆 消費排行榜")
    cols = st.columns(4)
    for i, row in summary.iterrows():
        with cols[i % 4]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            st.markdown(f"""
                <div class="rank-card">
                    <div class="rank-name">{icon} {row['類別']}</div>
                    <div class="rank-price">${int(row['金額']):,}</div>
                </div>
            """, unsafe_allow_html=True)

    st.divider()
    st.markdown("### 📊 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.add_annotation(text=f"總支出<br><b>${total_val:,.0f}</b>", showarrow=False, font=dict(size=22))
    st.plotly_chart(fig, use_container_width=True)
