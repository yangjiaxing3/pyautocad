"""
app_ui.py
倉位解析精靈 — Streamlit 驗證原型 (Storeasy 企業端設計版)

採用 Storeasy.fm Marketing 既有設計規範：
- 暗黑主題 (Deep Dark: #0b0f1a)
- 玻璃擬物化 (Glassmorphism)
- Plus Jakarta Sans 字體
- 霓虹卡片發光效應 (Neon Glow)
"""
import json
import logging
import streamlit as st
import pandas as pd

from main_pipeline import run_pipeline, results_to_dataframe, results_to_excel_bytes

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# ─────────────────────────────────────────────
# 頁面配置
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="倉位解析精靈 | CAD to Excel",
    page_icon="🧊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# 自定義樣式 (CSS) - 遵循 Storeasy_fm_marketing 規範
# ─────────────────────────────────────────────
st.markdown("""
<style>
    /* 引入企業標準英文字體 */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    /* 1. 深度深色背景 (Deep Dark Theme) & 全局覆寫 */
    .stApp, .main, [data-testid="stAppViewContainer"] {
        background-color: #0b0f1a !important;
        background-image: radial-gradient(ellipse 70% 60% at 50% -20%, rgba(99,102,241,0.12) 0%, transparent 60%);
        font-family: 'Plus Jakarta Sans', 'Noto Sans TC', sans-serif !important;
        color: #f8fafc;
    }
    
    /* 隱藏原生背景色以免破壞底色 */
    [data-testid="stHeader"] {
        background: transparent !important;
    }

    h1, h2, h3, h4, h5, h6, .markdown-text-container {
        font-family: 'Plus Jakarta Sans', 'Noto Sans TC', sans-serif !important;
        letter-spacing: 0.025em; /* tracking-wide */
        color: #ffffff !important;
    }

    /* 2. 玻璃面板效果 (Glassmorphism) - .glass-shell */
    .glass-shell {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(16px) saturate(1.4);
        -webkit-backdrop-filter: blur(16px) saturate(1.4);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 24px;
        position: relative;
        overflow: hidden;
        margin-bottom: 24px;
    }

    /* 光暈點綴 - 絕對定位在卡片內 */
    .glass-shell::before {
        content: '';
        position: absolute;
        top: -50px;
        right: -50px;
        width: 100px;
        height: 100px;
        background: rgba(99, 102, 241, 0.15); /* Indigo glow */
        filter: blur(40px);
        border-radius: 50%;
        pointer-events: none;
    }

    /* 3. 共用卡片行為 (.nav-card hover) */
    .nav-card {
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease, border-color 0.3s ease;
    }
    .nav-card:hover {
        transform: translateY(-4px);
        border-color: rgba(139, 92, 246, 0.3); /* Violet */
        box-shadow: 0 10px 25px -5px rgba(139, 92, 246, 0.1), 0 8px 10px -6px rgba(139, 92, 246, 0.1);
    }

    /* 統計小卡設計 */
    .stat-card {
        background: rgba(255, 255, 255, 0.02);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }
    .stat-value {
        font-size: 2.5rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(to bottom right, #e2e8f0, #94a3b8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .stat-label {
        color: #94a3b8; /* slate-400 */
        font-size: 0.875rem;
        font-weight: 500;
        margin-top: 8px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* 主標題 */
    .main-title {
        color: white;
        font-size: 2.75rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        margin-bottom: 0.5rem;
    }
    .main-title span {
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .sub-title {
        color: #94a3b8;
        font-size: 1.1rem;
        font-weight: 400;
        margin-bottom: 3rem;
    }

    /* 步驟標題 */
    .step-header {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    .step-badge {
        background: rgba(139, 92, 246, 0.15);
        border: 1px solid rgba(139, 92, 246, 0.3);
        color: #c084fc;
        font-weight: 700;
        border-radius: 8px;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-right: 12px;
        font-size: 0.9rem;
    }
    .step-title {
        font-size: 1.25rem;
        font-weight: 600;
        color: #f8fafc;
        margin: 0;
    }

    /* Sidebar 客製化 */
    [data-testid="stSidebar"] {
        background-color: #080b13 !important; /* 更深的底色區隔 */
        border-right: 1px solid rgba(255,255,255,0.05);
    }
    [data-testid="stSidebar"] .stMarkdown h2 {
        color: #e2e8f0;
        font-weight: 600;
        letter-spacing: 0.025em;
    }

    /* 4. 進場動畫 (fadeSlideUp) */
    @keyframes fadeSlideUp {
        0% { opacity: 0; transform: translateY(16px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    .animate-entry {
        animation: fadeSlideUp 0.5s ease-out forwards;
    }
    .delay-1 { animation-delay: 0.05s; opacity: 0; }
    .delay-2 { animation-delay: 0.10s; opacity: 0; }
    .delay-3 { animation-delay: 0.15s; opacity: 0; }

    /* ======================================================== */
    /* 🎯 TDD: Task 1 - 拯救所有標籤文字 (Labels) 與說明字體顏色 */
    /* ======================================================== */
    .stTextInput label, .stNumberInput label, .stSlider label, .stCheckbox label, 
    div[data-testid="stWidgetLabel"] p, label > div > p, .stMarkdown p {
        color: #e2e8f0 !important;
    }

    /* ======================================================== */
    /* 🎯 TDD: Task 2 - 深色化 File Uploader (Dropzone) */
    /* ======================================================== */
    [data-testid="stFileUploader"] {
        background-color: transparent !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background-color: rgba(0, 0, 0, 0.2) !important;
        border: 1px dashed rgba(255,255,255,0.3) !important;
        border-radius: 12px !important;
    }
    [data-testid="stFileUploaderDropzone"] section, 
    [data-testid="stFileUploaderDropzone"] div, 
    [data-testid="stFileUploaderDropzone"] span {
        color: #e2e8f0 !important;
        /* 確保不會繼承父層的強制白色背景 */
        background-color: transparent !important; 
    }
    /* File Uploader 內建按鈕 */
    [data-testid="stFileUploaderDropzone"] button {
        background-color: rgba(255,255,255,0.1) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 6px !important;
    }
    [data-testid="stFileUploaderDropzone"] button:hover {
        background-color: rgba(255,255,255,0.15) !important;
    }

    /* ======================================================== */
    /* 🎯 TDD: Task 3 - 修復輸入框與 Slider 的顏色與白屏現象 */
    /* ======================================================== */
    .stTextInput > div > div, .stNumberInput > div > div {
        background-color: transparent !important;
    }
    .stTextInput > div > div > input, .stNumberInput > div > div > input {
        background-color: #f1f5f9 !important; /* 配合黑字，將底色換成極亮灰 */
        color: #0f172a !important; /* 左側欄的 輸入欄位， font color 改成黑色 */
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    .stTextInput > div > div > input:focus, .stNumberInput > div > div > input:focus {
        border-color: #8b5cf6 !important;
        box-shadow: 0 0 0 1px #8b5cf6 !important;
        background-color: rgba(0, 0, 0, 0.5) !important;
    }
    
    /* 拯救 Slider 不可視的值 */
    .stSlider [data-testid="stThumbValue"] {
        color: #e2e8f0 !important;
        font-weight: bold;
    }

    /* ======================================================== */
    /* 🎯 TDD: Task 4 - 強勢重寫 Primary 按鈕 (阻擋原廠覆蓋) */
    /* ======================================================== */
    /* 使用屬性選擇器強壓 Streamlit 的 inline style */
    div[data-testid="stButton"] button[kind="primary"] {
        background: linear-gradient(to right, #6366f1, #8b5cf6) !important;
        background-color: transparent !important; /* 解除原生底色 */
        border: none !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        padding: 0.75rem 1.5rem !important;
        box-shadow: 0 0 15px rgba(139, 92, 246, 0.4) !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        box-shadow: 0 0 25px rgba(139, 92, 246, 0.6) !important;
        transform: translateY(-2px) !important;
    }
    div[data-testid="stButton"] button[kind="secondary"] {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #f8fafc !important;
        border-radius: 8px !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover {
        background: rgba(255,255,255,0.1) !important;
        border-color: rgba(255,255,255,0.2) !important;
    }

    /* ======================================================== */
    /* 其他補充：DataFrame 與 Status Container 的防禦性暗色設計 */
    /* ======================================================== */
    [data-testid="stDataFrame"] {
        background: rgba(15, 23, 42, 0.4);
        border-radius: 8px;
        padding: 8px;
        border: 1px solid rgba(255,255,255,0.05);
    }
    [data-testid="stStatusWidget"] {
        background: rgba(15, 23, 42, 0.5) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #e2e8f0 !important;
    }
    /* Info 提示框防護 */
    [data-testid="stAlert"] {
        background-color: rgba(255,255,255,0.05) !important;
        color: #e2e8f0 !important;
    }
</style>
""", unsafe_allow_html=True)


