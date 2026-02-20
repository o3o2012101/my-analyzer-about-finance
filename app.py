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

# 套用樣式：排行榜卡片設計
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { 
        padding: 20px; border-radius: 15px; background-color: #F8F9FA; border: 1px solid #E9ECEF; 
        text-align: center; margin-bottom: 15px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    .rank-name { font-size: 1.1rem; color: #666; font-weight: 500; }
    .rank-price { font-size: 1.8rem; color: #4A90E2; font-weight: bold; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初始化 gspread (全自動建表用) ---
@st.cache_resource
def get_gspread_client():
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"❌ Google 連線初始化失敗: {e}")
        return None

gc = get_gspread_client()

# --- 3. 穩定讀取規則 (Sheet1) ---
conn = st.connection("gsheets", type=GSheetsConnection)

def safe_load_rules():
    try:
        # 強制刷新讀取 Sheet1
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        # 取得下拉選單清單
        cats = rules_df['分類名稱'].dropna().unique().tolist()
        cat_list = [str(c).strip() for c in cats if str(c).strip() != 'nan']
        # 建立匹配字典
        rules_dict = {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                      for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
        return cat_list, rules_dict
    except:
        return [], {}

# 初始化 Session State (確保切換月份時規則還在)
if 'category_options' not in st.session_state or not st.session_state.category_options:
    c_list, r_dict = safe_load_rules()
    st.session_state.category_options = c_list
    st.session_state.category_rules = r_dict

# --- 4. 側邊欄 ---
with st.sidebar:
    st.title("📂 月份切換")
    target_month = st.text_input("操作月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    st.divider()
    if st.button("🔄 同步雲端規則與選單"):
        c_list, r_dict = safe_load_rules()
        st.session_state.category_options = c_list
        st.session_state.category_rules = r_dict
        st.success("規則已同步！")
        st.rerun()
    with st.expander("🛠️ 目前規則預覽"):
        st.write(st.session_state.category_rules)

st.title(f"📊 {target_month} 消費狀態分析")

# --- 5. 核心邏輯：資料處理 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        
        # 建立分頁函數
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

        # 如果沒資料，顯示上傳
        if 'working_df' not in st.session_state:
            st.info(f"💡 請上傳 {target_month} 的 Richart Excel。")
            u_file = st.file_uploader("📥 上傳 Excel 初始化雲端資料", type=["xlsx"])
            if u_file:
                raw = pd.read_excel(u_file, header=None)
                h_idx = next(i for i, row in raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
                df = pd.read_excel(u_file, header=h_idx)
                df.columns = [str(c).strip() for c in df.columns]
                c_desc = next(c for c in df.columns if "明細" in c)
                c_amt = next(c for c in df.columns if "金額" in c)
                c_date = next(c for c in df.columns if "日期" in c)
                
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

        # 顯示資料與圖表區
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            
            # 功能按鈕
            if st.button("🚀 根據最新規則重新自動分類"):
                def re_classify(t):
                    t = str(t).lower()
                    for cat, kws in st.session_state.category_rules.items():
                        if any(k in t for k in kws): return cat
                    return "待分類"
                st.session_state.working_df['類別'] = st.session_state.working_df['消費明細'].apply(re_classify)
                st.rerun()

            # --- 篩選功能 ---
            st.markdown("### 🔍 明細管理與修正")
            all_c = sorted(w_df['類別'].unique())
            sel_c = st.multiselect("📂 顯示類別：", options=all_c, default=all_c)
            f_df = w_df[w_df['類別'].isin(sel_c)]

            # --- 表格編輯 ---
            if not f_df.empty:
                opts = sorted(list(set(st.session_state.category_options + ["待分類"])))
                edt_df = st.data_editor(
                    f_df,
                    column_config={
                        "類別": st.column_config.SelectboxColumn("分類修正", options=opts),
                        "金額": st.column_config.NumberColumn("金額", format="$%d")
                    },
                    use_container_width=True, hide_index=True, key="main_editor"
                )

                # 儲存變動
                if st.session_state.main_editor.get("edited_rows"):
                    for idx_s, change in st.session_state.main_editor["edited_rows"].items():
                        real_idx = f_df.index[int(idx_s)]
                        for f, v in change.items(): 
                            st.session_state.working_df.at[real_idx, f] = v
                    
                    if st.button("💾 確認儲存至雲端"):
                        conn.update(worksheet=target_month, data=st.session_state.working_df)
                        st.success("✅ 雲端已更新！")
                        time.sleep(1)
                        st.rerun()

                # --- 統計圖表 (隨篩選變動) ---
                sum_df = f_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
                
                st.divider()
                st.markdown("### 🏆 消費排行榜")
                cols = st.columns(4)
                for i, row in sum_df.iterrows():
                    with cols[i % 4]:
                        icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
                        st.markdown(f"""
                            <div class="rank-card">
                                <div class="rank-name">{icon} {row['類別']}</div>
                                <div class="rank-price">${int(row['金額']):,}</div>
                            </div>
                        """, unsafe_allow_html=True)

                st.divider()
                st.markdown("### 🥧 支出佔比分析")
                fig = px.pie(sum_df, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                fig.add_annotation(text=f"總支出<br><b>${sum_df['金額'].sum():,.0f}</b>", showarrow=False, font=dict(size=22))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("請至少勾選一個類別以顯示資料與圖表。")

    except Exception as e:
        st.error(f"⚠️ 存取試算表時發生錯誤：{e}")
