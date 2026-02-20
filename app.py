import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 頁面設定
st.set_page_config(page_title="Richart AI 雲端記憶版", page_icon="☁️", layout="wide")

# 套用基礎美化 CSS
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stSidebarNav"] { padding-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. 雲端連結設定 (使用您提供的網址) ---
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pub?output=csv"
# 編輯用連結
EMBED_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&headers=false"

# --- 2. 核心功能：讀取雲端規則 ---
@st.cache_data(ttl=5)
def load_rules_from_sheets():
    try:
        rules_df = pd.read_csv(SHEET_CSV_URL)
        # 清理欄位名稱，避免空格導致抓不到
        rules_df.columns = [c.strip() for c in rules_df.columns]
        
        rules_dict = {}
        # 遍歷表格，建立分類字典
        for _, row in rules_df.iterrows():
            cat = str(row['分類名稱']).strip()
            if cat and cat != 'nan':
                # 處理關鍵字清單
                kws = [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip() and k != 'nan']
                rules_dict[cat] = kws
        return rules_dict
    except Exception as e:
        st.sidebar.error(f"❌ 雲端同步失敗：{e}")
        return {"預設分類": []}

# 初始化規則
st.session_state.category_rules = load_rules_from_sheets()

# --- 3. 左側面板：鑲嵌 Google Sheets 編輯器 ---
with st.sidebar:
    st.header("☁️ 雲端規則編輯器")
    st.caption("在下方直接編輯後，務必點擊「同步」按鈕。")
    
    # 內嵌編輯視窗 (使用 iframe)
    st.components.v1.iframe(EMBED_URL, height=550, scrolling=True)
    
    if st.button("🔄 同步雲端最新規則", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules_from_sheets()
        st.toast("規則已從 Google Sheets 更新！", icon="✅")
        st.rerun()
    
    st.divider()
    st.info("💡 貼心提醒：若 Google 表格顯示『唯讀』，請確認試算表共用權限已開啟為『知道連結的人均可編輯』。")

# --- 4. 檔案處理核心 ---
st.subheader("📤 第一步：上傳本月明細")
uploaded_file = st.file_uploader("請拖入 Richart 信用卡 Excel 檔案", type=["xlsx"], label_visibility="collapsed")

if uploaded_file:
    try:
        # 標題偵測邏輯
        df_temp = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_temp.iterrows():
            row_str = "".join(str(v) for v in row.values)
            if "消費明細" in row_str:
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

            # 自動分類邏輯
            def auto_classify(text):
                text = str(text).lower()
                for cat, keywords in st.session_state.category_rules.items():
                    if any(k in text for k in keywords):
                        return cat
                return "待分類"

            df['類別'] = df[col_desc].apply(auto_classify)

            # --- 5. 圓餅圖與明細篩選區 ---
            st.divider()
            col_chart, col_detail = st.columns([1, 1.2])

            with col_chart:
                st.subheader("📊 消費支出佔比")
                summary = df.groupby('類別')[col_amt].sum().reset_index()
                fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2))
                st.plotly_chart(fig, use_container_width=True)

            with col_detail:
                st.subheader("🔍 分類細節管理")
                target_cat = st.selectbox("🎯 選擇類別檢視：", options=["全部項目"] + list(df['類別'].unique()))
                
                filtered_df = df if target_cat == "全部項目" else df[df['類別'] == target_cat]
                
                # 小計面板
                st.metric(label=f"💰 {target_cat} 總計", value=f"${filtered_df[col_amt].sum():,.0f}")
                
                # 互動表格
                st.data_editor(
                    filtered_df[[col_date, col_desc, col_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn("修正分類", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
                        "金額": st.column_config.NumberColumn(format="$%d")
                    },
                    use_container_width=True, hide_index=True
                )

            # --- 6. 下方排名與總結 ---
            st.divider()
            st.subheader("🏆 本月消費實力排行")
            
            total_sum = df[col_amt].sum()
            rank_df = df.groupby('類別')[col_amt].sum().sort_values(ascending=False).reset_index()
            
            # 排名動態顯示
            rank_cols = st.columns(len(rank_df) if len(rank_df) < 5 else 5)
            for i, row in rank_df.iterrows():
                with rank_cols[i % 5]:
                    st.metric(label=f"No.{i+1} {row['類別']}", 
                              value=f"${row[col_amt]:,.0f}", 
                              delta=f"{(row[col_amt]/total_sum*100):.1f}%")

            st.success(f"🏁 結算完成！本月信用卡總支出共計： **${total_sum:,.0f}**")
            
            # 下載按鈕
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載分類後的 Excel (CSV)", csv, "report.csv", "text/csv", type="primary")

        else:
            st.error("❌ 欄位偵測失敗，請確認 Excel 是否包含『消費明細』與『金額』。")

    except Exception as e:
        st.error(f"⚠️ 發生未知錯誤：{e}")