def render_step_card(num: int, title: str, delay_class: str = ""):
    """渲染統一的卡片結構起頭"""
    # 由於 Streamlit 不能直接寫一半的 HTML tag，我們用 st.container 來組合，
    # 這裡的 HTML 只負責渲染純視覺標題
    st.markdown(f"""
    <div class="animate-entry {delay_class}">
        <div class="step-header">
            <div class="step-badge">{num}</div>
            <h3 class="step-title">{title}</h3>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_stat_card(value: str, label: str):
    """渲染 Tailwind 風格的狀態卡片"""
    st.markdown(
        f'<div class="stat-card nav-card">'
        f'<div class="stat-value">{value}</div>'
        f'<div class="stat-label">{label}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# Sidebar — 參數設定
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 模型參數")
    st.markdown("<div style='height: 1px; background: rgba(255,255,255,0.1); margin-bottom: 24px;'></div>", unsafe_allow_html=True)

    prefix = st.text_input(
        "倉位前綴 (Prefix)",
        value="HD",
        help="例如: HD, WU, SN",
    )

    start_num = st.number_input(
        "起始編號 (Start Num)",
        min_value=1,
        value=1,
        step=1,
    )

    exclude_input = st.text_input(
        "排除號碼 (Exclude)",
        value="004, 013, 044, 444, 4444",
        help="逗號分隔",
    )
    exclude_list = [x.strip() for x in exclude_input.split(",") if x.strip()]

    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("### 🎛️ 進階演算法微調")

    line_threshold = st.slider(
        "散線縫合閾值 (mm)",
        min_value=1.0,
        max_value=50.0,
        value=10.0,
        step=1.0,
    )

    pillar_max = st.slider(
        "柱體極限判定 (mm)",
        min_value=100.0,
        max_value=2000.0,
        value=800.0,
        step=50.0,
    )

    dim_threshold = st.slider(
        "尺寸關聯半徑 (mm)",
        min_value=100.0,
        max_value=1500.0,
        value=800.0,
        step=50.0,
    )

    st.markdown("<br/><br/>", unsafe_allow_html=True)
    st.markdown(
        '<p style="color:rgba(255,255,255,0.4);font-size:0.75rem;">v2.0.0 — Data Processing Engine<br/>'
        'Storeasy.fm Marketing UI/UX Specs</p>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────
# 頁面主結構
# ─────────────────────────────────────────────
st.markdown("""
<div class="animate-entry">
    <h1 class="main-title">CAD <span>Data Parser</span></h1>
    <p class="sub-title">From unformatted CAD plots to structured structured datasets.</p>
</div>
""", unsafe_allow_html=True)


# --- Step 1 ---
st.markdown('<div class="glass-shell animate-entry delay-1">', unsafe_allow_html=True)
render_step_card(1, "資料輸入層 (Data Ingestion)")

uploaded_file = st.file_uploader(
    "上傳 AutoCAD 提撥實體層 (JSON payload)",
    type=["json"],
    help="必須是由 extract_cad_safe.py 拋出的格式化實體 JSON",
)

use_local = st.checkbox("載入本機端測試資料 (`cad_dump.json`)", value=False)

cad_data = None
if uploaded_file is not None:
    try:
        cad_data = json.load(uploaded_file)
        st.success(f"資料流掛載成功！實體數量：{len(cad_data):,}")
    except json.JSONDecodeError:
        st.error("JSON 架構無效。")
elif use_local:
    try:
        with open("cad_dump.json", encoding="utf-8") as f:
            cad_data = json.load(f)
        st.success(f"本地資料流掛載成功！實體數量：{len(cad_data):,}")
    except FileNotFoundError:
        st.warning("⚠️ 查無本地快取資料。請上傳檔案或透過 CLI 生成。")

if cad_data:
    has_route = any(ent.get("type") == "AcDbPolyline" and "ROUTE" in str(ent.get("layer", "")).upper() for ent in cad_data)
    if has_route:
        st.info("💡 偵測到走道引導線 (ROUTE)，已準備就緒啟動「空間拓樸循序編排」演算法！")

st.markdown('</div>', unsafe_allow_html=True)


# --- Step 2 ---
st.markdown('<div class="glass-shell animate-entry delay-2">', unsafe_allow_html=True)
render_step_card(2, "運算範圍校準 (Scope Calibration)")

col1, col2, col3 = st.columns(3)
with col1:
    render_stat_card(prefix or "—", "Prefix")
with col2:
    render_stat_card(str(start_num), "Sequence Start")
with col3:
    render_stat_card(str(len(exclude_list)), "Exclusion Rules")

st.markdown('</div>', unsafe_allow_html=True)


# --- Step 3 ---
st.markdown('<div class="glass-shell animate-entry delay-3">', unsafe_allow_html=True)
render_step_card(3, "執行管線 (Execute Pipeline)")

can_run = cad_data is not None

if not can_run:
    st.info("💡 等待資料流注入以解鎖運算管線。")
    run_button = False
else:
    run_button = st.button("啟動引擎 (Initialize Parsing)", type="primary", use_container_width=True)

if run_button and cad_data:
    # 建立一個暗色系的進度容器
    with st.status("🔮 正在編譯幾何運算圖...", expanded=True) as status:
        st.write("1. 濾除黑名單實體層...")
        # (故意加一點點延遲模擬編譯感，雖然實際上很快)
        st.write("2. 執行散線縫合演算法 (Line Stitching)...")
        results = run_pipeline(
            cad_data=cad_data,
            prefix=prefix,
            start_num=start_num,
            exclude_list=exclude_list,
            line_stitch_threshold=line_threshold,
            max_pillar_size=pillar_max,
            dim_distance_threshold=dim_threshold,
        )
        st.write("3. 文字特徵與幾何 Bounding Box 空間映射關聯...")
        st.write("4. 產出結構化 DataFrame...")
        
        # 存入 session state
        st.session_state["results"] = results
        status.update(label=f"✅ 成功，運算產生 {len(results)} 組空間單位", state="complete", expanded=False)

st.markdown('</div>', unsafe_allow_html=True)


# --- Step 4 ---
if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]

    st.markdown('<div class="glass-shell animate-entry delay-3" style="animation-delay: 0.25s">', unsafe_allow_html=True)
    render_step_card(4, "關聯數據庫匯出 (Data Export)")

    df = results_to_dataframe(results)
    c1, c2, c3, c4 = st.columns(4)
    with c1: render_stat_card(str(len(df)), "總單元數")
    with c2: render_stat_card(str(len(df[df["屬性"] == "單"]) if "屬性" in df.columns else 0), "單層倉")
    with c3: render_stat_card(str(len(df[df["屬性"] == "雙"]) if "屬性" in df.columns else 0), "雙層倉")
    with c4: render_stat_card(str(len(df[df["屬性"] == "半"]) if "屬性" in df.columns else 0), "半層倉")

    st.markdown("<br/>", unsafe_allow_html=True)

    st.dataframe(
        df,
        use_container_width=True,
        height=350,
        column_config={
            "倉位號碼": st.column_config.TextColumn("實體識別 (ID)", width="medium"),
            "屬性": st.column_config.TextColumn("倉型 (Type)", width="small"),
            "W": st.column_config.NumberColumn("寬 mm"),
            "D": st.column_config.NumberColumn("深 mm"),
            "H": st.column_config.NumberColumn("高 mm"),
        },
    )

    st.markdown("<br/>", unsafe_allow_html=True)
    excel_bytes = results_to_excel_bytes(results)
    filename = f"Parsed_Entities_{prefix or 'CAD'}.xlsx"

    st.download_button(
        label="下載結構化報表 (Download Excel)",
        data=excel_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

    st.markdown('</div>', unsafe_allow_html=True)
