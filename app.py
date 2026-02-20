import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 頁面設定
st.set_page_config(page_title="Richart AI 雲端記憶版", page_icon="☁️", layout="wide")

# --- 1. 聯動 Google Sheets (讀取功能) ---
# 請將這裡的網址換成你的 Google Sheet 「發佈到網路」後的 CSV 下載連結
# 格式通常是：<iframe src="https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&amp;headers=false"></iframe>
SHEET_CSV_URL = "<iframe src="https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&amp;headers=false"></iframe>"

@st.cache_data(ttl=10) # 每10秒自動更新一次快取
def load_rules_from_sheets():
    try:
        rules_df = pd.read_csv(SHEET_CSV_URL)
        rules_dict = {}
        for _, row in rules_df.iterrows():
            # 將關鍵字轉為清單
            kws = [k.strip() for k in str(row['關鍵字']).split(",") if k.strip()]
            rules_dict[row['分類名稱']] = kws
        return rules_dict
    except:
        return {"錯誤": ["無法讀取雲端表單"]}

# 初始化規則
st.session_state.category_rules = load_rules_from_sheets()

# --- 2. 左側面板：鑲嵌 Google Sheet 編輯器 ---
with st.sidebar:
    st.header("☁️ 雲端規則編輯器")
    st.caption("直接在下方編輯表格，系統會自動同步記憶。")
    
    # 鑲嵌 Google Sheets 視窗
    # 請替換為你的內嵌網址
    EMBED_URL = "你的試算表鑲嵌網址" 
    st.components.v1.iframe(EMBED_URL, height=500, scrolling=True)
    
    if st.button("🔄 同步雲端最新規則", type="primary"):
        st.cache_data.clear()
        st.rerun()

# --- 3. 檔案處理與分類 (維持原有強大功能) ---
uploaded_file = st.file_uploader("📤 上傳信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    try:
        # (標題偵測邏輯同前，確保相容 Richart 格式)
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
            
            def auto_classify(text):
                text = str(text).lower()
                for cat, keywords in st.session_state.category_rules.items():
                    if any(k.lower() in text for k in keywords):
                        return cat
                return "待分類"
            df['類別'] = df[col_desc].apply(auto_classify)

            # --- 4. 儀表板視覺化 ---
            st.divider()
            col_chart, col_detail = st.columns([1, 1.2])

            with col_chart:
                st.subheader("📊 消費支出佔比")
                summary = df.groupby('類別')[col_amt].sum().reset_index()
                fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.5)
                st.plotly_chart(fig, use_container_width=True)

            with col_detail:
                st.subheader("🔍 明細管理與小計")
                target_cat = st.selectbox("🎯 篩選類別：", options=["全部項目"] + list(df['類別'].unique()))
                filtered_df = df if target_cat == "全部項目" else df[df['類別'] == target_cat]
                st.metric(label=f"💰 【{target_cat}】小計", value=f"${filtered_df[col_amt].sum():,.0f}")
                
                st.data_editor(filtered_df[[col_date, col_desc, col_amt, '類別']], use_container_width=True, hide_index=True)

            # --- 5. 下方排行與總結 ---
            st.divider()
            total_sum = df[col_amt].sum()
            st.success(f"🏁 本月總結算支出： **${total_sum:,.0f}**")
            
            # 橫向排名圖
            rank_df = df.groupby('類別')[col_amt].sum().sort_values(ascending=False).reset_index()
            fig_rank = px.bar(rank_df, x=col_amt, y='類別', orientation='h', color='類別')
            st.plotly_chart(fig_rank, use_container_width=True)

    except Exception as e:
        st.error(f"偵測異常: {e}")
