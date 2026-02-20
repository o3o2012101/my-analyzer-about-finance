import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import time

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 全自動帳本", page_icon="🤖", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card-box { 
        padding: 20px; border-radius: 15px; background-color: #F8F9FA; border: 1px solid #E9ECEF; 
        text-align: center; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        cursor: pointer;
    }
    .rank-name { font-size: 1.1rem; color: #666; font-weight: 500; }
    .rank-price { font-size: 1.8rem; color: #4A90E2; font-weight: bold; margin-top: 5px; }
    .stButton>button { width: 100%; border-radius: 15px; border: 1px solid #E9ECEF; background-color: #F8F9FA; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化 gspread ---
@st.cache_resource
def get_gspread_client():
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"❌ Google 連線失敗: {e}")
        return None

gc = get_gspread_client()

# --- 3. 穩定讀取規則 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def safe_load_rules():
    try:
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        cats = rules_df['分類名稱'].dropna().unique().tolist()
        cat_list = [str(c).strip() for c in cats if str(c).strip() != 'nan']
        rules_dict = {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                      for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
        return cat_list, rules_dict
    except: return [], {}

if 'category_options' not in st.session_state:
    c_list, r_dict = safe_load_rules()
    st.session_state.category_options = c_list
    st.session_state.category_rules = r_dict

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端規則"):
        c_list, r_dict = safe_load_rules()
        st.session_state.category_options = c_list
        st.session_state.category_rules = r_dict
        st.rerun()

st.title(f"📊 {target_month} 消費狀態分析")

# --- 5. 核心邏輯 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        def get_or_create_ws(name):
            try: return sh.worksheet(name)
            except: return sh.add_worksheet(title=name, rows="1000", cols="20")

        # 讀取當月資料
        try:
            df_month = conn.read(worksheet=target_month, ttl="0s")
            if not df_month.empty:
                if 'working_df' not in st.session_state or st.session_state.get('curr_m') != target_month:
                    st.session_state.working_df = df_month
                    st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        # 上傳邏輯
        if 'working_df' not in st.session_state:
            st.info(f"💡 請上傳 {target_month} 的 Excel。")
            u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
            if u_file:
                raw = pd.read_excel(u_file, header=None)
                h_idx = next(i for i, row in raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
                df = pd.read_excel(u_file, header=h_idx)
                df.columns = [str(c).strip() for c in df.columns]
                c_desc, c_amt, c_date = next(c for c in df.columns if "明細" in c), next(c for c in df.columns if "金額" in c), next(c for c in df.columns if "日期" in c)
                
                def classify(t):
                    t = str(t).lower()
                    for cat, kws in st.session_state.category_rules.items():
                        if any(k in t for k in kws): return cat
                    return "待分類"
                
                df['類別'] = df[c_desc].apply(classify)
                st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
                st.session_state.curr_m = target_month
                get_or_create_ws(target_month)
                conn.update(worksheet=target_month, data=st.session_state.working_df)
                st.rerun()

        # 顯示資料
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            
            # --- 篩選與編輯 ---
            st.markdown("### 🔍 明細管理與修正")
            all_c = sorted(w_df['類別'].unique())
            sel_c = st.multiselect("📂 顯示類別：", options=all_c, default=all_c)
            f_df = w_df[w_df['類別'].isin(sel_c)]

            if not f_df.empty:
                opts = sorted(list(set(st.session_state.category_options + ["待分類"])))
                edt_df = st.data_editor(
                    f_df,
                    column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=opts), "金額": st.column_config.NumberColumn("金額", format="$%d")},
                    use_container_width=True, hide_index=True, key="main_editor"
                )

                if st.session_state.main_editor.get("edited_rows"):
                    for idx_s, change in st.session_state.main_editor["edited_rows"].items():
                        real_idx = f_df.index[int(idx_s)]
                        for f, v in change.items(): st.session_state.working_df.at[real_idx, f] = v
                    if st.button("💾 儲存修改至雲端"):
                        conn.update(worksheet=target_month, data=st.session_state.working_df)
                        st.success("✅ 已儲存！")
                        st.rerun()

                # --- 核心更新：排行榜點擊跳轉功能 ---
                sum_df = f_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
                
                st.divider()
                st.markdown("### 🏆 消費排行榜 (點擊卡片查看明細)")
                cols = st.columns(4)
                for i, row in sum_df.iterrows():
                    with cols[i % 4]:
                        icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                        # 使用 Popover 模擬點擊卡片跳出視窗
                        with st.popover(f"{icon} {row['類別']} | ${int(row['金額']):,}"):
                            st.markdown(f"#### 📝 {row['類別']} 消費明細")
                            detail_df = f_df[f_df['類別'] == row['類別']][['日期', '消費明細', '金額']].sort_values(by='日期', ascending=False)
                            st.dataframe(detail_df, hide_index=True, use_container_width=True)

                st.divider()
                st.markdown("### 🥧 支出佔比分析")
                fig = px.pie(sum_df, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.add_annotation(text=f"總支出<br><b>${sum_df['金額'].sum():,.0f}</b>", showarrow=False, font=dict(size=22))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("請勾選類別。")
    except Exception as e:
        st.error(f"⚠️ 錯誤：{e}")
