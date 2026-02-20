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

# --- 2. 質感 CSS (修正按鈕過大問題) ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    /* 限制排行榜按鈕高度與間距 */
    div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div { margin-bottom: -10px; }
    .stButton>button {
        border-radius: 12px;
        padding: 10px;
        height: auto;
        min-height: 80px;
        border: 1px solid #E0E0E0;
        background: #F8F9FA;
        transition: 0.2s;
    }
    .stButton>button:hover {
        border-color: #4A90E2;
        background: #FFFFFF;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
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
        # 強制刷新讀取 Sheet1 規則清單
        rules_df = conn.read(worksheet="Sheet1", ttl="0s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        opts = sorted([str(c).strip() for c in rules_df['分類名稱'].dropna().unique() if str(c).strip() != 'nan'])
        # 建立關鍵字比對字典
        rules_dict = {str(r['分類名稱']).strip(): [k.strip().lower() for k in str(r['關鍵字']).split(",") if k.strip()] 
                      for _, r in rules_df.iterrows() if str(r['分類名稱']).strip() != 'nan'}
        return opts, rules_dict
    except: return [], {}

# 初始載入
if 'opts' not in st.session_state:
    st.session_state.opts, st.session_state.rules = load_rules()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 控制面板")
    target_month = st.text_input("分析月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端規則"):
        st.session_state.opts, st.session_state.rules = load_rules()
        st.success("最新規則已載入！")
        st.rerun()

# --- 5. 大視窗明細對話框 ---
@st.dialog("📋 消費明細深入查看", width="large")
def show_details(cat, data):
    st.subheader(f"類別：{cat}")
    detail_df = data[data['類別'] == cat][['日期', '消費明細', '金額']].sort_values('日期', ascending=False)
    st.dataframe(detail_df, use_container_width=True, hide_index=True)
    st.metric("該類別累計支出", f"${int(detail_df['金額'].sum()):,}")

# --- 6. 核心數據處理 ---
if gc:
    try:
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        def get_or_create_ws(name):
            try: return sh.worksheet(name)
            except: return sh.add_worksheet(title=name, rows="1000", cols="20")

        # 讀取目標月份資料
        try:
            df_m = conn.read(worksheet=target_month, ttl="0s")
            if not df_m.empty: 
                # 確保日期格式美化
                if '日期' in df_m.columns:
                    df_m['日期'] = pd.to_datetime(df_m['日期']).dt.strftime('%Y-%m-%d')
                st.session_state.working_df = df_m
                st.session_state.curr_m = target_month
        except:
            if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
                del st.session_state.working_df

        st.title(f"📊 {target_month} 財務儀表板")

        # 上傳邏輯
        if 'working_df' not in st.session_state:
            st.info(f"💡 請上傳 {target_month} 的 Richart Excel 以初始化。")
            u_file = st.file_uploader("📥 上傳 Excel", type=["xlsx"])
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
                new_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
                new_df['日期'] = pd.to_datetime(new_df['日期']).dt.strftime('%Y-%m-%d')
                get_or_create_ws(target_month)
                conn.update(worksheet=target_month, data=new_df)
                st.session_state.working_df = new_df
                st.rerun()

        # 展示與連動
        if 'working_df' in st.session_state:
            w_df = st.session_state.working_df
            sum_df = w_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()

            # --- 🏆 排行榜 (縮小按鈕) ---
            st.subheader("🏆 支出排行 (點擊看明細)")
            n_cols = 4
            cols = st.columns(n_cols)
            for i, row in sum_df.iterrows():
                with cols[i % n_cols]:
                    rank_icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "💰"
                    # 使用 markdown 包裹模擬更小的卡片感
                    if st.button(f"{rank_icon} {row['類別']}\n${int(row['金額']):,}", key=f"r_{row['類別']}", use_container_width=True):
                        show_details(row['類別'], w_df)

            st.divider()

            # --- 🔍 管理與修正 ---
            c1, c2 = st.columns([6, 4])
            with c1:
                st.subheader("🔍 明細修正")
                all_c = sorted(w_df['類別'].unique())
                sel_c = st.multiselect("過濾顯示類別：", options=all_c, default=all_c)
                filtered_df = w_df[w_df['類別'].isin(sel_c)].copy()
                
                opts = sorted(list(set(st.session_state.opts + ["待分類"])))
                # 這裡確保 data_editor 的異動能準確寫回
                edited_df = st.data_editor(
                    filtered_df,
                    column_config={"類別": st.column_config.SelectboxColumn("分類修正", options=opts, width="medium")},
                    use_container_width=True, hide_index=True, key="editor_key"
                )
                
                if st.button("💾 儲存修改並同步雲端"):
                    # 獲取 editor 的異動
                    if st.session_state.editor_key.get("edited_rows"):
                        # 將異動套用到 working_df
                        for idx_str, changes in st.session_state.editor_key["edited_rows"].items():
                            actual_idx = filtered_df.index[int(idx_str)]
                            for col, val in changes.items():
                                st.session_state.working_df.at[actual_idx, col] = val
                        
                        conn.update(worksheet=target_month, data=st.session_state.working_df)
                        st.success("✅ 同步完成！")
                        time.sleep(1)
                        st.rerun()

            with c2:
                st.subheader("🥧 支出佔比")
                fig = px.pie(sum_df, values='金額', names='類別', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"⚠️ 系統異常：{e}")
