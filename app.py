import streamlit as st
import pandas as pd
import plotly.express as px
import io
import random
from datetime import datetime

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart AI 理財資料庫", page_icon="⚪", layout="wide")

# 自定義 CSS (質感風)
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { padding: 15px; border-radius: 12px; background-color: #F8F9FA; border: 1px solid #EEEEEE; text-align: center; margin-bottom: 10px; }
    .save-box { padding: 20px; border: 1px solid #4A90E2; border-radius: 10px; background-color: #F0F7FF; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端規則同步 ---
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1CoQxrsfhWDumhsbq_uQbUJVpzM9iDbBwhu16oUoRO_o/export?format=csv&gid=0"

def load_rules():
    url = f"{SHEET_CSV_URL}&cache_buster={random.randint(1, 99999)}"
    try:
        rules_df = pd.read_csv(url)
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except: return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 3. 側邊欄：月份資料庫管理 ---
with st.sidebar:
    st.markdown("### 🗄️ 月份資料庫")
    # 讓使用者輸入或選擇月份
    target_month = st.text_input("📁 目前編輯月份", value=datetime.now().strftime("%Y%m"))
    
    if st.button("🔄 同步雲端規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.rerun()
    
    st.divider()
    if st.button("🗑️ 清空目前資料重新上傳"):
        if 'working_df' in st.session_state:
            del st.session_state.working_df
            st.rerun()

# --- 4. 主頁面 ---
st.title(f"📊 {target_month} 消費狀態分析")

# 檢查是否已有該月份資料
if 'working_df' not in st.session_state:
    uploaded_file = st.file_uploader("📥 上傳 Richart Excel 以開啟新月份帳單", type=["xlsx"], label_visibility="collapsed")
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
            c_desc = next((c for c in df.columns if "明細" in c), "消費明細")
            c_amt = next((c for c in df.columns if "金額" in c), "金額")
            c_date = next((c for c in df.columns if "日期" in c), "日期")
            df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
            df = df.dropna(subset=[c_desc])
            
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            
            df['類別'] = df[c_desc].apply(classify)
            st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(
                columns={c_date: '日期', c_desc: '消費明細', c_amt: '金額'}
            ).reset_index(drop=True)
            st.rerun()
        except Exception as e:
            st.error(f"解析失敗：{e}")
else:
    # 數據已存在，顯示編輯與儲存區
    st.markdown(f"""<div class="save-box">✅ 目前正在編輯 <b>{target_month}</b> 的數據。
    您的修改會暫存在此網頁，編輯完請務必點擊下方「匯出存檔」以備份。</div>""", unsafe_allow_html=True)

    # A. 篩選與編輯
    all_cats = sorted(st.session_state.working_df['類別'].unique())
    selected_cats = st.multiselect("📂 類別篩選：", options=all_cats, default=all_cats)
    
    mask = st.session_state.working_df['類別'].isin(selected_cats)
    display_df = st.session_state.working_df[mask]

    edited_df = st.data_editor(
        display_df,
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, height=350, key="main_editor"
    )

    # 即時儲存編輯內容
    if st.session_state.main_editor.get("edited_rows"):
        for row_idx, changes in st.session_state.main_editor["edited_rows"].items():
            actual_idx = display_df.index[int(row_idx)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        st.rerun()

    # B. 統計與排行
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_sum = summary['金額'].sum()

    st.divider()
    st.markdown("### 🏆 消費排行榜")
    cols = st.columns(4)
    for i, row in summary.iterrows():
        with cols[i % 4]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            st.markdown(f'<div class="rank-card"><div>{icon} {row["類別"]}</div><div style="font-size:1.5rem; color:#4A90E2; font-weight:bold;">{int(row["金額"]):,}元</div></div>', unsafe_allow_html=True)

    # C. 進化環形圖
    st.divider()
    st.markdown("### 📊 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.add_annotation(text=f"{target_month}<br>總支出<br><b>${total_sum:,.0f}</b>", showarrow=False, font=dict(size=18))
    st.plotly_chart(fig, use_container_width=True)
    
    # D. 匯出功能（存檔為特定月份）
    filename = f"Richart_{target_month}_Report.csv"
    csv_data = st.session_state.working_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(f"💾 點我存檔並匯出 {target_month} 月數據", csv_data, filename, "text/csv")
