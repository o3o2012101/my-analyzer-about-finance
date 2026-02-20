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

# --- 2. 質感 CSS (讓排行榜更有 Feel) ---
st.markdown("""
    <style>
    .stApp { background-color: #F8F9FA; }
    .stButton>button {
        border-radius: 15px;
        height: 120px;
        border: 1px solid #E0E0E0;
        background: white;
        transition: 0.3s;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
    .stButton>button:hover {
        border-color: #4A90E2;
        box-shadow: 0 8px 15px rgba(0,0,0,0.08);
        transform: translateY(-2px);
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線 (gspread + GSheetsConnection) ---
@st.cache_resource
def get_gc():
    try:
        creds = Credentials.from_service_account_info(st.secrets["connections"]["gsheets"], 
                scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        return gspread.authorize(creds)
    except: return None

gc = get_gc()
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [c.strip() for c in df.columns]
        opts = df['分類名稱'].dropna().unique().tolist()
        rules = {str(r['分類名稱']).strip(): str(r['關鍵字']).lower().split(",") for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except: return [], {}

# 確保 Session 狀態
if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_month = st.text_input("分析月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端規則"):
        st.session_state.opts, st.session_state.rules = load_rules()
        st.success("規則已同步！")
        st.rerun()

# --- 5. 核心：大視窗明細對話框 ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    # 過濾該類別資料
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別累計支出", f"${detail_df['金額'].sum():,.0f}")

# --- 6. 讀取/自動建立分頁 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        def get_or_create_ws(name):
            try: return sh.worksheet(name)
            except: return sh.add_worksheet(title=name, rows="1000", cols="20")

        # 讀取當月資料
        try:
            df_m = conn.read(worksheet=target_month, ttl="0s")
            if not df_m.empty: 
                st.session_state.working_df = df_m
                st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        st.title(f"💳 {target_month} 財務儀表板")

        # 初始化上傳邏輯
        if 'working_df' not in st.session_state:
            st.info(f"💡 偵測到 {target_month} 尚未初始化。")
            u_file = st.file_uploader("📥 上傳 Richart Excel", type=["xlsx"])
            if u_file:
                raw = pd.read_excel(u_file, header=None)
                h_idx = next(i for i, row in raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
                df = pd.read_excel(u_file, header=h_idx)
                df.columns = [str(c).strip() for c in df.columns]
                c_desc, c_amt, c_date = next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c), next(c for c in df.columns if "日期" in c)
                
                def classify(t):
                    t = str(t).lower()
                    for cat, kws in st.session_state.rules.items():
                        if any(k in t for k in kws): return cat
                    return "待分類"
                
                df['類別'] = df[c_desc].apply(classify)
                st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
                get_or_create_ws(target_month)
                conn.update(worksheet=target_month, data=st.session_state.working_df)
                st.rerun()

        # 數據展示區
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            sum_df = w_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

            # --- 🏆 排行榜 (點擊觸發大視窗) ---
            st.subheader("🏆 消費排行榜 (點擊卡片看明細)")
            cols = st.columns(min(len(sum_df), 4) if not sum_df.empty else 1)
            for i, row in sum_df.iterrows():
                with cols[i % 4]:
                    rank_icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "📍"
                    # 排行榜按鈕：點擊開啟大視窗
                    if st.button(f"{rank_icon} {row['類別']}\n\n${int(row['金額']):,}", key=f"rank_{row['類別']}"):
                        show_details(row['類別'], w_df)

            st.divider()

            # --- 🔍 編輯與圖表區 ---
            c1, c2 = st.columns([6, 4])
            with c1:
                st.subheader("🔍 明細管理")
                all_c = sorted(w_df['類別'].unique())
                sel_c = st.multiselect("過濾顯示類別：", options=all_c, default=all_c)
                filtered = w_df[w_df['類別'].isin(sel_c)]
                
                # 直接編輯類別選單
                opts = sorted(list(set(st.session_state.opts + ["待分類"])))
                edited = st.data_editor(
                    filtered,
                    column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=opts)},
                    use_container_width=True, hide_index=True, key="editor"
                )
                
                if st.button("💾 儲存所有變動至雲端"):
                    # 將編輯結果合併回主 Dataframe
                    for idx, row in edited.iterrows():
                        st.session_state.working_df.loc[idx, '類別'] = row['類別']
                    conn.update(worksheet=target_month, data=st.session_state.working_df)
                    st.success("✅ 雲端更新成功！")
                    st.rerun()

            with c2:
                st.subheader("🥧 支出佔比")
                fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Safe)
                fig.update_traces(textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"⚠️ 運行發生問題：{e}")
