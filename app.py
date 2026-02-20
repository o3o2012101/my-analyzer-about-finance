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

# --- 2. CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .stButton>button {
        border-radius: 10px;
        min-height: 60px;
        background: #F8F9FA;
        border: 1px solid #E0E0E0;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 連線與規則讀取 ---
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
    """強化版規則讀取：增加詳細錯誤回報"""
    try:
        # ttl=0 確保每次都抓最新的，避免被 Cache 誤導
        df = conn.read(worksheet="Sheet1", ttl="0s")
        if df.empty:
            st.error("❌ Sheet1 是空的，請檢查試算表內容！")
            return [], {}
        
        # 清除欄位空格
        df.columns = [str(c).strip() for c in df.columns]
        
        if "分類名稱" not in df.columns or "關鍵字" not in df.columns:
            st.error(f"❌ 欄位名稱不符！目前抓到的是: {list(df.columns)}。請確保有『分類名稱』與『關鍵字』。")
            return [], {}

        opts = sorted([str(c).strip() for c in df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        rules_dict = {
            str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
            for _, r in df.iterrows() if str(r['分類名稱']).strip() != 'nan'
        }
        return opts, rules_dict
    except Exception as e:
        st.error(f"❌ 讀取 Sheet1 失敗: {e}")
        return [], {}

# 初始化 Session State
if 'opts' not in st.session_state or not st.session_state.opts:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_month = st.text_input("分析月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    
    st.divider()
    if st.button("🔄 強制同步雲端規則"):
        st.cache_resource.clear() # 清除連線快取
        st.session_state.opts, st.session_state.rules = load_rules()
        st.success("規則已重新載入！")
        st.rerun()
    
    with st.expander("🛠️ 目前抓取到的規則"):
        if st.session_state.rules:
            st.write(st.session_state.rules)
        else:
            st.warning("⚠️ 目前沒有抓到任何規則！")

# --- 5. 對話框與主邏輯 ---
@st.dialog("📋 消費明細查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別總計", f"${int(detail_df['金額'].sum()):,}")

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

        # --- 資料初始化與自動分類 ---
        if 'working_df' not in st.session_state:
            st.info("💡 請上傳 Excel 開始分析。")
            u_file = st.file_uploader("📥 上傳 Richart Excel", type=["xlsx"])
            if u_file:
                # 這裡增加自動分類邏輯
                raw = pd.read_excel(u_file, header=None)
                h_idx = next(i for i, r in raw.iterrows() if "消費明細" in "".join(map(str, r)))
                df = pd.read_excel(u_file, header=h_idx)
                df.columns = [str(c).strip() for c in df.columns]
                c_d, c_m, c_a = next(c for c in df.columns if "日期" in c), next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c)
                
                def classify(t):
                    # 如果規則是空的，這裡會全部回傳待分類
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

        # --- 頁面展示區 ---
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            sum_df = w_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

            # 1. 排行榜 (縮小版)
            st.subheader("🏆 支出排行")
            cols = st.columns(6)
            for i, row in sum_df.iterrows():
                with cols[i % 6]:
                    if st.button(f"{row['類別']}\n${int(row['金額']):,}", key=f"r_{row['類別']}", use_container_width=True):
                        show_details(row['類別'], w_df)

            # 2. 圓餅圖 (置中獨佔一行)
            st.divider()
            st.subheader("🥧 支出比例分析")
            fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

            # 3. 明細管理 (獨佔一行)
            st.divider()
            st.subheader("🔍 明細管理與類別修正")
            opts = sorted(list(set(st.session_state.opts + ["待分類"])))
            
            edited_df = st.data_editor(
                w_df,
                column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=opts, width="medium")},
                use_container_width=True, hide_index=True, key="main_editor"
            )

            if st.button("💾 儲存並同步至雲端"):
                conn.update(worksheet=target_month, data=edited_df)
                st.session_state.working_df = edited_df
                st.success("✅ 雲端已同步！")
                time.sleep(1)
                st.rerun()

    except Exception as e:
        st.error(f"⚠️ 異常：{e}")
