import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="個人化帳單分析師", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# --- 1. 動態規則設定區 ---
with st.sidebar:
    st.header("⚙️ 分類規則設定")
    st.info("您可以在此新增分類或修改關鍵字，系統會即時重新計算。")
    
    # 初始化預設規則（如果 session 裡還沒有的話）
    if 'category_map' not in st.session_state:
        st.session_state.category_map = [
            {"分類名稱": "吃飯", "關鍵字": "餐廳, 711, 全家, ok超商, 優食, uber eats, 八曜和茶, 牛排, 麥當勞, 星巴克, 雅室, 美食, 必勝客"},
            {"分類名稱": "交通", "關鍵字": "優步, uber, 車隊, 高鐵, 台鐵, 捷運, 中油, taxi, 大慶, 皇冠, 停車, 和運"},
            {"分類名稱": "購物", "關鍵字": "蝦皮, coupang, 樂購, chance, uniqlo, momo, 貓纜, 美妝, pchome"},
            {"分類名稱": "旅遊開銷", "關鍵字": "客路, klook, trip.com, 訂房, airbnb, 飯店, 旅館"},
            {"分類名稱": "基本固定開銷", "關鍵字": "netflix, 電信, apple.com/billa, 連支＊一般商品買賣taipei, google, icloud, 水費, 電費, 保費"}
        ]
    
    # 讓使用者在介面上直接編輯表格
    edited_map = st.data_editor(
        st.session_state.category_map,
        num_rows="dynamic", # 允許新增/刪除行
        use_container_width=True,
        key="rules_editor"
    )
    # 更新 session 狀態
    st.session_state.category_map = edited_map

# --- 2. 檔案處理邏輯 ---
uploaded_file = st.file_uploader("上傳您的信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    try:
        # 模糊搜尋標題行
        df_temp = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_temp.iterrows():
            combined_text = "".join(str(v) for v in row.values)
            if "消費明細" in combined_text:
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

            # --- 3. 根據使用者設定的規則進行分類 ---
            def classify_v3(text):
                text = str(text).lower().replace(" ", "")
                # 從 sidebar 的編輯器中抓取最新規則
                for rule in st.session_state.category_map:
                    cat_name = rule["分類名稱"]
                    keywords = [k.strip().lower().replace(" ", "") for k in str(rule["關鍵字"]).split(",")]
                    if any(k in text for k in keywords if k):
                        return cat_name
                return "待分類"

            df['類別'] = df[col_desc].apply(classify_v3)

            # --- 4. 展示分析介面 ---
            st.divider()
            
            # 手動修正與日期顯示
            unclassified = df[df['類別'] == "待分類"]
            if not unclassified.empty:
                with st.expander(f"🛠️ 有 {len(unclassified)} 筆項目需要手動分類 (已顯示日期)"):
                    for idx, row in unclassified.iterrows():
                        date_str = str(row[col_date]).split(" ")[0] if col_date else "N/A"
                        chosen = st.selectbox(
                            f"【{date_str}】 {row[col_desc]} (${row[col_amt]})",
                            options=["待分類"] + [r["分類名稱"] for r in st.session_state.category_map] + ["其他"],
                            key=f"final_fix_{idx}"
                        )
                        if chosen != "待分類":
                            df.at[idx, '類別'] = chosen

            # 圓餅圖與明細區
            summary = df.groupby('類別')[col_amt].sum().reset_index()
            plot_df = summary[summary[col_amt] > 0]
            
            c1, c2 = st.columns([1, 1])
            with c1:
                st.subheader("📊 消費佔比分析")
                fig = px.pie(plot_df, values=col_amt, names='類別', hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.subheader("🔍 分類消費明細")
                sel_cat = st.selectbox("選擇類別", options=df['類別'].unique())
                view_cols = [c for c in [col_date, col_desc, col_amt] if c is not None]
                st.dataframe(df[df['類別'] == sel_cat][view_cols], hide_index=True)
                st.metric(f"{sel_cat} 總計", f"${df[df['類別'] == sel_cat][col_amt].sum():,.0f}")

    except Exception as e:
        st.error(f"系統錯誤: {e}")
