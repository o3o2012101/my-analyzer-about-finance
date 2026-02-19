import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Richart 帳單專家", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# 分類規則庫
DEFAULT_RULES = {
    "餐飲": ["統一超商", "全家", "ok超商", "優食", "uber eats", "八曜和茶", "牛排", "麥當勞", "星巴克", "雅室", "美食", "必勝客", "餐廳"],
    "交通": ["優步", "uber", "車隊", "高鐵", "台鐵", "捷運", "中油", "taxi", "大慶", "皇冠", "停車", "和運"],
    "購物": ["連支", "街口", "蝦皮", "樂購", "apple.com", "chance", "uniqlo", "momo", "貓纜", "美妝", "pchome"],
    "基本固定開銷": ["電信", "水費", "電費", "保費", "國外交易服務費", "trip.com", "訂房", "google", "icloud", "netflix"]
}

uploaded_file = st.file_uploader("上傳您的信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    try:
        # 1. 模糊搜尋標題行
        df_temp = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_temp.iterrows():
            combined_text = "".join(str(v) for v in row.values)
            if "消費明細" in combined_text:
                header_idx = i
                break
        
        # 2. 重新讀取並清理欄位
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]

        # 3. 模糊鎖定關鍵欄位 (只要包含「明細」或「金額」就抓)
        col_desc = next((c for c in df.columns if "明細" in c), None)
        col_amt = next((c for c in df.columns if "金額" in c), None)
        col_date = next((c for c in df.columns if "日期" in c), None)

        if col_desc and col_amt:
            df[col_amt] = pd.to_numeric(df[col_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[col_desc])

            # 4. 自動分類
            def classify(text):
                text = str(text).lower()
                for cat, keywords in DEFAULT_RULES.items():
                    if any(k.lower() in text for k in keywords):
                        return cat
                return "待分類"

            df['類別'] = df[col_desc].apply(classify)

            # --- UI 介面 ---
            st.divider()
            
            # 手動修正
            unclassified = df[df['類別'] == "待分類"]
            if not unclassified.empty:
                with st.expander(f"🛠️ 有 {len(unclassified)} 筆項目需要手動分類"):
                    for idx, row in unclassified.iterrows():
                        chosen = st.selectbox(f"項目: {row[col_desc]} (${row[col_amt]})", 
                                            options=["待分類", "餐飲", "交通", "購物", "基本固定開銷", "其他"], 
                                            key=f"m_{idx}")
                        if chosen != "待分類":
                            df.at[idx, '類別'] = chosen

            # 圖表展示
            summary = df.groupby('類別')[col_amt].sum().reset_index()
            plot_df = summary[summary[col_amt] > 0]
            
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("📊 消費支出佔比")
                fig = px.pie(plot_df, values=col_amt, names='類別', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("🔍 分類細節")
                sel_cat = st.selectbox("查看類別", options=df['類別'].unique())
                st.dataframe(df[df['類別'] == sel_cat][[col_date, col_desc, col_amt]], hide_index=True)
        else:
            st.error("找不到對應欄位，請確認 Excel 標題包含『消費明細』與『金額』。")

    except Exception as e:
        st.error(f"錯誤: {e}")
