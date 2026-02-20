import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 頁面設定
st.set_page_config(page_title="Richart AI 雲端記憶版", page_icon="☁️", layout="wide")

# 自定義 CSS 美化
st.markdown("""
    <style>
    .stButton>button { border-radius: 8px; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 雲端連結設定 ---
# 請確認此 ID 與您的試算表一致
SHEET_ID = "1X_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pub?output=csv"
# 編輯頁面的網址
EDIT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
# 預覽用的網址
PREVIEW_URL = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&headers=false"

# --- 2. 核心功能：讀取雲端規則 ---
@st.cache_data(ttl=5)
def load_rules_from_sheets():
    try:
        rules_df = pd.read_csv(SHEET_CSV_URL)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        rules_dict = {}
        for _, row in rules_df.iterrows():
            cat = str(row['分類名稱']).strip()
            if cat and cat != 'nan':
                kws = [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip() and k != 'nan']
                rules_dict[cat] = kws
        return rules_dict
    except Exception as e:
        st.sidebar.error(f"❌ 雲端同步失敗：{e}")
        return {"預設分類": []}

# 初始化規則
st.session_state.category_rules = load_rules_from_sheets()

# --- 3. 左側面板：編輯與預覽 ---
with st.sidebar:
    st.header("⚙️ 規則設定中心")
    
    # 解決方案：提供直接跳轉編輯的按鈕
    st.markdown(f"""
        <a href="{EDIT_URL}" target="_blank">
            <button style="
                width: 100%;
                background-color: #ff4b4b;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: bold;
                margin-bottom: 10px;">
                📝 點我打開 Google 表格編輯
            </button>
        </a>
    """, unsafe_allow_html=True)
    
    if st.button("🔄 同步雲端最新規則", type="secondary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules_from_sheets()
        st.toast("規則已更新！", icon="✅")
        st.rerun()

    st.divider()
    st.subheader("📋 目前雲端規則預覽")
    # 預覽視窗 (僅供對照)
    st.components.v1.iframe(PREVIEW_URL, height=400, scrolling=True)

# --- 4. 檔案處理與圖表 (維持原有邏輯) ---
st.subheader("📤 上傳信用卡明細")
uploaded_file = st.file_uploader("拖入 Richart Excel 檔案", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    try:
        # 標題偵測
        df_temp = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_temp.iterrows():
            if "消費明細" in "".join(str(v) for v in row.values):
                header_idx = i
                break
        
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        col_desc = next((c for c in df.columns if "明細" in c), None)
        col_amt = next((c for c in df.columns if "金額" in c), None)
        col_date = next((c for c in df.columns if "日期" in c), None)

        if col_desc and col_amt:
            df[col_amt] = pd.to_numeric(df[col_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[col_desc])

            def auto_classify(text):
                text = str(text).lower()
                for cat, keywords in st.session_state.category_rules.items():
                    if any(k in text for k in keywords):
                        return cat
                return "待分類"
            df['類別'] = df[col_desc].apply(auto_classify)

            # --- 5. 圓餅圖與明細 ---
            st.divider()
            col_chart, col_detail = st.columns([1, 1.2])

            with col_chart:
                st.subheader("📊 消費支出佔比")
                summary = df.groupby('類別')[col_amt].sum().reset_index()
                fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)

            with col_detail:
                st.subheader("🔍 分類細節管理")
                target_cat = st.selectbox("🎯 選擇類別：", options=["全部項目"] + list(df['類別'].unique()))
                filtered_df = df if target_cat == "全部項目" else df[df['類別'] == target_cat]
                st.metric(label=f"💰 總計", value=f"${filtered_df[col_amt].sum():,.0f}")
                
                st.data_editor(
                    filtered_df[[col_date, col_desc, col_amt, '類別']],
                    column_config={"類別": st.column_config.SelectboxColumn("修正", options=list(st.session_state.category_rules.keys()) + ["待分類"])},
                    use_container_width=True, hide_index=True
                )

            # --- 6. 排名總結 ---
            st.divider()
            total_sum = df[col_amt].sum()
            rank_df = df.groupby('類別')[col_amt].sum().sort_values(ascending=False).reset_index()
            
            rank_cols = st.columns(len(rank_df) if len(rank_df) < 5 else 5)
            for i, row in rank_df.iterrows():
                with rank_cols[i % 5]:
                    st.metric(label=f"No.{i+1} {row['類別']}", value=f"${row[col_amt]:,.0f}", delta=f"{(row[col_amt]/total_sum*100):.1f}%")

            st.success(f"🏁 本月總支出： **${total_sum:,.0f}**")
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載分類結果 Excel", csv, "report.csv", "text/csv", type="primary")

    except Exception as e:
        st.error(f"錯誤：{e}")
