import streamlit as st
import pandas as pd
import plotly.express as px
import io
import json

# 頁面設定
st.set_page_config(page_title="Richart AI 帳單專家", page_icon="💳", layout="wide")

# 套用自定義 CSS 美化
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; transition: 0.3s; }
    .stButton>button:hover { border: 2px solid #ff4b4b; color: #ff4b4b; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #ff4b4b; }
    </style>
    """, unsafe_allow_html=True)

st.title("💳 Richart AI 信用卡自動化分析系統")
st.caption("輕鬆匯入、自動分類、掌握您的每一分開銷")

# --- 1. 分類規則管理 (Session State) ---
if 'category_rules' not in st.session_state:
    st.session_state.category_rules = {
        "吃飯": ["餐廳", "711", "全家", "優食", "麥當勞", "星巴克", "雅室", "牛排"],
        "交通": ["優步", "uber", "車隊", "高鐵", "台鐵", "捷運", "中油", "taxi"],
        "購物": ["蝦皮", "coupang", "momo", "uniqlo", "連支"],
        "旅遊開銷": ["客路", "trip.com", "訂房", "飯店"],
        "基本固定開銷": ["netflix", "電信", "icloud", "apple.com", "google", "服務費"]
    }

# --- 2. 左側設定面板：美化字卡與檔案管理 ---
with st.sidebar:
    st.header("⚙️ 系統設定中心")
    
    # --- 規則存檔工具列 ---
    with st.container(border=True):
        st.subheader("💾 規則存檔")
        col_save1, col_save2 = st.columns(2)
        with col_save1:
            rules_json = json.dumps(st.session_state.category_rules, ensure_ascii=False)
            st.download_button("📤 匯出備份", rules_json, file_name="my_rules.json", mime="application/json", use_container_width=True)
        with col_save2:
            st.button("📥 載入備份", on_click=lambda: st.toast("請將 JSON 檔案拖入下方"), use_container_width=True)
        
        uploaded_rules = st.file_uploader("點擊上傳備份檔", type=["json"], label_visibility="collapsed")
        if uploaded_rules:
            st.session_state.category_rules = json.load(uploaded_rules)
            st.success("規則載入成功！")

    st.divider()
    
    # --- 字卡管理 ---
    st.subheader("📁 消費類別字卡")
    new_cat = st.text_input("輸入新類別名稱", placeholder="例如：醫美、寵物...")
    if st.button("✨ 點擊新增分類", type="primary"):
        if new_cat and new_cat not in st.session_state.category_rules:
            st.session_state.category_rules[new_cat] = []
            st.rerun()

    for cat in list(st.session_state.category_rules.keys()):
        with st.expander(f"📌 {cat}", expanded=False):
            kw_list = st.session_state.category_rules[cat]
            new_kws = st.text_area(f"關鍵字 (以英文逗號分開)", value=", ".join(kw_list), key=f"kw_{cat}")
            st.session_state.category_rules[cat] = [k.strip() for k in new_kws.split(",") if k.strip()]
            
            if st.button(f"🗑️ 刪除該字卡", key=f"del_{cat}"):
                del st.session_state.category_rules[cat]
                st.rerun()

# --- 3. 檔案上傳與核心邏輯 ---
with st.container(border=True):
    uploaded_file = st.file_uploader("📤 請在此上傳您的信用卡明細 Excel (Richart 格式)", type=["xlsx"])

if uploaded_file:
    try:
        # 標題偵測邏輯
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

            # 分類
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
                fig = px.pie(summary[summary[col_amt]>0], values=col_amt, names='類別', hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)

            with col_detail:
                st.subheader("🔍 明細管理與快速篩選")
                target_cat = st.selectbox("🎯 快速篩選類別：", options=["全部項目"] + list(df['類別'].unique()))
                
                filtered_df = df if target_cat == "全部項目" else df[df['類別'] == target_cat]
                cat_total = filtered_df[col_amt].sum()
                
                # 美化總計顯示
                st.metric(label=f"💰 【{target_cat}】小計", value=f"${cat_total:,.0f}")
                
                # 互動式表格
                edited_df = st.data_editor(
                    filtered_df[[col_date, col_desc, col_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn("分類", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
                        "消費金額": st.column_config.NumberColumn("金額", format="$%d")
                    },
                    use_container_width=True, hide_index=True
                )

            # --- 5. 消費排名與結算 (新功能區) ---
            st.divider()
            st.subheader("🏆 本月消費實力榜")
            
            rank_df = df.groupby('類別')[col_amt].sum().sort_values(ascending=False).reset_index()
            total_sum = rank_df[col_amt].sum()
            
            # 排名卡片
            rank_cols = st.columns(len(rank_df) if len(rank_df) < 5 else 5)
            for i, row in rank_df.iterrows():
                with rank_cols[i % 5]:
                    st.metric(label=f"Rank {i+1}: {row['類別']}", value=f"${row[col_amt]:,.0f}", 
                              delta=f"佔 { (row[col_amt]/total_sum*100):.1f}%", delta_color="normal")
            
            st.divider()
            
            col_sum1, col_sum2 = st.columns([2, 1])
            with col_sum1:
                # 橫向排名圖
                fig_rank = px.bar(rank_df, x=col_amt, y='類別', orientation='h', 
                                  color='類別', color_discrete_sequence=px.colors.qualitative.Set3)
                fig_rank.update_layout(showlegend=False, height=300)
                st.plotly_chart(fig_rank, use_container_width=True)
            
            with col_sum2:
                st.markdown(f"### 🏁 結算報告")
                st.success(f"本月總支出： **${total_sum:,.0f}**")
                
                # 美化的匯出按鈕
                output = io.BytesIO()
                df.to_excel(output, index=False)
                st.download_button("📥 匯出 Excel 完整報表", output.getvalue(), "Monthly_Report.xlsx", type="primary")

    except Exception as e:
        st.error(f"系統偵測到異常: {e}")
        
