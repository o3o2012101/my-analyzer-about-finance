import streamlit as st
import pandas as pd
import plotly.express as px
import json
import io

st.set_page_config(page_title="個人化帳單分析師", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# --- 1. 永久儲存與初始化設定 ---
# 初始化分類規則 (Session State)
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = {
        "吃飯": ["餐廳", "711", "全家", "優食", "麥當勞", "星巴克"],
        "交通": ["優步", "高鐵", "台鐵", "捷運", "中油", "taxi"],
        "購物": ["蝦皮", "coupang", "momo", "uniqlo"],
        "旅遊開銷": ["客路", "trip.com", "訂房", "飯店"],
        "基本固定開銷": ["netflix", "電信", "icloud", "apple.com", "google"]
    }

# 初始化歷史紀錄
if 'history_records' not in st.session_state:
    st.session_state.history_records = pd.DataFrame()

# --- 2. 左側設定面板：大分類字卡與規則管理 ---
with st.sidebar:
    st.header("⚙️ 分類規則管理")
    
    # 匯入與匯出規則功能 (永久儲存的概念)
    col_save1, col_save2 = st.columns(2)
    with col_save1:
        rules_json = json.dumps(st.session_state.category_rules, ensure_ascii=False)
        st.download_button("📤 匯出規則檔", rules_json, file_name="my_rules.json", mime="application/json")
    with col_save2:
        uploaded_rules = st.file_uploader("📥 載入規則檔", type=["json"])
        if uploaded_rules:
            st.session_state.category_rules = json.load(uploaded_rules)

    st.divider()
    
    # 字卡式管理介面
    new_cat = st.text_input("➕ 新增分類名稱")
    if st.button("確認新增"):
        if new_cat and new_cat not in st.session_state.category_rules:
            st.session_state.category_rules[new_cat] = []
            st.rerun()

    st.subheader("目前類別與關鍵字")
    for cat, keywords in st.session_state.category_rules.items():
        with st.expander(f"📁 {cat}"):
            # 顯示現有關鍵字
            kw_text = st.text_area(f"關鍵字 (以逗號隔開)", value=", ".join(keywords), key=f"kw_{cat}")
            st.session_state.category_rules[cat] = [k.strip() for k in kw_text.split(",") if k.strip()]
            if st.button(f"刪除 {cat} 分類", key=f"del_{cat}"):
                del st.session_state.category_rules[cat]
                st.rerun()

# --- 3. 檔案讀取與分類核心 ---
uploaded_file = st.file_uploader("上傳本月信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    try:
        # 自動偵測標題 (與前版邏輯相同)
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

            # 自動分類函數
            def auto_classify(text):
                text = str(text).lower()
                for cat, keywords in st.session_state.category_rules.items():
                    if any(k.lower() in text for k in keywords):
                        return cat
                return "待分類"

            df['類別'] = df[col_desc].apply(auto_classify)

            # --- 4. 圓餅圖與直接修改功能 ---
            st.divider()
            
            summary = df.groupby('類別')[col_amt].sum().reset_index()
            c1, c2 = st.columns([1, 1.2])

            with c1:
                st.subheader("📊 消費佔比")
                fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
                
                # 功能 3：保存本月資料到歷史紀錄
                if st.button("💾 將本月數據保存至系統歷史庫"):
                    st.session_state.history_records = pd.concat([st.session_state.history_records, df], ignore_index=True)
                    st.success("已儲存！您可以在下方查看或匯出歷史總表。")

            with c2:
                st.subheader("🔍 明細管理與快速修正")
                st.caption("若發現分類錯誤，可直接在下方表格修改「類別」欄位")
                # 功能 2：在表格中直接修改隸屬類別
                edited_df = st.data_editor(
                    df[[col_date, col_desc, col_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn(
                            "類別",
                            options=list(st.session_state.category_rules.keys()) + ["待分類", "其他"]
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
                df.update(edited_df) # 更新原始資料

            # --- 5. 歷史資料查詢與 Excel 匯出 ---
            st.divider()
            st.subheader("📜 歷史消費總庫")
            if not st.session_state.history_records.empty:
                st.dataframe(st.session_state.history_records, use_container_width=True)
                
                # 功能 3：匯出 Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    st.session_state.history_records.to_excel(writer, index=False, sheet_name='History')
                st.download_button(
                    label="📥 匯出歷史紀錄 Excel",
                    data=output.getvalue(),
                    file_name="expense_history.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.write("目前尚無存檔紀錄。")

    except Exception as e:
        st.error(f"錯誤: {e}")
