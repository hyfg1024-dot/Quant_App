import pandas as pd
import streamlit as st

from fast_engine import fetch_fast_panel
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
        --text-strong: #15253f;
        --text-normal: #1f334f;
        --text-muted: #536985;
    }
    .stApp {
        background: linear-gradient(180deg, var(--bg-main) 0%, #e8eff8 100%);
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
    h1, h2, h3, h4 { color: var(--text-strong) !important; }
    .stButton > button {
        background: #dbeafe;
        color: #0f2a52;
        border: 1px solid #a8c2e8;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: #c7ddfb;
        color: #0b2346;
    }
    [data-testid="stMetricLabel"] div { color: #5b6f89 !important; }
    [data-testid="stMetricValue"] div { color: #15253f !important; }
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        background: #f7fbff !important;
        border: 1px solid #b8cdea !important;
        color: #0f2a52 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("去幻觉量化防御交易看板")
st.caption("慢引擎与快引擎分离 | PE口径: TTM优先(对齐中信)")

init_db()

st.sidebar.header("慢引擎筛选阈值")
dividend_threshold = st.sidebar.number_input(
    "股息率高亮阈值 (%)", min_value=0.0, max_value=20.0, value=5.0, step=0.5
)
pb_threshold = st.sidebar.number_input(
    "PB 高亮阈值", min_value=0.0, max_value=10.0, value=1.5, step=0.1
)

st.sidebar.markdown("---")
st.sidebar.subheader("股票池管理")
new_query = st.sidebar.text_input(
    "新增股票（代码或名称）", value="", placeholder="例如 600036 或 招商银行"
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
st.sidebar.caption("当前股票池: " + "、".join([f"{c}-{n}" for c, n in pool_rows]))

if st.button("刷新慢引擎数据"):
    with st.spinner("正在更新慢引擎数据..."):
        update_fundamental_data()
    st.success("慢引擎数据更新完成")

rows = get_latest_fundamental_snapshot()
if not rows:
    st.info("数据库暂无数据，请先点击“刷新慢引擎数据”。")
    st.stop()

snapshot_df = pd.DataFrame(rows)
snapshot_df = snapshot_df[["code", "name", "trade_date", "pe", "pb", "dividend_yield", "created_at"]]
snapshot_df.columns = ["代码", "名称", "日期", "PE(TTM)", "PB", "股息率", "更新时间"]
snapshot_df = snapshot_df.where(pd.notna(snapshot_df), pd.NA)

st.subheader("慢引擎主面板")

def _highlight_defensive(row):
    cond = (
        pd.notna(row["股息率"])
        and pd.notna(row["PB"])
        and row["股息率"] > dividend_threshold
        and row["PB"] < pb_threshold
    )
    return ["background-color: #dcecff; color: #0f172a" if cond else "" for _ in row]

styled = snapshot_df.style.apply(_highlight_defensive, axis=1).format(
    {"PE(TTM)": "{:.2f}", "PB": "{:.2f}", "股息率": "{:.2f}"}, na_rep="N/A"
)
st.dataframe(styled, width="stretch", hide_index=True)

st.markdown("#### 点击股票名称打开快引擎子版面")
btn_cols = st.columns(min(3, max(1, len(rows))))
for idx, row in enumerate(rows):
    col = btn_cols[idx % len(btn_cols)]
    if col.button(f"{row['name']} ({row['code']})", key=f"open_fast_{row['code']}", use_container_width=True):
        st.session_state["fast_selected_code"] = row["code"]
        st.session_state["fast_selected_name"] = row["name"]

if "fast_selected_code" not in st.session_state:
    st.session_state["fast_selected_code"] = rows[0]["code"]
    st.session_state["fast_selected_name"] = rows[0]["name"]

selected_code = st.session_state["fast_selected_code"]
selected_name = st.session_state["fast_selected_name"]

st.subheader("快引擎子版面")
header_cols = st.columns([3, 1])
header_cols[0].markdown(f"### {selected_name} ({selected_code})")
if header_cols[1].button("刷新快引擎", use_container_width=True):
    st.rerun()

panel = fetch_fast_panel(selected_code)
quote = panel["quote"]
ind = panel["indicators"]
intraday_df = panel["intraday"]
order_book_10 = panel["order_book_10"]

if panel.get("error") and not quote.get("current_price"):
    st.warning(f"快引擎数据拉取失败: {panel['error']}")
    st.stop()

price_now = quote.get("current_price")
change_pct = quote.get("change_pct")
if price_now is not None:
    st.markdown(f"## {price_now:.2f}  {'+' if (change_pct or 0) >= 0 else ''}{(change_pct or 0):.2f}%")
    st.caption(f"更新时间: {quote.get('quote_time') or 'N/A'}")

k1, k2, k3, k4 = st.columns(4)
k1.metric("MACD 柱", f"{ind.get('macd_hist'):.3f}" if ind.get("macd_hist") is not None else "N/A")
k2.metric("RSI (6)", f"{ind.get('rsi6'):.2f}" if ind.get("rsi6") is not None else "N/A")
k3.metric("MA20 线", f"{ind.get('ma20'):.2f}" if ind.get("ma20") is not None else "N/A")
k4.metric("昨收基准", f"{quote.get('prev_close'):.2f}" if quote.get("prev_close") is not None else "N/A")

left, right = st.columns([2, 1])
with left:
    st.markdown("#### 资金分时")
    if intraday_df.empty:
        st.info("暂无分时资金数据")
    else:
        chart_df = intraday_df.set_index("time")
        st.area_chart(chart_df["volume_lot"], width="stretch")

with right:
    st.markdown("#### 实时盘口（买10/卖10，单位: 手）")
    sell_df = pd.DataFrame(order_book_10.get("sell", []))
    buy_df = pd.DataFrame(order_book_10.get("buy", []))

    if sell_df.empty or buy_df.empty:
        st.info("暂无盘口数据")
    else:
        sell_df = sell_df.sort_values("level", ascending=False).copy()
        buy_df = buy_df.sort_values("level", ascending=True).copy()
        sell_df["档位"] = sell_df["level"].map(lambda x: f"卖{x}")
        buy_df["档位"] = buy_df["level"].map(lambda x: f"买{x}")

        sell_show = sell_df[["档位", "price", "volume_lot"]].rename(
            columns={"price": "价格", "volume_lot": "手数"}
        )
        buy_show = buy_df[["档位", "price", "volume_lot"]].rename(
            columns={"price": "价格", "volume_lot": "手数"}
        )
        st.dataframe(sell_show, width="stretch", hide_index=True)
        st.dataframe(buy_show, width="stretch", hide_index=True)

st.caption(panel.get("depth_note", ""))
