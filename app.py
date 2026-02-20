import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="Richart AI Pro", page_icon="💰", layout="wide")

# --- 2. 質感 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .stButton>button {
        border-radius: 10px;
        min-height: 60px;
        background: #F8F9FA;
        border: 1px solid #E0E0E0;
    }
    [data-testid="stDataEditor"] { border: 1px solid #4A90E2; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線 ---
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
        # 關鍵字處理：轉小寫並去除空白
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 自動分類核心函數 ---
def auto_classify_df(df):
    """根據最新的 session_state.rules 重新分類表格"""
    def get_cat(desc):
        desc_lower = str(desc).lower()
        for cat, keywords in st.session_state.rules.items():
            for k in keywords:
                if k in desc_lower: # 模糊比對
                    return cat
        return "待分類"
    
    df['類別'] = df['消費明細'].apply(get_cat)
    return df

# --- 5. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_month = st.text_input("分析月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步規則並「重新分類」全部"):
        st.session_state.opts, st.session_state.rules = load_rules()
        if 'working_df' in st.session_state:
            st.session_state.working_df = auto_classify_df(st.session_state.working_df)
            st.success("規則已同步，所有明細已重新分類！")
        st.rerun()

# --- 6. 明細對話框 ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別總額", f"${int(detail_df['金額'].sum()):,}")

# --- 7. 主程式邏輯 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
        # 讀取資料
        try:
            df_m = conn.read(worksheet=target_month, ttl="0s")
            if not df_m.empty:
                # 這裡確保載入時日期格式正確
                df_m['日期'] = pd.to_datetime(df_m['日期']).dt.strftime('%Y-%m-%d')
                st.session_state.working_df = df_m
                st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        st.title(f"📊 {target_month} 財務儀表板")

        # 初始化上傳
        if 'working_df' not in st.session_state:
            st.info(f"💡 請上傳 {target_month} 的 Excel 以開始。")
            u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
            if u_file:
                df_raw = pd.read_excel(u_file, header=next(i for i, r in pd.read_excel(u_file, header=None).iterrows() if "消費明細" in "".join(map(str, r))))
                df_raw.columns = [str(c).strip() for c in df_raw.columns]
                c_d, c_m, c_a = next(c for c in df_raw.columns if "日期" in c), next(c for c in df_raw.columns if "明細" in c), next(c for c in df_raw.columns if "金額" in c)
                
                new_df = df_raw[[c_d, c_m, c_a]].copy()
                new_df.columns = ['日期', '消費明細', '金額']
                new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
                # 執行第一次自動分類
                new_df = auto_classify_df(new_df)
                
                try: sh.worksheet(target_month)
                except: sh.add_worksheet(title=target_month, rows="1000", cols="20")
                conn.update(worksheet=target_month, data=new_df)
                st.session_state.working_df = new_df
                st.rerun()

        # --- 正式顯示區：依照指定順序 ---
        if 'working_df' in st.session_state:
            
            # 第一部分：🔍 明細管理與類別修正
            st.markdown("### 🔍 明細管理與類別修正")
            col_btn1, col_btn2 = st.columns([2, 8])
            with col_btn1:
                if st.button("🤖 執行自動分類", help="根據目前 Sheet1 的關鍵字重新掃描所有明細"):
                    st.session_state.working_df = auto_classify_df(st.session_state.working_df)
                    st.rerun()

            display_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
            edited_df = st.data_editor(
                st.session_state.working_df,
                column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=display_opts, width="medium")},
                use_container_width=True, hide_index=True, key="main_editor"
            )

            if st.button("💾 儲存所有分類修正並同步雲端", type="primary"):
                st.session_state.working_df = edited_df
                conn.update(worksheet=target_month, data=edited_df)
                st.success("✅ 雲端同步成功！")
                time.sleep(0.5)
                st.rerun()

            st.divider()

            # 第二部分：🏆 排行榜
            # 重新計算排行榜數據
            sum_df = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
            
            st.markdown("### 🏆 消費支出排行榜 (點擊卡片看明細)")
            cols = st.columns(6)
            for i, row in sum_df.iterrows():
                with cols[i % 6]:
                    icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💰"
                    if st.button(f"{icon} {row['類別']}\n${int(row['金額']):,}", key=f"r_{row['類別']}", use_container_width=True):
                        show_details(row['類別'], st.session_state.working_df)

            st.divider()

            # 第三部分：🥧 圓餅圖
            st.markdown("### 🥧 支出佔比分析")
            fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(height=600)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"⚠️ 系統錯誤：{e}")
