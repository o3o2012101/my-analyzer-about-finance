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

# --- 2. 質感 CSS (徹底解決按鈕過大) ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    /* 自定義小卡片樣式 */
    .ranking-card {
        background: #F8F9FA;
        border: 1px solid #E0E0E0;
        border-radius: 12px;
        padding: 15px;
        text-align: center;
        transition: 0.3s;
        cursor: pointer;
        margin-bottom: 10px;
    }
    .ranking-card:hover {
        border-color: #4A90E2;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        background: #FFFFFF;
    }
    .ranking-icon { font-size: 1.5rem; }
    .ranking-name { font-size: 1rem; color: #555; font-weight: bold; }
    .ranking-price { font-size: 1.2rem; color: #4A90E2; font-weight: 800; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 初始化連線 ---
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
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        opts = sorted([str(c).strip() for c in rules_df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules_dict = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                      for _, r in rules_df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules_dict
    except: return [], {}

# 載入規則至 session_state
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

# --- 5. 明細對話框 ---
@st.dialog("📋 消費明細查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別總計", f"${int(detail_df['金額'].sum()):,}")

# --- 6. 核心數據邏輯 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
        # 讀取資料
        try:
            df_m = conn.read(worksheet=target_month, ttl="0s")
            if not df_m.empty:
                st.session_state.working_df = df_m
                st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        st.title(f"📊 {target_month} 財務儀表板")

        # 初始化上傳
        if 'working_df' not in st.session_state:
            st.info("💡 請上傳 Excel 初始化。")
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

        # 數據展示
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            sum_df = w_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

            # --- 🏆 排行榜 (使用 Column 排版縮小按鈕) ---
            st.subheader("🏆 支出排行 (點擊看明細)")
            # 限制按鈕不要太寬
            cols = st.columns(6) 
            for i, row in sum_df.iterrows():
                with cols[i % 6]:
                    rank_icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💰"
                    # 使用小字號標題模擬縮小按鈕
                    if st.button(f"{rank_icon}{row['類別']}\n${int(row['金額']):,}", key=f"r_{row['類別']}", use_container_width=True):
                        show_details(row['類別'], w_df)

            # --- 🥧 圓餅圖 (置中，單獨一行) ---
            st.divider()
            st.subheader("🥧 支出比例分析")
            fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(height=500, margin=dict(t=30, b=30, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

            # --- 🔍 明細編輯 (單獨一行) ---
            st.divider()
            st.subheader("🔍 明細管理與類別修正")
            
            # 使用副本進行編輯
            opts = sorted(list(set(st.session_state.opts + ["待分類"])))
            edited_df = st.data_editor(
                w_df,
                column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=opts, width="medium")},
                use_container_width=True, hide_index=True, key="main_editor"
            )

            if st.button("💾 儲存所有變動至雲端"):
                # 直接將編輯後的表格儲存
                st.session_state.working_df = edited_df
                conn.update(worksheet=target_month, data=edited_df)
                st.success("✅ 雲端同步完成！")
                time.sleep(1)
                st.rerun()

    except Exception as e:
        st.error(f"⚠️ 異常：{e}")
