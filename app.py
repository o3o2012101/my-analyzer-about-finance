import streamlit as st
import pandas as pd
import plotly.express as px
import io
import random

# 1. 頁面基礎設定
st.set_page_config(page_title="Richart AI 終極報表", page_icon="⚪", layout="wide")

# 自定義 CSS (極簡質感風)
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    div[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #EEEEEE; }
    .stButton>button { width: 100%; border-radius: 4px; border: 1px solid #E0E0E0; background-color: transparent; color: #444444; }
    div[data-testid="stMetric"] { border-bottom: 2px solid #F5F5F5; padding: 10px 0px; }
    h1, h2, h3 { font-weight: 300 !important; color: #333333; }
    
    /* 強化排行榜字卡質感 */
    .rank-box {
        padding: 20px;
        border-radius: 12px;
        background-color: #FDFDFD;
        border: 1px solid #F0F0F0;
        text-align: center;
        margin-bottom: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連結與同步邏輯 ---
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"

def load_rules_force():
    url = f"{SHEET_CSV_URL}&cache_buster={random.randint(1, 99999)}"
    try:
        rules_df = pd.read_csv(url)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except:
        return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules_force()

# --- 3. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定中心")
    st.markdown(f"[📝 打開雲端表格]({EDIT_URL})")
    if st.button("🔄 同步規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules_force()
        st.rerun()
    st.divider()
    with st.expander("👀 目前生效規則"):
        st.write(st.session_state.category_rules)

# --- 4. 主頁面內容 ---
st.title("帳務分析報表")
uploaded_file = st.file_uploader("📥 上傳 Richart Excel", type=["xlsx"], label_visibility="collapsed")

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
        c_desc, c_amt, c_date = next((c for c in df.columns if "明細" in c), None), next((c for c in df.columns if "金額" in c), None), next((c for c in df.columns if "日期" in c), None)

        if c_desc and c_amt:
            df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[c_desc])
            
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            df['類別'] = df[c_desc].apply(classify)

            # 數據摘要
            total_sum = df[c_amt].sum()
            summary = df.groupby('類別')[c_amt].sum().sort_values(ascending=False).reset_index()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 總支出", f"${total_sum:,.0f}")
            m2.metric("🏆 第一名", summary.iloc[0]['類別'] if not summary.empty else "-")
            m3.metric("📋 筆數", f"{len(df)} 筆")

            # --- 🏆 全類別消費排行榜 (修復版：保證無原始碼) ---
            st.divider()
            st.markdown("### 🏆 全類別消費排行榜")
            
            # 使用每行 4 個的佈局
            cols_per_row = 4
            for i in range(0, len(summary), cols_per_row):
                cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(summary):
                        row = summary.iloc[i + j]
                        index = i + j
                        if index == 0: icon = "🥇"
                        elif index == 1: icon = "🥈"
                        elif index == 2: icon = "🥉"
                        else: icon = f"#{index + 1}"
                        
                        with cols[j]:
                            st.markdown(f"""
                            <div class="rank-box">
                                <div style="font-size: 1.1rem; color: #666;">{icon} {row['類別']}</div>
                                <div style="font-size: 1.6rem; font-weight: 500; color: #4A90E2; margin-top: 5px;">
                                    {int(row[c_amt]):,}元
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

            # --- 圓餅圖 ---
            st.divider()
            st.markdown("### 🥧 支出佔比")
            st.plotly_chart(px.pie(summary, values=c_amt, names='類別', hole=0.7, color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)

            # --- 明細編輯區 ---
            st.divider()
            st.markdown("### 🔍 明細管理與修正")
            st.data_editor(
                df[[c_date, c_desc, c_amt, '類別']],
                column_config={
                    "類別": st.column_config.SelectboxColumn("分類", options=list(st.session_state.category_rules.keys()) + ["待分類"]), 
                    c_amt: st.column_config.NumberColumn("金額", format="$%d")
                },
                use_container_width=True, hide_index=True, height=500
            )
            st.download_button("📤 匯出報表", df.to_csv(index=False).encode('utf-8-sig'), "report.csv", "text/csv")

    except Exception as e:
        st.error(f"系統錯誤: {e}")
