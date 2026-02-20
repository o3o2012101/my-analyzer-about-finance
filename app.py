import streamlit as st
import pandas as pd
import plotly.express as px
import io
import time
import random

# 1. 頁面基礎設定
st.set_page_config(page_title="極簡帳務分析", page_icon="⚪", layout="wide")

# 自定義 CSS (極簡風)
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    div[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #EEEEEE; }
    .stButton>button { width: 100%; border-radius: 4px; border: 1px solid #E0E0E0; background-color: transparent; color: #444444; }
    div[data-testid="stMetric"] { border-bottom: 2px solid #F5F5F5; padding: 10px 0px; }
    h1, h2, h3 { font-weight: 300 !important; color: #333333; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連結設定 ---
# 這是你的編輯連結
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"

# --- 3. 強制同步讀取函數 ---
def load_rules_force():
    # 這裡加上隨機參數，防止 Google 或 Streamlit 緩存舊資料
    sheet_url = f"https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0&cache_buster={random.randint(1, 100000)}"
    try:
        rules_df = pd.read_csv(sheet_url)
        # 清理欄位空白
        rules_df.columns = [c.strip() for c in rules_df.columns]
        rules_dict = {}
        for _, row in rules_df.iterrows():
            cat = str(row['分類名稱']).strip()
            if cat and cat != 'nan':
                # 清理關鍵字空白
                kws = [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip() and k != 'nan']
                rules_dict[cat] = kws
        return rules_dict
    except Exception as e:
        st.sidebar.error(f"讀取失敗：{e}")
        return {"預設": []}

# 初始化
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules_force()

# --- 4. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定")
    st.markdown(f"[📝 點我開啟雲端表格]({EDIT_URL})")
    
    if st.button("🔄 強制同步雲端規則"):
        with st.spinner('同步中...'):
            # 清除所有緩存並重新讀取
            st.cache_data.clear()
            st.session_state.category_rules = load_rules_force()
            time.sleep(1) # 給系統一點反應時間
            st.success("同步成功！")
            st.rerun()

    st.divider()
    # 顯示目前抓到的規則，方便檢查
    with st.expander("👀 查看目前生效規則"):
        st.write(st.session_state.category_rules)

# --- 5. 主頁面 (邏輯維持極簡質感) ---
st.title("帳務分析報表")
uploaded_file = st.file_uploader("", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_raw.iterrows():
            if "消費明細" in "".join(str(v) for v in row.values):
                header_idx = i
                break
        
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        c_desc = next((c for c in df.columns if "明細" in c), None)
        c_amt = next((c for c in df.columns if "金額" in c), None)
        c_date = next((c for c in df.columns if "日期" in c), None)

        if c_desc and c_amt:
            df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[c_desc])

            def classify(t):
                t = str(t).lower()
                # 使用 session_state 裡的最新規則
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            
            df['類別'] = df[c_desc].apply(classify)

            # 數據摘要
            total_sum = df[c_amt].sum()
            summary_df = df.groupby('類別')[c_amt].sum().sort_values(ascending=False).reset_index()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("總支出", f"${total_sum:,.0f}")
            c2.metric("最大開銷", summary_df.iloc[0]['類別'] if not summary_df.empty else "-")
            c3.metric("紀錄比數", f"{len(df)} 筆")

            st.markdown("<br>", unsafe_allow_html=True)
            t1, t2 = st.tabs(["📊 數據圖表", "📋 明細管理"])

            with t1:
                col_a, col_b = st.columns(2)
                with col_a:
                    fig_pie = px.pie(summary_df, values=c_amt, names='類別', hole=0.7, color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_b:
                    fig_rank = px.bar(summary_df, x=c_amt, y='類別', orientation='h', color_discrete_sequence=['#555555'])
                    fig_rank.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_rank, use_container_width=True)

            with t2:
                st.data_editor(
                    df[[c_date, c_desc, c_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn("分類", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
                        c_amt: st.column_config.NumberColumn("金額", format="$%d")
                    },
                    use_container_width=True, hide_index=True
                )
    except Exception as e:
        st.error(f"解析錯誤: {e}")
