import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Richart 帳單專家", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# 1. 定義初始分類規則（針對你的明細優化）
DEFAULT_RULES = {
    "餐飲": ["統一超商", "全家", "ok超商", "優食", "八曜和茶", "牛排", "麥當勞"],
    "交通": ["優步", "車隊", "高鐵", "台鐵", "捷運", "中油"],
    "購物": ["連支", "蝦皮", "樂購", "apple.com", "chance", "uniqlo"],
    "基本固定開銷": ["電信", "水費", "電費", "保費", "國外交易服務費", "trip.com"] # 旅遊暫歸此處或可自訂
}

uploaded_file = st.file_uploader("上傳 Richart 信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    # 讀取資料，跳過標題行（Richart 匯出通常第一行是卡片資訊）
    df = pd.read_excel(uploaded_file, header=1)
    
    # 清理資料：移除空行並確保金額為數字
    df = df.dropna(subset=['消費明細(含消費地)', '消費金額'])
    df['消費金額'] = pd.to_numeric(df['消費金額'], errors='coerce')

    # 2. 自動分類邏輯
    def classify(desc):
        desc = str(desc).lower()
        for cat, keywords in DEFAULT_RULES.items():
            if any(key.lower() in desc for key in keywords):
                return cat
        return "待分類"

    if '手動分類' not in st.session_state:
        df['類別'] = df['消費明細(含消費地)'].apply(classify)
    else:
        df['類別'] = st.session_state['手動分類']

    # 3. 處理「待分類」項目 (滿足手動分類需求)
    unclassified = df[df['類別'] == "待分類"]
    if not unclassified.empty:
        st.warning(f"偵測到 {len(unclassified)} 筆無法識別的消費，請在下方手動分類")
        with st.expander("🛠️ 執行手動分類"):
            for idx, row in unclassified.iterrows():
                new_cat = st.selectbox(
                    f"項目：{row['消費明細(含消費地)']} (${row['消費金額']})",
                    options=["餐飲", "交通", "購物", "基本固定開銷", "其他"],
                    key=f"select_{idx}"
                )
                df.at[idx, '類別'] = new_cat

    # 4. 圖表分析頁面
    st.divider()
    summary = df.groupby('類別')['消費金額'].sum().reset_index()
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("💰 分類金額匯總")
        fig = px.pie(summary, values='消費金額', names='類別', hole=0.5,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("🔍 類別明細展開")
        selected_cat = st.selectbox("點選類別查看明細", options=summary['類別'].unique())
        
        # 展開該類別的詳細消費
        details = df[df['類別'] == selected_cat][['消費日期', '消費明細(含消費地)', '消費金額']]
        st.dataframe(details, use_container_width=True, hide_index=True)
        
        cat_total = details['消費金額'].sum()
        st.info(f"【{selected_cat}】類別總計：${cat_total:,.0f}")

    # 下載分析後的 Excel
    st.download_button("📥 下載分類完成的報表", df.to_csv(index=False).encode('utf-8-sig'), "analyzed_expenses.csv")
