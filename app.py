import pandas as pd
import streamlit as st

from fast_engine import fetch_realtime_quote
from slow_engine import get_latest_fundamental_snapshot, init_db, update_fundamental_data

st.set_page_config(page_title="Defensive Quant Dashboard", page_icon="📊", layout="wide")

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #f5f9ff 0%, #ecf2fb 100%);
        color: #1e293b;
    }
    .block-container {
        padding-top: 1.5rem;
        max-width: 1100px;
    }
    .panel {
        background: #f0f6ff;
        border: 1px solid #c9d9ee;
        border-radius: 10px;
        padding: 0.8rem 1rem;
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
st.dataframe(styled, use_container_width=True, hide_index=True)

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
