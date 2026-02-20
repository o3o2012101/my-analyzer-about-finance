import streamlit as st
import pandas as pd
import plotly.express as px
import io
import random

st.set_page_config(page_title="Richart AI 終極報表", page_icon="⚪", layout="wide")

# --- 1. CSS 樣式 ---
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    div[data-testid="stMetric"] { border-bottom: 2px solid #F5F5F5; padding: 10px 0px; }
    .rank-box { padding: 20px; border-radius: 12px; background-color: #FDFDFD; border: 1px solid #F0F0F0; text-align: center; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端規則讀取 ---
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"

def load_rules():
    url = f"{SHEET_CSV_URL}&cache_buster={random.randint(1, 99999)}"
    try:
        rules_df = pd.read_csv(url)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except: return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 3. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定中心")
    if st.button("🔄 同步雲端規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.rerun()
    st.markdown(f"[📝 編輯 Google Sheets]({EDIT_URL})")

# --- 4. 主頁面 ---
st.title("帳務分析報表")
uploaded_file = st.file_uploader("📥 上傳 Richart Excel", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    # 讀取資料 (僅在第一次上傳或重新整理時執行)
    if 'main_df' not in st.session_state:
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
                    for cat, kws in st.session_state.category_rules.items():
                        if any(k in t for k in kws): return cat
                    return "待分類"
                df['類別'] = df[c_desc].apply(classify)
                st.session_state.main_df = df[[c_date, c_desc, c_amt, '類別']]
        except Exception as e:
            st.error(f"讀取錯誤: {e}")

    # 如果有資料，開始計算與顯示
    if 'main_df' in st.session_state:
        # 重要：從編輯器獲取最新變動並更新資料
        edited_df = st.data_editor(
            st.session_state.main_df,
            column_config={
                "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
                "消費金額": st.column_config.NumberColumn("金額", format="$%d")
            },
            use_container_width=True, hide_index=True, height=400,
            key="data_editor_main" # 設定 key 追蹤變動
        )
        
        # 使用編輯後的 edited_df 進行即時計算
        total_sum = edited_df.iloc[:, 2].sum() # 假設金額在第三欄
        summary = edited_df.groupby('類別').iloc[:, 2].sum().sort_values(ascending=False).reset_index()
        summary.columns = ['類別', '金額']

        # --- 顯示排行 ---
        st.divider()
        st.markdown("### 🏆 全類別消費排行榜")
        cols_per_row = 4
        for i in range(0, len(summary), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(summary):
                    row = summary.iloc[i + j]
                    idx = i + j
                    icon = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"#{idx+1}"
                    with cols[j]:
                        st.markdown(f'<div class="rank-box"><div style="color:#666;">{icon} {row["類別"]}</div><div style="font-size:1.6rem;color:#4A90E2;">{int(row["金額"]):,}元</div></div>', unsafe_allow_html=True)

        # --- 顯示圖表 ---
        st.divider()
        st.plotly_chart(px.pie(summary, values='金額', names='類別', hole=0.7, color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)
        
        # 匯出按鈕
        st.download_button("📤 匯出目前報表", edited_df.to_csv(index=False).encode('utf-8-sig'), "report.csv", "text/csv")
