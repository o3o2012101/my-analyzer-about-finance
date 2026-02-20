import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import plotly.express as px
import random
from datetime import datetime

# --- 1. 頁面基礎設定 ---
st.set_page_config(page_title="Richart 永久雲端資料庫", page_icon="🏦", layout="wide")

# 自定義 CSS
st.markdown("""
    <style>
    .stApp { background-color: #FFFFFF; }
    .rank-card { padding: 15px; border-radius: 12px; background-color: #F8F9FA; border: 1px solid #EEEEEE; text-align: center; margin-bottom: 10px; }
    .save-status { padding: 10px; border-radius: 8px; background-color: #D4EDDA; color: #155724; margin-bottom: 20px; font-weight: bold; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 建立 Google Sheets 連線 ---
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 3. 雲端規則讀取 (從 rules 工作表) ---
def load_rules():
    try:
        # 讀取規則表 (假設在第一個分頁或名為 'rules' 的分頁)
        rules_df = conn.read(worksheet="Sheet1", ttl="1s") # Sheet1 是您目前的規則表
        rules_df.columns = [c.strip() for c in rules_df.columns]
        return {str(row['分類名稱']).strip(): [k.strip().lower() for k in str(row['關鍵字']).split(",") if k.strip()] 
                for _, row in rules_df.iterrows() if str(row['分類名稱']).strip() != 'nan'}
    except:
        return {"預設": []}

if 'category_rules' not in st.session_state:
    st.session_state.category_rules = load_rules()

# --- 4. 側邊欄：月份資料庫管理 ---
with st.sidebar:
    st.title("🗄️ 雲端月份管理")
    
    # 輸入想要管理的月份
    target_month = st.text_input("📁 欲操作月份 (如 202601)", value=datetime.now().strftime("%Y%m"))
    
    if st.button("🔄 同步雲端分類規則"):
        st.cache_data.clear()
        st.session_state.category_rules = load_rules()
        st.success("規則已同步！")
        st.rerun()

    st.divider()
    st.info("💡 只要修改表格內容，系統將會即時準備更新資料，您可以點擊「確認儲存至雲端」來完成永久備份。")

# --- 5. 主頁面邏輯 ---
st.title(f"📊 {target_month} 消費狀態分析")

# 嘗試從 Google Sheets 讀取該月份的工作表
month_exists = False
try:
    # 嘗試讀取以月份命名的分頁
    df_month = conn.read(worksheet=target_month, ttl="0s")
    if not df_month.empty:
        if 'working_df' not in st.session_state or st.session_state.get('last_month') != target_month:
            st.session_state.working_df = df_month
            st.session_state.last_month = target_month
        month_exists = True
except:
    month_exists = False

# 如果該月份還沒有資料，則顯示上傳按鈕
if not month_exists and 'working_df' not in st.session_state:
    st.warning(f"⚠️ 偵測到雲端尚未有 {target_month} 的分頁資料。")
    uploaded_file = st.file_uploader("📥 請上傳 Richart Excel 檔案來初始化該月份", type=["xlsx"])
    
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
            
            def classify(t):
                t = str(t).lower()
                for cat, kws in st.session_state.category_rules.items():
                    if any(k in t for k in kws): return cat
                return "待分類"
            df['類別'] = df[c_desc].apply(classify)
            
            # 初始化格式
            new_df = df[[c_date, c_desc, c_amt, '類別']].rename(
                columns={c_date: '日期', c_desc: '消費明細', c_amt: '金額'}
            ).reset_index(drop=True)
            
            st.session_state.working_df = new_df
            st.session_state.last_month = target_month
            
            # 立即寫入雲端建立新分頁
            conn.update(worksheet=target_month, data=new_df)
            st.success(f"✅ 已在雲端成功建立 {target_month} 分頁！")
            st.rerun()
        except Exception as e:
            st.error(f"上傳出錯: {e}")

# --- 6. 數據呈現與自動儲存區 ---
if 'working_df' in st.session_state:
    df = st.session_state.working_df

    # A. 篩選與編輯
    st.markdown("### 🔍 明細管理與篩選")
    all_cats = sorted(df['類別'].unique())
    selected_cats = st.multiselect("📂 篩選類別：", options=all_cats, default=all_cats)
    
    mask = df['類別'].isin(selected_cats)
    
    edited_df = st.data_editor(
        df[mask],
        column_config={
            "類別": st.column_config.SelectboxColumn("分類修正", options=list(st.session_state.category_rules.keys()) + ["待分類"]),
            "金額": st.column_config.NumberColumn("金額", format="$%d")
        },
        use_container_width=True, hide_index=True, height=350, key="editor"
    )

    # 偵測改動並同步回 Session
    if st.session_state.editor.get("edited_rows"):
        for row_idx_str, changes in st.session_state.editor["edited_rows"].items():
            actual_idx = df[mask].index[int(row_idx_str)]
            for field, value in changes.items():
                st.session_state.working_df.at[actual_idx, field] = value
        
        # 顯示儲存按鈕
        if st.button("💾 確認修改並同步至雲端資料庫"):
            conn.update(worksheet=target_month, data=st.session_state.working_df)
            st.balloons()
            st.success("🎉 資料已成功備份至 Google Sheets！")

    # B. 圖表與排行
    summary = st.session_state.working_df.groupby('類別')['金額'].sum().sort_values(ascending=False).reset_index()
    total_sum = summary['金額'].sum()

    st.divider()
    st.markdown("### 🏆 消費排行榜")
    cols = st.columns(4)
    for i, row in summary.iterrows():
        with cols[i % 4]:
            icon = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
            st.markdown(f'<div class="rank-card"><div>{icon} {row["類別"]}</div><div style="font-size:1.5rem; color:#4A90E2; font-weight:bold;">{int(row["金額"]):,}元</div></div>', unsafe_allow_html=True)

    st.divider()
    st.markdown("### 🥧 支出佔比分析")
    fig = px.pie(summary, values='金額', names='類別', hole=0.6, color_discrete_sequence=px.colors.qualitative.Pastel)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    fig.add_annotation(text=f"總支出<br><b>${total_sum:,.0f}</b>", showarrow=False, font=dict(size=20))
    st.plotly_chart(fig, use_container_width=True)
