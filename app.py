import streamlit as st
import pandas as pd
import plotly.express as px
import io

# 1. 頁面基礎設定
st.set_page_config(page_title="極簡帳務分析", page_icon="⚪", layout="wide")

# 自定義 CSS：極簡主義風格
st.markdown("""
    <style>
    /* 移除背景顏色，回歸純淨白 */
    .stApp { background-color: #FFFFFF; }
    
    /* 側邊欄：極簡灰線條 */
    div[data-testid="stSidebar"] { 
        background-color: #FAFAFA; 
        border-right: 1px solid #EEEEEE; 
    }
    
    /* 按鈕：細膩線條感 */
    .stButton>button { 
        width: 100%; 
        border-radius: 4px; 
        border: 1px solid #E0E0E0;
        background-color: transparent;
        color: #444444;
        transition: 0.2s;
    }
    .stButton>button:hover { 
        border: 1px solid #AF8F6F;
        color: #AF8F6F;
    }
    
    /* 數據卡片：無陰影、細邊框 */
    div[data-testid="stMetric"] {
        background-color: transparent;
        border-bottom: 2px solid #F5F5F5;
        border-radius: 0px;
        padding: 10px 0px;
    }
    
    /* 字體控制 */
    h1, h2, h3 { font-weight: 300 !important; color: #333333; }
    
    /* 隱藏裝飾元素 */
    div[data-testid="stExpander"] { border: none !important; box-shadow: none !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連結設定 ---
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"
PREVIEW_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRXIjjDF83p13Bln5VMi6olbKMW4VBJri9Dy9jZKjeZqVLx_Ls5Z6DFMPy7EId8bvCjWOQUzUg6LYvX/pubhtml?widget=true&headers=false"

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

# --- 4. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定")
    st.markdown(f"[📝 編輯雲端規則]({EDIT_URL})")
    
    if st.button("🔄 同步規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.rerun()

    st.divider()
    st.components.v1.iframe(PREVIEW_URL, height=450, scrolling=True)

# --- 5. 主頁面 ---
st.title("帳務分析報表")
uploaded_file = st.file_uploader("", type=["xlsx"])

if uploaded_file:
    try:
        # 資料處理 (Richart 格式自動偵測)
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

            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            df['類別'] = df[c_desc].apply(classify)

            # --- 核心數據摘要 ---
            total_sum = df[c_amt].sum()
            summary_df = df.groupby('類別')[c_amt].sum().sort_values(ascending=False).reset_index()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("總支出", f"${total_sum:,.0f}")
            c2.metric("最大開銷", summary_df.iloc[0]['類別'] if not summary_df.empty else "-")
            c3.metric("紀錄比數", f"{len(df)} 筆")

            # --- 功能區塊 ---
            st.markdown("<br>", unsafe_allow_html=True)
            t1, t2, t3 = st.tabs(["數據分析", "明細管理", "排名看板"])

            with t1:
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    fig_pie = px.pie(summary_df, values=c_amt, names='類別', hole=0.7,
                                     color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_pie.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_b:
                    if c_date:
                        trend = df.groupby(c_date)[c_amt].sum().reset_index()
                        fig_line = px.line(trend, x=c_date, y=c_amt, color_discrete_sequence=['#333333'])
                        fig_line.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                        st.plotly_chart(fig_line, use_container_width=True)

            with t2:
                # 明細修正
                st.data_editor(
                    df[[c_date, c_desc, c_amt, '類別']],
                    column_config={
                        "類別": st.column_config.SelectboxColumn("分類", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
                        c_amt: st.column_config.NumberColumn("金額", format="$%d")
                    },
                    use_container_width=True, hide_index=True
                )
                
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📤 匯出 CSV", csv, "report.csv", "text/csv")

            with t3:
                # 簡單的橫向條形圖
                fig_rank = px.bar(summary_df, x=c_amt, y='類別', orientation='h', 
                                  color_discrete_sequence=['#555555'])
                fig_rank.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                                      yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_rank, use_container_width=True)

    except Exception as e:
        st.error(f"解析錯誤: {e}")
