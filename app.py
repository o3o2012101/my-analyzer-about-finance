import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import random
from datetime import datetime

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart 雲端理財帳本", page_icon="💰", layout="wide")

# 自定義 CSS
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { padding: 15px; border-radius: 12px; background-color: #F8F9FA; border: 1px solid #EEEEEE; text-align: center; margin-bottom: 10px; }
    .stMetric { background-color: #ffffff; border: 1px solid #eee; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

def load_rules():
    try:
        # 讀取 Sheet1 作為分類規則
        rules_df = conn.read(worksheet="Sheet1", ttl="1s")
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except: return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 3. 側邊欄：月份切換 ---
with st.sidebar:
    st.title("📂 雲端管理")
    target_month = st.text_input("操作月份 (YYYYMM)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端分類規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.rerun()

# --- 4. 核心邏輯 ---
st.title(f"📊 {target_month} 消費狀態分析")

# 嘗試讀取雲端分頁
try:
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty and ('working_df' not in st.session_state or st.session_state.get('curr_m') != target_month):
        st.session_state.working_df = df_month
        st.session_state.curr_m = target_month
except:
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df

# 如果沒資料則上傳
if 'working_df' not in st.session_state:
    st.warning(f"雲端尚未有 {target_month} 的資料。")
    uploaded_file = st.file_uploader("📥 上傳 Richart Excel 初始化月份", type=["xlsx"])
    if uploaded_file:
        df_raw = pd.read_excel(uploaded_file, header=None)
        header_idx = next(i for i, row in df_raw.iterrows() if "消費明細" in "".join(str(v) for v in row.values))
        df = pd.read_excel(uploaded_file, header=header_idx)
        df.columns = [str(c).strip() for c in df.columns]
        c_desc = next(c for c in df.columns if "明細" in c)
        c_amt = next(c for c in df.columns if "金額" in c)
        c_date = next(c for c in df.columns if "日期" in c)
        df[c_amt] = pd.to_numeric(df[c_amt], errors='coerce').fillna(0)
        
        def classify(t):
            t = str(t).lower()
            for cat, kws in st.session_state.category_rules.items():
                if any(k in t for k in kws): return cat
            return "待分類"
        df['類別'] = df[c_desc].apply(classify)
        st.session_state.working_df = df[[c_date, c_desc, c_amt, '類別']].rename(columns={c_date:'日期', c_desc:'消費明細', c_amt:'金額'})
        st.session_state.curr_m = target_month
        conn.update(worksheet=target_month, data=st.session_state.working_df)
        st.rerun()

# --- 5. 數據呈現 ---
if 'working_df' in st.session_state:
    working_df = st.session_state.working_df
    
    # 篩選功能
    all_cats = sorted(working_df['類別'].unique())
    selected_cats = st.multiselect("📂 類別篩選 (勾選欲查看的類別)：", options=all_cats, default=all_cats)
    
    # 編輯器
    mask = working_df['類別'].isin(selected_cats)
    edited_df = st.data_editor(
        working_df[mask],
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # 儲存與同步
    if st.session_state.main_editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.main_editor["edited_rows"].items():
            actual_idx = working_df[mask].index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        if st.button("💾 確認修改並儲存至雲端"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.success("✅ 雲端資料庫已更新！")
            st.rerun()

    # 報表區
    summary = working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total = summary['金額'].sum()

    st.divider()
    st.markdown("### 🥧 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#FFFFFF', width=2)))
    fig.add_annotation(text=f"總支出<br><b>${total:,.0f}</b>", showarrow=False, font=dict(size=22))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("### 🏆 消費排行榜")
    cols = st.columns(4)
    for i, row in summary.iterrows():
        with cols[i % 4]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            st.markdown(f'<div class="rank-card"><div>{icon} {row["類別"]}</div><div style="font-size:1.5rem;color:#4A90E2;font-weight:bold;">{int(row["金額"]):,}元</div></div>', unsafe_allow_html=True)
