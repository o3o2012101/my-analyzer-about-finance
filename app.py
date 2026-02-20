import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 頁面基礎風格設定
st.set_page_config(page_title="奶茶色系理財管家", page_icon="☕", layout="wide")

# 自定義 CSS：注入奶茶色與大地色靈魂
st.markdown("""
    <style>
    /* 全域背景 */
    .stApp { background-color: #F5F5F2; }
    
    /* 側邊欄美化 */
    div[data-testid="stSidebar"] { 
        background-color: #EAE3D2; 
        border-right: 1px solid #D2B48C; 
    }
    
    /* 按鈕美化：奶茶棕色 */
    .stButton>button { 
        width: 100%; 
        border-radius: 20px; 
        background-color: #AF8F6F; 
        color: white;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover { 
        background-color: #5C4033; 
        color: #F5F5F2;
    }
    
    /* 數據卡片 (Metrics) 美化：燕麥色 */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        padding: 20px;
        border-radius: 20px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.02);
        border: 1px solid #EAE3D2;
    }
    
    /* 文字顏色 */
    h1, h2, h3, p { color: #5C4033 !important; }
    
    /* Tab 標籤美化 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #EAE3D2;
        border-radius: 10px 10px 0px 0px;
        padding: 10px 20px;
        color: #AF8F6F;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #AF8F6F !important; 
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連結設定 (保持原有功能) ---
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"
PREVIEW_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&headers=false"

# 大地色系調色盤
EARTH_COLORS = ['#AF8F6F', '#D2B48C', '#EAE3D2', '#C19A6B', '#8E735B', '#5C4033']

# --- 3. 核心功能：讀取規則 ---
@st.cache_data(ttl=5)
def load_rules():
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
    except:
        return {"預設": []}

st.session_state.category_rules = load_rules()

# --- 4. 側邊欄設計 ---
with st.sidebar:
    st.markdown("<h2 style='text-align: center;'>☕ 規則設定區</h2>", unsafe_allow_html=True)
    
    with st.container():
        st.markdown(f"""
            <a href="{EDIT_URL}" target="_blank">
                <div style="background-color: #AF8F6F; color: white; text-align: center; padding: 15px; border-radius: 15px; font-weight: bold; cursor: pointer; margin-bottom: 10px;">
                    📝 開啟雲端表單編輯
                </div>
            </a>
        """, unsafe_allow_html=True)
        
        if st.button("🔄 同步規則"):
            st.cache_data.clear()
            st.session_state.category_rules = load_rules()
            st.rerun()

    st.divider()
    st.markdown("🔍 **目前規則快照**")
    st.components.v1.iframe(PREVIEW_URL, height=400, scrolling=True)

# --- 5. 主頁面內容 ---
st.markdown("<h1 style='text-align: center;'>🧸 奶茶色個人財富帳簿</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>溫柔地記錄每一筆生活痕跡</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("", type=["xlsx"])

if uploaded_file:
    try:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_idx = 0
        for i, row in df_raw.iterrows():
            if "消費明細" in "".join(str(v) for v in row.values):
                header_idx = i
                break
        
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        
        c_desc = next((c for c in df.columns if "明細" in c), None)
        c_amt = next((c for c in df.columns if "金額" in c), None)
        c_date = next((c for c in df.columns if "日期" in c), None)

        if c_desc and c_amt:
            df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[c_desc])

            # 分類邏輯
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待處理 ☁️"
            df['類別'] = df[c_desc].apply(classify)

            # --- 頂部數據卡片 ---
            total_sum = df[c_amt].sum()
            summary_df = df.groupby('類別')[c_amt].sum().sort_values(ascending=False).reset_index()
            
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("☕ 本月總消費", f"${total_sum:,.0f}")
            with m2:
                top_cat = summary_df.iloc[0]['類別'] if not summary_df.empty else "N/A"
                st.metric("🧺 支出大宗", top_cat)
            with m3:
                st.metric("📝 紀錄筆數", f"{len(df)} 筆")

            st.markdown("<br>", unsafe_allow_html=True)

            # --- 分頁系統 ---
            tab1, tab2, tab3 = st.tabs(["🍯 支出圓餅圖", "🗂️ 明細清單", "📈 支出排行榜"])

            with tab1:
                st.subheader("支出分配比例")
                fig_pie = px.pie(summary_df[summary_df[c_amt]>0], values=c_amt, names='類別', hole=0.6,
                                 color_discrete_sequence=EARTH_COLORS)
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_pie, use_container_width=True)

            with tab2:
                cat_filter = st.selectbox("🎯 快速過濾：", options=["全部項目"] + list(df['類別'].unique()))
                view_df = df if cat_filter == "全部項目" else df[df['類別'] == cat_filter]
                
                st.data_editor(
                    view_df[[c_date, c_desc, c_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn("修正", options=list(st.session_state.category_rules.keys()) + ["待處理 ☁️"]),
                        c_amt: st.column_config.NumberColumn("金額", format="$%d")
                    },
                    use_container_width=True, hide_index=True, height=400
                )
                
                csv_data = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("💾 匯出帳簿資料", csv_data, "My_Daily_Report.csv", "text/csv")

            with tab3:
                st.subheader("支出排行與權重")
                fig_rank = px.bar(summary_df, x=c_amt, y='類別', orientation='h', 
                                  text_auto=',.0f', color=c_amt, 
                                  color_continuous_scale=['#EAE3D2', '#AF8F6F', '#5C4033'])
                fig_rank.update_layout(yaxis={'categoryorder':'total ascending'}, showlegend=False, 
                                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_rank, use_container_width=True)

        else:
            st.error("找不到資料欄位，請檢查 Excel 內容。")

    except Exception as e:
        st.error(f"小助手迷路了：{e}")
