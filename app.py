import streamlit as st
import pandas as pd
import plotly.express as px
import io
import random

# 1. 頁面基礎設定
st.set_page_config(page_title="極簡帳務分析", page_icon="⚪", layout="wide")

# 自定義 CSS (極簡風)
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    div[data-testid="stSidebar"] { background-color: #FAFAFA; border-right: 1px solid #EEEEEE; }
    .stButton>button { width: 100%; border-radius: 4px; border: 1px solid #E0E0E0; background-color: transparent; color: #444444; }
    div[data-testid="stMetric"] { border-bottom: 2px solid #F5F5F5; padding: 10px 0px; }
    h1, h2, h3 { font-weight: 300 !important; color: #333333; }
    /* 讓表格顯示更清晰 */
    .stDataEditor { border: 1px solid #f0f0f0; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連結與同步邏輯 ---
EDIT_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/edit?gid=0#gid=0"

def load_rules_force():
    sheet_url = f"https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0&cache_buster={random.randint(1, 100000)}"
    try:
        rules_df = pd.read_csv(sheet_url)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        rules_dict = {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                      for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
        return rules_dict
    except:
        return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules_force()

# --- 3. 側邊欄 ---
with st.sidebar:
    st.markdown("### ⚙️ 設定")
    st.markdown(f"[📝 點我開啟雲端表格]({EDIT_URL})")
    if st.button("🔄 強制同步雲端規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules_force()
        st.success("同步成功！")
        st.rerun()
    st.divider()
    with st.expander("👀 目前生效規則"):
        st.write(st.session_state.category_rules)

# --- 4. 主頁面內容 ---
st.title("帳務分析報表")
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

            # 自動分類
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            df['類別'] = df[c_desc].apply(classify)

            # --- 數據摘要卡片 ---
            total_sum = df[c_amt].sum()
            summary_df = df.groupby('類別')[c_amt].sum().sort_values(ascending=False).reset_index()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("總支出", f"${total_sum:,.0f}")
            c2.metric("最大開銷", summary_df.iloc[0]['類別'] if not summary_df.empty else "-")
            c3.metric("紀錄筆數", f"{len(df)} 筆")

            # --- 視覺化圖表區 (左右平分) ---
            st.markdown("<br>", unsafe_allow_html=True)
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown("### 📊 支出分佈")
                fig_pie = px.pie(summary_df, values=c_amt, names='類別', hole=0.7, 
                                 color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_pie.update_layout(margin=dict(t=0, b=0, l=0, r=0), showlegend=True)
                st.plotly_chart(fig_pie, use_container_width=True)

            with col_right:
                st.markdown("### 🏆 消費排行")
                fig_rank = px.bar(summary_df, x=c_amt, y='類別', orientation='h', 
                                  color_discrete_sequence=['#555555'])
                fig_rank.update_layout(yaxis={'categoryorder':'total ascending'}, 
                                      plot_bgcolor='rgba(0,0,0,0)', margin=dict(t=0, b=0))
                st.plotly_chart(fig_rank, use_container_width=True)

            # --- 關鍵區域：直接編輯表格 ---
            st.divider()
            st.markdown("### 🔍 明細管理與類別修正")
            st.caption("您可以直接在「類別」欄位下拉選單修正分類，修正結果可於下方匯出。")
            
            # 這裡就是你要的表格，直接放在主頁面最醒目的位置
            st.data_editor(
                df[[c_date, c_desc, c_amt, '類別']],
                column_config={
                    "類別": st.column_config.SelectboxColumn(
                        "分類修正", 
                        options=list(st.session_state.category_rules.keys()) + ["待分類"],
                        width="medium"
                    ),
                    c_amt: st.column_config.NumberColumn("金額", format="$%d"),
                    c_desc: "消費明細",
                    c_date: "日期"
                },
                use_container_width=True, 
                hide_index=True,
                height=500 # 固定高度方便捲動
            )
            
            # 匯出按鈕
            csv = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📤 匯出修正後的報表 (CSV)", csv, "richart_report.csv", "text/csv")

    except Exception as e:
        st.error(f"解析錯誤: {e}")
