import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Richart 帳單專家", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# 1. 根據您的需求重整消費類別與關鍵字
# 注意：類別名稱已依照您的要求調整（如：餐飲改為「吃飯」）
DEFAULT_RULES = {
    "吃飯": ["餐廳", "711", "全家", "ok超商", "優食", "uber eats", "八曜和茶", "牛排", "麥當勞", "星巴克", "雅室", "美食", "必勝客"],
    "交通": ["優步", "uber", "車隊", "高鐵", "台鐵", "捷運", "中油", "taxi", "大慶", "皇冠", "停車", "和運"],
    "購物": ["蝦皮", "coupang", "樂購", "chance", "uniqlo", "momo", "貓纜", "美妝", "pchome"],
    "旅遊開銷": ["客路", "klook", "trip.com", "訂房", "airbnb", "飯店", "旅館"],
    "基本固定開銷": [
        "netflix", "電信", "apple.com/billa", "連支＊一般商品買賣taipei", 
        "google", "icloud", "水費", "電費", "保費", "國外交易服務費"
    ]
}

uploaded_file = st.file_uploader("上傳您的信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    try:
        # 步驟 A: 模糊搜尋標題行
        df_temp = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_temp.iterrows():
            combined_row_text = "".join(str(v) for v in row.values)
            if "消費明細" in combined_row_text:
                header_idx = i
                break
        
        # 步驟 B: 以偵測到的行數重新讀取
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]

        # 步驟 C: 欄位名稱模糊搜尋
        col_desc = next((c for c in df.columns if "明細" in c), None)
        col_amt = next((c for c in df.columns if "金額" in c), None)
        col_date = next((c for c in df.columns if "日期" in c), None)

        if col_desc and col_amt:
            # 清理資料
            df[col_amt] = pd.to_numeric(df[col_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[col_desc])

            # 步驟 D: 自動分類邏輯 (精確匹配與關鍵字優化)
            def classify_refined(text):
                text = str(text).lower().replace(" ", "") # 移除空格方便比對
                for cat, keywords in DEFAULT_RULES.items():
                    for k in keywords:
                        if k.lower().replace(" ", "") in text:
                            return cat
                return "待分類"

            df['類別'] = df[col_desc].apply(classify_refined)

            # --- UI 介面展示 ---
            st.divider()
            
            # 2. 調整：無法識別的項目需顯示消費日期 (功能 1)
            unclassified_df = df[df['類別'] == "待分類"]
            if not unclassified_df.empty:
                with st.expander(f"🛠️ 有 {len(unclassified_df)} 筆「待分類」項目，請協助歸類"):
                    for idx, row in unclassified_df.iterrows():
                        # 在顯示標籤中加入日期
                        display_date = str(row[col_date]).split(" ")[0] if col_date else "無日期"
                        chosen = st.selectbox(
                            f"【{display_date}】項目: {row[col_desc]} (${row[col_amt]})",
                            options=["待分類", "吃飯", "交通", "購物", "旅遊開銷", "基本固定開銷", "其他"],
                            key=f"manual_v2_{idx}"
                        )
                        if chosen != "待分類":
                            df.at[idx, '類別'] = chosen

            # 3. 圖表分析
            summary = df.groupby('類別')[col_amt].sum().reset_index()
            plot_df = summary[summary[col_amt] > 0] 

            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.subheader("📊 消費支出佔比")
                fig = px.pie(plot_df, values=col_amt, names='類別', hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Safe)
                st.plotly_chart(fig, use_container_width=True)

            with col_right:
                st.subheader("🔍 分類細節展開")
                selected_cat = st.selectbox("請選擇類別查看明細", options=df['類別'].unique())
                view_cols = [c for c in [col_date, col_desc, col_amt] if c is not None]
                view_df = df[df['類別'] == selected_cat][view_cols].copy()
                st.dataframe(view_df, hide_index=True, use_container_width=True)
                st.metric(f"{selected_cat} 合計", f"${view_df[col_amt].sum():,.0f}")

        else:
            st.error("❌ 找不到關鍵欄位，請確認 Excel 標題包含『消費明細』與『金額』。")

    except Exception as e:
        st.error(f"⚠️ 系統錯誤: {e}")
