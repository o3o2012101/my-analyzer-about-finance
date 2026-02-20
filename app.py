import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="個人化帳單分析師", layout="wide")
st.title("💳 信用卡自動分類分析系統")

# --- 1. 自動記憶邏輯：使用本地檔案儲存規則 ---
# 在雲端部署時，這會暫存在伺服器磁碟；若要永久保存，建議連結 Streamlit Secrets
DB_FILE = "persistent_rules.csv"

def load_rules():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE).set_index('分類名稱')['關鍵字'].to_dict()
    return {
        "吃飯": "餐廳, 711, 全家, 優食, 麥當勞, 星巴克",
        "交通": "優步, 高鐵, 台鐵, 捷運, 中油, taxi",
        "購物": "蝦皮, coupang, momo, uniqlo",
        "旅遊開銷": "客路, trip.com, 訂房, 飯店",
        "基本固定開銷": "netflix, 電信, icloud, apple.com, google"
    }

def save_rules(rules_dict):
    df_rules = pd.DataFrame(list(rules_dict.items()), columns=['分類名稱', '關鍵字'])
    df_rules.to_csv(DB_FILE, index=False)

# 初始化 Session State
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 2. 左側設定面板：字卡化管理 ---
with st.sidebar:
    st.header("⚙️ 智慧分類設定")
    st.caption("修改後系統會自動記住，下次上傳直接生效。")
    
    # 新增分類功能
    new_cat = st.text_input("➕ 新增分類名稱")
    if st.button("確認新增"):
        if new_cat and new_cat not in st.session_state.category_rules:
            st.session_state.category_rules[new_cat] = ""
            save_rules(st.session_state.category_rules)
            st.rerun()

    st.divider()
    
    # 動態產生字卡
    for cat in list(st.session_state.category_rules.keys()):
        with st.expander(f"📁 {cat}", expanded=False):
            current_kws = st.session_state.category_rules[cat]
            new_kws = st.text_area(f"關鍵字", value=current_kws, key=f"input_{cat}", help="以逗號隔開")
            
            # 若有變更，自動儲存
            if new_kws != current_kws:
                st.session_state.category_rules[cat] = new_kws
                save_rules(st.session_state.category_rules)
            
            if st.button(f"刪除 {cat}", key=f"del_{cat}"):
                del st.session_state.category_rules[cat]
                save_rules(st.session_state.category_rules)
                st.rerun()

# --- 3. 檔案處理與圖表顯示 ---
uploaded_file = st.file_uploader("上傳本月信用卡明細 Excel", type=["xlsx"])

if uploaded_file:
    # (省略重複的偵測標題邏輯，與前版相同...)
    # ... 原有的偵測 header_idx 程式碼 ...
    raw_df = pd.read_excel(uploaded_file, header=None)
    header_idx = 0
    for i, row in raw_df.iterrows():
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
        
        # 自動分類
        def auto_classify(text):
            text = str(text).lower()
            for cat, kws in st.session_state.category_rules.items():
                keywords = [k.strip().lower() for k in str(kws).split(",") if k.strip()]
                if any(k in text for k in keywords):
                    return cat
            return "待分類"

        df['類別'] = df[col_desc].apply(auto_classify)

        # --- 4. 圓餅圖與直接修改功能 ---
        st.divider()
        col_chart, col_table = st.columns([1, 1.5])
        
        with col_chart:
            st.subheader("📊 消費支出佔比")
            summary = df.groupby('類別')[col_amt].sum().reset_index()
            fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
            
            if st.button("📥 匯出本月分類結果 Excel"):
                output = io.BytesIO()
                df.to_excel(output, index=False)
                st.download_button("點擊下載", output.getvalue(), "monthly_report.xlsx")

        with col_table:
            st.subheader("🔍 明細管理 (直接修改類別)")
            # 功能：在表格直接改類別，並詢問是否要把這個店家記下來
            edited_df = st.data_editor(
                df[[col_date, col_desc, col_amt, '類別']],
                column_config={
                    "類別": st.column_config.SelectboxColumn("類別", options=list(st.session_state.category_rules.keys()) + ["待分類"])
                },
                use_container_width=True, hide_index=True
            )
            
            # 檢查是否有手動修改，若有，詢問是否要將該關鍵字加入規則
            # (此處可實作自動學習邏輯：若用戶改了某項，自動把該店名存入關鍵字)
