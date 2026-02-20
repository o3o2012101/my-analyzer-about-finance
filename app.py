import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import random
from datetime import datetime
import gspread  # 用於處理分頁建立

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart 雲端自動化帳本", page_icon="💰", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { padding: 15px; border-radius: 12px; background-color: #F8F9FA; border: 1px solid #EEEEEE; text-align: center; margin-bottom: 10px; }
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

# --- 3. 側邊欄 ---
with st.sidebar:
    st.title("📂 雲端管理")
    target_month = st.text_input("操作月份 (如 202602)", value=datetime.now().strftime("%Y%m"))
    if st.button("🔄 同步雲端分類規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.success("規則已更新！")
        st.rerun()

# --- 4. 核心邏輯：讀取或建立資料 ---
st.title(f"📊 {target_month} 消費狀態分析")

# 嘗試從雲端抓取該月資料
try:
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty and ('working_df' not in st.session_state or st.session_state.get('curr_m') != target_month):
        st.session_state.working_df = df_month
        st.session_state.curr_m = target_month
except Exception:
    # 如果抓不到（分頁不存在），且月份切換了，就清空目前視窗
    if 'working_df' in st.session_state and st.session_state.get('curr_m') != target_month:
        del st.session_state.working_df

# 如果目前沒資料（全新月份），顯示上傳
if 'working_df' not in st.session_state:
    st.info(f"💡 雲端尚未偵測到 {target_month} 的分頁。")
    uploaded_file = st.file_uploader(f"📥 請上傳 {target_month} 的 Richart Excel 初始化", type=["xlsx"])
    
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
        
        # 【關鍵修復】: 使用 conn.update 時，如果 worksheet 不存在，這個 library 有時會報錯。
        # 改用更保險的方式上傳
        conn.update(worksheet=target_month, data=st.session_state.working_df)
        st.success(f"✅ {target_month} 資料已成功建立並同步至雲端！")
        st.rerun()

# --- 5. 數據呈現與自動更新 ---
if 'working_df' in st.session_state:
    w_df = st.session_state.working_df
    
    # 分類篩選
    all_cats = sorted(w_df['類別'].unique())
    selected_cats = st.multiselect("📂 類別篩選：", options=all_cats, default=all_cats)
    
    mask = w_df['類別'].isin(selected_cats)
    
    # 編輯器
    edited_df = st.data_editor(
        w_df[mask],
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, key="main_editor"
    )

    # 偵測改動並顯示儲存鈕
    if st.session_state.main_editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.main_editor["edited_rows"].items():
            actual_idx = w_df[mask].index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        if st.button("💾 確認修改並永久儲存至雲端"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.success("✅ 雲端資料更新成功！")
            st.rerun()

    # 報表統計 (圓餅圖與排行)
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_val = summary['金額'].sum()

    st.divider()
    st.markdown("### 📊 支出佔比分析")
    
    # 進化版圓餅圖 (更明確標註與總額)
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, 
                 color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label', marker=dict(line=dict(color='#FFFFFF', width=2)))
    
    fig.add_annotation(text=f"總支出<br><b>${total_val:,.0f}</b>", showarrow=False, font=dict(size=22))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.markdown("### 🏆 消費排行榜")
    cols = st.columns(4)
    for i, row in summary.iterrows():
        with cols[i % 4]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            st.markdown(f'<div class="rank-card"><div>{icon} {row["類別"]}</div><div style="font-size:1.5rem;color:#4A90E2;font-weight:bold;">{int(row["金額"]):,}元</div></div>', unsafe_allow_html=True)
            
