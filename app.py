import streamlit as st
import pandas as pd
import plotly.express as px
import io
import random

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 終極理財報表", page_icon="⚪", layout="wide")

# 自定義 CSS (極簡質感風，確保 HTML 不會露出)
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    div[data-testid="stMetric"] { border-bottom: 2px solid #F5F5F5; padding: 10px 0px; }
    .rank-card {
        padding: 15px;
        border-radius: 12px;
        background-color: #F8F9FA;
        border: 1px solid #EEEEEE;
        text-align: center;
        margin-bottom: 10px;
    }
    .rank-icon { font-size: 1.2rem; margin-bottom: 5px; }
    .rank-cat { color: #333; font-weight: 500; }
    .rank-amt { font-size: 1.6rem; color: #4A90E2; font-weight: bold; margin-top: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端規則同步邏輯 ---
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"

def load_rules():
    # 加入隨機數防止讀取到舊的 Google Sheets 緩存
    url = f"{SHEET_CSV_URL}&cache_buster={random.randint(1, 99999)}"
    try:
        rules_df = pd.read_csv(url)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        # 建立規則字典：分類名稱 -> 關鍵字列表
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except:
        return {"預設": []}

# 初始化規則到 Session State
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 3. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定中心")
    if st.button("🔄 同步雲端最新規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.success("同步成功！已抓取最新分類名稱。")
        st.rerun()
    st.markdown(f"[📝 編輯 Google 表格](https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit)")
    st.divider()
    with st.expander("👀 目前生效分類"):
        st.write(list(st.session_state.category_rules.keys()))

# --- 4. 主頁面 ---
st.title("帳務分析報表")
uploaded_file = st.file_uploader("📥 上傳 Richart Excel", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    # 確保資料只在第一次上傳時讀取
    if 'working_df' not in st.session_state:
        try:
            df_raw = pd.read_excel(uploaded_file, header=None)
            header_idx = 0
            for i, row in df_raw.iterrows():
                if "消費明細" in "".join(str(v) for v in row.values):
                    header_idx = i
                    break
            
            df = pd.read_excel(uploaded_file, header=header_idx)
            df.columns = [str(c).strip() for c in df.columns]
            
            # 找到關鍵欄位（日期、明細、金額）
            c_desc = next((c for c in df.columns if "明細" in c), "消費明細")
            c_amt = next((c for c in df.columns if "金額" in c), "金額")
            c_date = next((c for c in df.columns if "日期" in c), "日期")
            
            # 清洗金額與排除空白
            df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[c_desc])
            
            # 自動分類函數
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            
            df['類別'] = df[c_desc].apply(classify)
            
            # 將 DataFrame 標準化後存入 Session
            st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(
                columns={c_date: '日期', c_desc: '消費明細', c_amt: '金額'}
            )
        except Exception as e:
            st.error(f"檔案解析失敗：{e}")

    # --- 核心邏輯：即時連動與呈現 ---
    if 'working_df' in st.session_state:
        
        # A. 明細管理區 (放在最前面，確保編輯結果能即時傳遞給下方的圖表)
        st.markdown("### 🔍 明細管理與修正")
        edited_df = st.data_editor(
            st.session_state.working_df,
            column_config={
                "類別": st.column_config.SelectboxColumn(
                    "分類修正", 
                    # 關鍵：動態抓取最新的規則 Key 值，解決「餐飲/吃飯」名稱不對應問題
                    options=list(st.session_state.category_rules.keys()) + ["待分類"]
                ),
                "金額": st.column_config.NumberColumn("金額", format="$%d")
            },
            use_container_width=True, 
            hide_index=True, 
            height=350,
            key="main_editor"
        )

        # B. 根據 edited_df 即時計算數據
        # (這裡不需要 iloc，直接用欄位名稱更穩定)
        summary = edited_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
        total_sum = summary['金額'].sum()

        # C. 數據摘要指標
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.metric("💰 總支出", f"${total_sum:,.0f}")
        m2.metric("🏆 消費大宗", summary.iloc[0]['類別'] if not summary.empty else "-")
        m3.metric("📋 紀錄筆數", f"{len(edited_df)} 筆")

        # D. 獎牌排行榜 (全量顯示所有類別)
        st.divider()
        st.markdown("### 🏆 消費排行榜")
        
        cols_per_row = 4
        for i in range(0, len(summary), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(summary):
                    row = summary.iloc[i + j]
                    idx = i + j
                    # 獎牌與序號邏輯
                    icon = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"#{idx+1}"
                    with cols[j]:
                        st.markdown(f"""
                        <div class="rank-card">
                            <div class="rank-icon">{icon} <span class="rank-cat">{row['類別']}</span></div>
                            <div class="rank-amt">{int(row['金額']):,}元</div>
                        </div>
                        """, unsafe_allow_html=True)

        # E. 圓餅圖 (排除佔比太小的視覺干擾)
        st.divider()
        st.markdown("### 🥧 支出佔比分析")
        fig_pie = px.pie(summary, values='金額', names='類別', hole=0.7, 
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pie.update_layout(margin=dict(t=30, b=30, l=30, r=30))
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # F. 匯出按鈕
        csv_data = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📤 匯出修正後的報表", csv_data, "finance_report.csv", "text/csv")
