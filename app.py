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
    /* 讓編輯器更醒目 */
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
    except Exception as e:
        st.error(f"❌ Google 連線失敗: {e}")
        return None

gc = get_gc()
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    """從 Sheet1 抓取分類與關鍵字"""
    try:
        df = conn.read(worksheet="Sheet1", ttl="0s")
        df.columns = [str(c).strip() for c in df.columns]
        # 抓取分類清單
        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        # 抓取關鍵字字典
        rules = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                 for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules
    except Exception as e:
        st.warning(f"⚠️ 無法讀取 Sheet1 規則：{e}")
        return [], {}

# 初始化 Session State
if 'opts' not in st.session_state or not st.session_state.opts:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_month = st.text_input("分析月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端規則"):
        st.session_state.opts, st.session_state.rules = load_rules()
        st.success("規則已更新！")
        st.rerun()
    with st.expander("🛠️ 規則檢查"):
        st.write("分類清單：", st.session_state.opts)
        st.write("規則細節：", st.session_state.rules)

# --- 5. 明細對話框 ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別總額", f"${int(detail_df['金額'].sum()):,}")

# --- 6. 核心流程 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
        # 讀取當月資料
        try:
            df_m = conn.read(worksheet=target_month, ttl="0s")
            if not df_m.empty:
                st.session_state.working_df = df_m
                st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        st.title(f"📊 {target_month} 財務儀表板")

        # --- 初始化上傳 ---
        if 'working_df' not in st.session_state:
            st.info(f"💡 請上傳 {target_month} 的 Excel 以開始。")
            u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
            if u_file:
                df = pd.read_excel(u_file, header=next(i for i, r in pd.read_excel(u_file, header=None).iterrows() if "消費明細" in "".join(map(str, r))))
                df.columns = [str(c).strip() for c in df.columns]
                c_d, c_m, c_a = next(c for c in df.columns if "日期" in c), next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c)
                
                def classify(t):
                    for cat, kws in st.session_state.rules.items():
                        if any(k in str(t).lower() for k in kws): return cat
                    return "待分類"
                
                new_df = df[[c_d, c_m, c_a]].copy()
                new_df.columns = ['日期', '消費明細', '金額']
                new_df['類別'] = new_df['消費明細'].apply(classify)
                new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
                
                try: sh.worksheet(target_month)
                except: sh.add_worksheet(title=target_month, rows="1000", cols="20")
                conn.update(worksheet=target_month, data=new_df)
                st.session_state.working_df = new_df
                st.rerun()

        # --- 正式顯示區：依照指定順序 ---
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df

            # 第一部分：🔍 明細管理與類別修正 (要在第一欄)
            st.markdown("### 🔍 明細管理與類別修正")
            # 診斷提示
            if not st.session_state.opts:
                st.error("⚠️ 注意：目前抓不到 Sheet1 的分類名稱，下拉選單將無法運作！")
            
            # 下拉選單選項
            display_opts = sorted(list(set(st.session_state.opts + ["待分類"])))
            
            # 編輯表格
            edited_df = st.data_editor(
                w_df,
                column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=display_opts, width="medium")},
                use_container_width=True, hide_index=True, key="main_editor"
            )

            if st.button("💾 儲存所有分類修正並同步雲端", type="primary"):
                # 直接覆蓋 session 與雲端
                st.session_state.working_df = edited_df
                conn.update(worksheet=target_month, data=edited_df)
                st.success("✅ 雲端同步成功！頁面將重新計算。")
                time.sleep(1)
                st.rerun()

            st.divider()

            # 第二部分：🏆 排行榜
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
