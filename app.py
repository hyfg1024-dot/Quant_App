import pandas as pd
import streamlit as st

from fast_engine import fetch_realtime_quote
from slow_engine import (
    add_stock_by_query,
    get_latest_fundamental_snapshot,
    get_stock_pool,
    init_db,
    update_fundamental_data,
)

st.set_page_config(page_title="Defensive Quant Dashboard", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    :root {
        --bg-main: #edf3fa;
        --bg-panel: #f6f9ff;
        --text-strong: #15253f;
        --text-normal: #1f334f;
        --text-muted: #536985;
        --line-soft: #c8d5e6;
        --accent: #1d4ed8;
    }
    .stApp {
        background: linear-gradient(180deg, var(--bg-main) 0%, #e8eff8 100%);
        color: var(--text-normal);
    }
    [data-testid="stAppViewContainer"] {
        color: var(--text-normal);
    }
    [data-testid="stSidebar"] {
        background: #1e2432;
        color: #e8eef8;
    }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {
        color: #e8eef8 !important;
    }
    .block-container {
        padding-top: 1.5rem;
        max-width: 1100px;
    }
    h1, h2, h3, h4 {
        color: var(--text-strong) !important;
    }
    p, label, div, span {
        color: var(--text-normal);
    }
    [data-testid="stCaptionContainer"] p {
        color: var(--text-muted) !important;
    }
    [data-testid="stMetricLabel"] div {
        color: var(--text-muted) !important;
    }
    [data-testid="stMetricValue"] div {
        color: var(--text-strong) !important;
    }
    [data-testid="stMarkdownContainer"] p {
        color: var(--text-normal);
    }
    .stButton > button {
        background: #dbeafe;
        color: #0f2a52;
        border: 1px solid #a8c2e8;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: #c7ddfb;
        color: #0b2346;
        border-color: #8fb3e3;
    }
    [data-testid="stSelectbox"] label,
    [data-testid="stSelectbox"] > div {
        color: var(--text-strong) !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: #f7fbff !important;
        border: 1px solid #b8cdea !important;
        color: #0f2a52 !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] span,
    [data-testid="stSelectbox"] div[data-baseweb="select"] input {
        color: #0f2a52 !important;
        -webkit-text-fill-color: #0f2a52 !important;
        opacity: 1 !important;
    }
    [data-testid="stSelectbox"] div[data-baseweb="select"] svg {
        fill: #345b91 !important;
        color: #345b91 !important;
    }
    /* BaseWeb Select dropdown portal overrides: enforce high contrast */
    div[data-baseweb="popover"],
    div[data-baseweb="popover"] * {
        color: #f8fbff !important;
        -webkit-text-fill-color: #f8fbff !important;
    }
    div[data-baseweb="popover"] div[role="listbox"],
    div[data-baseweb="popover"] ul,
    div[data-baseweb="menu"] {
        background: #162235 !important;
        border: 1px solid #304a71 !important;
    }
    div[data-baseweb="popover"] div[role="option"],
    div[data-baseweb="menu"] li,
    div[role="listbox"] div[role="option"] {
        color: #f8fbff !important;
        background: #162235 !important;
        -webkit-text-fill-color: #f8fbff !important;
    }
    div[data-baseweb="popover"] div[role="option"]:hover,
    div[data-baseweb="menu"] li:hover,
    div[role="listbox"] div[role="option"]:hover {
        background: #24406b !important;
        color: #ffffff !important;
    }
    div[data-baseweb="popover"] div[role="option"][aria-selected="true"],
    div[data-baseweb="menu"] li[aria-selected="true"],
    div[role="listbox"] div[role="option"][aria-selected="true"] {
        background: #2c4f83 !important;
        color: #ffffff !important;
    }
    [data-testid="stCheckbox"] label span {
        color: var(--text-normal) !important;
    }
    [data-testid="stAlertContentInfo"] p,
    [data-testid="stAlertContentSuccess"] p,
    [data-testid="stAlertContentWarning"] p {
        color: #12345c !important;
    }
    .warn-box {
        background: #fff1e8;
        border-left: 6px solid #f59e0b;
        border-radius: 8px;
        color: #7c2d12;
        padding: 0.75rem 0.9rem;
        margin-top: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("去幻觉量化防御交易看板")
st.caption("慢引擎: 基本面估值 | 快引擎: 实时执行信号")

init_db()

st.sidebar.header("风控阈值")
dividend_threshold = st.sidebar.number_input(
    "股息率高亮阈值 (%)",
    min_value=0.0,
    max_value=20.0,
    value=5.0,
    step=0.5,
)
pb_threshold = st.sidebar.number_input(
    "PB 高亮阈值",
    min_value=0.0,
    max_value=10.0,
    value=1.5,
    step=0.1,
)
premium_warn_threshold = st.sidebar.number_input(
    "VWAP 溢价警告阈值 (%)",
    min_value=0.0,
    max_value=20.0,
    value=2.0,
    step=0.5,
)

st.sidebar.markdown("---")
st.sidebar.subheader("股票池管理")
new_query = st.sidebar.text_input(
    "新增股票（代码或名称）",
    value="",
    placeholder="例如 600036 或 招商银行",
)

if st.sidebar.button("添加到股票池并抓取数据"):
    try:
        code, name = add_stock_by_query(new_query)
        update_fundamental_data([(code, name)])
        st.sidebar.success(f"已加入: {code} - {name}")
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"添加失败: {exc}")

pool_rows = get_stock_pool()
pool_text = "、".join([f"{code}-{name}" for code, name in pool_rows])
st.sidebar.caption(f"当前股票池: {pool_text}")

if st.button("刷新慢引擎数据"):
    with st.spinner("正在更新 AkShare 低频数据..."):
        update_fundamental_data()
    st.success("慢引擎数据更新完成")

rows = get_latest_fundamental_snapshot()
if not rows:
    st.info("数据库暂无数据，请先点击“刷新慢引擎数据”。")
    st.stop()

snapshot_df = pd.DataFrame(rows)
snapshot_df = snapshot_df[["code", "name", "trade_date", "pe", "pb", "dividend_yield", "created_at"]]
snapshot_df.columns = ["代码", "名称", "日期", "PE", "PB", "股息率", "更新时间"]
snapshot_df = snapshot_df.where(pd.notna(snapshot_df), pd.NA)

st.subheader("股票池（慢引擎快照）")

def _highlight_defensive(row):
    cond = (
        pd.notna(row["股息率"])
        and pd.notna(row["PB"])
        and row["股息率"] > dividend_threshold
        and row["PB"] < pb_threshold
    )
    return ["background-color: #dcecff; color: #0f172a" if cond else "" for _ in row]

styled = snapshot_df.style.apply(_highlight_defensive, axis=1).format(
    {"PE": "{:.2f}", "PB": "{:.2f}", "股息率": "{:.2f}"}, na_rep="N/A"
)
st.dataframe(styled, width="stretch", hide_index=True)

if snapshot_df["股息率"].isna().all():
    st.warning("当前股息率字段源站返回缺失，已按防御模式继续展示，建议盘后再次刷新。")

options = [f"{r['code']} - {r['name']}" for r in rows]
selected = st.selectbox("选择标的查看快引擎", options=options)
selected_code = selected.split(" - ")[0]

st.subheader("实时执行面板（快引擎）")
quote = fetch_realtime_quote(selected_code)

if quote["error"]:
    st.warning(f"实时数据拉取失败: {quote['error']}")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("当前价格", f"{quote['current_price']:.3f}" if quote["current_price"] else "N/A")
    c2.metric("实时 VWAP", f"{quote['vwap']:.3f}" if quote["vwap"] else "N/A")
    c3.metric("偏离幅度", f"{quote['premium_pct']:.2f}%" if quote["premium_pct"] is not None else "N/A")

    if not quote["is_trading_data"]:
        st.info("当前可能处于非交易时段，VWAP 可能退化为参考值。")

    if quote["premium_pct"] is not None and quote["premium_pct"] > premium_warn_threshold:
        st.markdown(
            '<div class="warn-box">当前存在情绪溢价，请注意均值回归风险。</div>',
            unsafe_allow_html=True,
        )

st.subheader("交易 CheckList")
check_items = [
    "宏观逻辑未变",
    "位于支撑位且缩量",
    "估值仍在可接受区间",
    "仓位与回撤约束已确认",
]
checked = [st.checkbox(item, key=f"ck_{idx}") for idx, item in enumerate(check_items)]

if all(checked):
    st.success("符合逻辑，允许执行")
else:
    st.info("请完成全部检查项后再执行交易")
