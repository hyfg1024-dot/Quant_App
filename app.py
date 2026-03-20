import json
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
from streamlit.components.v1 import html

from fast_engine import fetch_fast_panel
from slow_engine import (
    add_stock_by_query,
    get_latest_fundamental_snapshot,
    get_stock_group_map,
    init_db,
    remove_stock_from_pool,
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
    [data-testid="stSidebar"] .stButton > button:not([kind="tertiary"]),
    [data-testid="stSidebar"] .stButton > button:not([kind="tertiary"]) * {
        background: #dbeafe !important;
        color: #0f2a52 !important;
        border: 1px solid #a8c2e8 !important;
    }
    [data-testid="stSidebar"] .stButton > button:not([kind="tertiary"]):hover,
    [data-testid="stSidebar"] .stButton > button:not([kind="tertiary"]):hover * {
        background: #c7ddfb !important;
        color: #0b2346 !important;
    }
    h1, h2, h3, h4 { color: var(--text-strong) !important; }
    .stButton > button:not([kind="tertiary"]) {
        background: #dbeafe;
        color: #0f2a52;
        border: 1px solid #a8c2e8;
        font-weight: 600;
    }
    .stButton > button:not([kind="tertiary"]):hover {
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
    [data-testid="stToggle"] label p,
    [data-testid="stSelectbox"] label p {
        color: #1f334f !important;
        font-weight: 700 !important;
    }
    [data-testid="stCheckbox"] label p,
    [data-testid="stCheckbox"] label span {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        opacity: 1 !important;
        font-weight: 700 !important;
    }
    div[data-testid="stToggle"] label,
    div[data-testid="stToggle"] label span,
    div[data-testid="stToggle"] label p,
    div[data-testid="stToggle"] label [data-testid="stMarkdownContainer"],
    div[data-testid="stToggle"] label [data-testid="stMarkdownContainer"] p {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        opacity: 1 !important;
        font-weight: 700 !important;
    }
    .engine-divider {
        margin: 2.4rem 0 2rem 0;
        border-top: 4px solid #b8c9de;
        position: relative;
    }
    .engine-divider span {
        position: relative;
        top: -1.45rem;
        background: #edf3fa;
        padding: 0 0.8rem;
        color: #15253f;
        font-weight: 800;
        font-size: 2.05rem;
        line-height: 1.1;
    }
    .section-title {
        color: #15253f;
        font-size: 2.05rem;
        font-weight: 800;
        line-height: 1.1;
        margin: 0.9rem 0 0.8rem 0;
    }
    .fast-head-title {
        color: #324760;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: 0.2px;
    }
    .fast-price-line {
        display: flex;
        align-items: baseline;
        gap: 0.8rem;
        margin: 0.3rem 0 0.7rem 0;
    }
    .price-num {
        font-size: 2.9rem;
        font-weight: 800;
        line-height: 1;
    }
    .chg-num {
        font-size: 1.7rem;
        font-weight: 700;
        line-height: 1;
    }
    .a-up { color: #d14343; }
    .a-down { color: #1fab63; }
    .fast-card {
        background: #f5f7fb;
        border: 1px solid #d9e2ef;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        min-height: 104px;
    }
    .fast-card .t {
        color: #5f738f;
        font-size: 0.95rem;
        font-weight: 700;
    }
    .fast-card .v {
        color: #202c3c;
        font-size: 2rem;
        font-weight: 800;
        margin-top: 0.15rem;
    }
    .fast-card .d {
        color: #8a98ac;
        font-size: 0.88rem;
        margin-top: 0.1rem;
    }
    .ob-title {
        font-size: 1.95rem;
        color: #23364f;
        font-weight: 800;
    }
    .panel-title {
        font-size: 2.7rem;
        color: #1e3450;
        font-weight: 800;
        line-height: 1.1;
        margin: 0 0 0.5rem 0;
        letter-spacing: 0.2px;
    }
    .fast-panels-gap {
        height: 0.75rem;
    }
    .ob-block { margin-top: 0.3rem; }
    .ob-row {
        display: grid;
        grid-template-columns: 44px 78px 1fr 56px;
        gap: 0.5rem;
        align-items: center;
        margin: 0.18rem 0;
    }
    .ob-lab {
        font-weight: 700;
        font-size: 1.05rem;
        letter-spacing: 0.3px;
    }
    .ob-price {
        font-weight: 700;
        font-size: 1.05rem;
        text-align: right;
        padding-right: 4px;
    }
    .ob-bar-wrap {
        height: 24px;
        background: rgba(207, 221, 236, 0.38);
        border-radius: 4px;
        position: relative;
        overflow: hidden;
    }
    .ob-bar {
        height: 100%;
        border-radius: 4px;
    }
    .ob-bar.sell { background: rgba(59, 180, 107, 0.25); }
    .ob-bar.buy { background: rgba(231, 98, 98, 0.28); }
    .ob-vol {
        text-align: right;
        color: #2f4059;
        font-weight: 700;
        font-size: 1rem;
        letter-spacing: 0.2px;
    }
    .ob-sell { color: #2f9f5d; }
    .ob-buy { color: #d84f4f; }
    .ob-sep {
        border-top: 1px solid #d7e0ec;
        margin: 0.5rem 0;
    }
    .stock-open-wrap div.stButton > button {
        min-height: 58px !important;
        border-radius: 10px !important;
        white-space: pre-line !important;
        line-height: 1.12 !important;
        font-size: 0.97rem !important;
        font-weight: 800 !important;
        padding: 0.14rem 0.22rem !important;
    }
    .stock-open-wrap div[data-testid="stButton"],
    .stock-del-inline-wrap div[data-testid="stButton"] {
        margin-bottom: 0.06rem !important;
    }
    .stock-open-wrap div.stButton > button * {
        white-space: pre-line !important;
    }
    .stock-open-wrap div.stButton > button p {
        margin: 0 !important;
        text-align: center !important;
    }
    .stock-open-wrap div.stButton > button p:last-child {
        font-size: 0.86rem !important;
        letter-spacing: 0.5px !important;
        font-variant-numeric: tabular-nums !important;
    }
    .stock-del-inline-wrap div.stButton > button {
        min-height: 58px !important;
        border-radius: 10px !important;
        border: none !important;
        background: transparent !important;
        background-color: transparent !important;
        background-image: none !important;
        color: #5d708a !important;
        font-size: 1.05rem !important;
        padding: 0 !important;
        box-shadow: none !important;
    }
    .stock-del-inline-wrap div.stButton > button:hover,
    .stock-del-inline-wrap div.stButton > button:focus,
    .stock-del-inline-wrap div.stButton > button:active {
        background: transparent !important;
        background-color: transparent !important;
        background-image: none !important;
        color: #1f334f !important;
        border: none !important;
        box-shadow: none !important;
    }
    .watch-split-divider {
        min-height: 0;
        border-left: 2px solid #c7d3e3;
        margin: 0.2rem auto 0 auto;
        width: 1px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("股票观察面板")
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
    "新增股票（代码或名称）", value="", placeholder="例如 600036 / 00700 / 腾讯控股"
)

add_cols = st.sidebar.columns(2)
add_holding = add_cols[0].button("加入持仓", use_container_width=True)
add_watch = add_cols[1].button("加入观察", use_container_width=True)
if add_holding or add_watch:
    pool_group = "holding" if add_holding else "watch"
    group_text = "持仓" if pool_group == "holding" else "观察"
    try:
        code, name = add_stock_by_query(new_query, pool_group=pool_group)
        update_fundamental_data([(code, name, pool_group)])
        st.sidebar.success(f"已加入{group_text}: {code} - {name}")
        st.rerun()
    except Exception as exc:
        st.sidebar.error(f"添加失败: {exc}")

if st.button("刷新慢引擎数据"):
    with st.spinner("正在更新慢引擎数据..."):
        update_fundamental_data()
    st.success("慢引擎数据更新完成")

rows = get_latest_fundamental_snapshot()
if not rows:
    st.info("数据库暂无数据，请先点击“刷新慢引擎数据”。")
    st.stop()

snapshot_df = pd.DataFrame(rows)
snapshot_df = snapshot_df[
    [
        "code",
        "name",
        "trade_date",
        "pe_dynamic",
        "pe_static",
        "pe_rolling",
        "pb",
        "dividend_yield",
        "boll_index",
        "created_at",
    ]
]
snapshot_df.columns = ["代码", "名称", "日期", "PE(动)", "PE(静)", "PE(滚)", "PB", "股息率", "布林指数", "更新时间"]

def _format_display_time(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    text = str(v).strip()
    if not text:
        return None
    dt = pd.to_datetime(text, errors="coerce")
    if pd.isna(dt):
        dt = pd.to_datetime(text, format="%Y%m%d%H%M%S", errors="coerce")
    if pd.isna(dt):
        return None
    return dt.strftime("%m-%d %H:%M:%S")


def _json_safe(v):
    if isinstance(v, dict):
        return {k: _json_safe(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, pd.DataFrame):
        return _json_safe(v.to_dict(orient="records"))
    if isinstance(v, pd.Series):
        return _json_safe(v.to_dict())
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return _json_safe(v.item())
        except Exception:
            pass
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


def _is_hk_code(code: str) -> bool:
    digits = "".join(ch for ch in str(code).strip() if ch.isdigit())
    return len(digits) == 5


def _is_market_open(code: str) -> bool:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        return False

    t = now.time()
    if _is_hk_code(code):
        # 港股常规交易时段（简化口径）
        return (time(9, 30) <= t <= time(12, 0)) or (time(13, 0) <= t <= time(16, 0))

    # A股常规交易时段
    return (time(9, 30) <= t <= time(11, 30)) or (time(13, 0) <= t <= time(15, 0))


snapshot_df["更新时间"] = snapshot_df["更新时间"].apply(_format_display_time)
snapshot_df = snapshot_df.where(pd.notna(snapshot_df), pd.NA)

st.markdown('<div class="section-title">基本面</div>', unsafe_allow_html=True)

def _highlight_defensive(row):
    cond = (
        pd.notna(row["股息率"])
        and pd.notna(row["PB"])
        and row["股息率"] > dividend_threshold
        and row["PB"] < pb_threshold
    )
    return ["background-color: #dcecff; color: #0f172a" if cond else "" for _ in row]

styled = snapshot_df.style.apply(_highlight_defensive, axis=1).format(
    {"PE(动)": "{:.2f}", "PE(静)": "{:.2f}", "PE(滚)": "{:.2f}", "PB": "{:.2f}", "股息率": "{:.2f}", "布林指数": "{:.2f}"},
    na_rep="N/A",
)
st.dataframe(styled, width="stretch", hide_index=True)

if "fast_selected_code" not in st.session_state:
    st.session_state["fast_selected_code"] = rows[0]["code"]
    st.session_state["fast_selected_name"] = rows[0]["name"]

selected_code_for_ctrl = st.session_state["fast_selected_code"]
market_open_for_ctrl = _is_market_open(selected_code_for_ctrl)

st.markdown('<div class="engine-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="section-title">交易面</div>', unsafe_allow_html=True)
header_cols = st.columns([2.4, 0.8, 0.6, 0.9], vertical_alignment="bottom")
header_cols[0].markdown("#### 观察标的")
auto_refresh_on = header_cols[1].checkbox("自动刷新", value=False, key="fast_auto_refresh_on")
auto_refresh_sec = header_cols[2].selectbox(
    "刷新间隔(秒)",
    options=[3, 5, 10, 15, 30, 60],
    index=2,
    key="fast_auto_refresh_sec",
)
if header_cols[3].button("立即刷新", use_container_width=True, disabled=not market_open_for_ctrl):
    st.rerun()
if auto_refresh_on:
    if market_open_for_ctrl:
        st.caption(f"快引擎已开启自动刷新：每 {auto_refresh_sec} 秒更新一次（局部刷新，不整页闪动）")
    else:
        st.caption("当前闭市，自动刷新已暂停（不抓取新数据）。")
else:
    st.caption("自动刷新已关闭")

group_map = get_stock_group_map()
holding_rows = [r for r in rows if group_map.get(str(r["code"]), "watch") == "holding"]
watch_rows = [r for r in rows if group_map.get(str(r["code"]), "watch") != "holding"]


def _stock_grid_cols(total: int) -> int:
    if total <= 1:
        return 1
    if total <= 4:
        return 2
    if total <= 9:
        return 3
    return 4


def _render_stock_group(stock_rows, group_key_prefix: str) -> None:
    if not stock_rows:
        st.caption("暂无标的")
        return

    grid_cols = _stock_grid_cols(len(stock_rows))
    for start in range(0, len(stock_rows), grid_cols):
        row_cols = st.columns(grid_cols)
        chunk = stock_rows[start : start + grid_cols]
        for idx, row in enumerate(chunk):
            col = row_cols[idx]
            with col:
                open_col, del_col = st.columns([5.2, 1], vertical_alignment="center")
                with open_col:
                    st.markdown('<div class="stock-open-wrap">', unsafe_allow_html=True)
                    if st.button(
                        f"{row['name']}\n{row['code']}",
                        key=f"open_fast_{group_key_prefix}_{row['code']}",
                        use_container_width=True,
                    ):
                        st.session_state["fast_selected_code"] = row["code"]
                        st.session_state["fast_selected_name"] = row["name"]
                    st.markdown("</div>", unsafe_allow_html=True)
                with del_col:
                    st.markdown('<div class="stock-del-inline-wrap">', unsafe_allow_html=True)
                    if st.button(
                        "🗑️",
                        key=f"mini_del_{group_key_prefix}_{row['code']}",
                        use_container_width=True,
                        type="tertiary",
                        help=f"删除 {row['name']}",
                    ):
                        remove_stock_from_pool(row["code"])
                        if st.session_state.get("fast_selected_code") == row["code"]:
                            st.session_state.pop("fast_selected_code", None)
                            st.session_state.pop("fast_selected_name", None)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)


holding_rows_needed = math.ceil(len(holding_rows) / max(_stock_grid_cols(len(holding_rows)), 1)) if holding_rows else 1
watch_rows_needed = math.ceil(len(watch_rows) / max(_stock_grid_cols(len(watch_rows)), 1)) if watch_rows else 1
divider_height = max(110, max(holding_rows_needed, watch_rows_needed) * 94 + 16)

group_cols = st.columns([1, 0.02, 1], vertical_alignment="top")
with group_cols[0]:
    st.markdown("##### 持仓")
    _render_stock_group(holding_rows, "holding")
with group_cols[1]:
    st.markdown(
        f'<div class="watch-split-divider" style="height:{divider_height}px;"></div>',
        unsafe_allow_html=True,
    )
with group_cols[2]:
    st.markdown("##### 观察")
    _render_stock_group(watch_rows, "watch")

def _render_fast_panel(selected_code: str, selected_name: str, panel=None):
    if panel is None:
        panel = fetch_fast_panel(selected_code)
    quote = panel["quote"]
    ind = panel["indicators"]
    intraday_df = panel["intraday"]
    order_book_5 = panel["order_book_5"]

    if panel.get("error") and not quote.get("current_price"):
        st.warning(f"快引擎数据拉取失败: {panel['error']}")
        return

    selected_slow = next((r for r in rows if str(r.get("code")) == str(selected_code)), {})
    export_payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "app": "Defensive Quant Dashboard",
        },
        "stock": {"code": selected_code, "name": selected_name},
        "slow_engine": selected_slow,
        "fast_engine": {
            "quote": quote,
            "indicators": ind,
            "order_book_5": order_book_5,
            "intraday": intraday_df,
            "depth_note": panel.get("depth_note"),
            "error": panel.get("error"),
        },
    }
    export_json = json.dumps(_json_safe(export_payload), ensure_ascii=False, indent=2)
    js_text = json.dumps(export_json, ensure_ascii=False)

    price_now = quote.get("current_price")
    prev_close_for_pct = quote.get("prev_close")
    api_change_pct = quote.get("change_pct")
    calc_change_pct = None
    if (
        price_now is not None
        and prev_close_for_pct is not None
        and prev_close_for_pct > 0
    ):
        calc_change_pct = (price_now - prev_close_for_pct) / prev_close_for_pct * 100

    # 以现价/昨收重算为主，避免接口涨跌幅字段偶发异常导致颜色反向
    change_pct = calc_change_pct if calc_change_pct is not None else api_change_pct
    is_down = change_pct is not None and change_pct < 0
    price_class = "a-down" if is_down else "a-up"

    head_left, head_right = st.columns([3.2, 1], vertical_alignment="center")
    if price_now is not None:
        with head_left:
            st.markdown(
                f"""
                <div class="fast-head-title">{selected_name} ({selected_code})</div>
                <div class="fast-price-line">
                    <span class="price-num {price_class}">{price_now:.2f}</span>
                    <span class="chg-num {price_class}">{(change_pct or 0):+.2f}%</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            q_time = _format_display_time(quote.get("quote_time"))
            st.caption(f"更新时间: {q_time if q_time else 'N/A'}")
    with head_right:
        html(
            f"""
            <div style="margin:1.05rem 0 0 0;">
              <button id="copy-json-btn-{selected_code}"
                style="width:100%;height:44px;padding:0 0.95rem;border-radius:10px;border:1px solid #a8c2e8;background:#dbeafe;color:#0f2a52;font-size:1.05rem;font-weight:700;cursor:pointer;white-space:nowrap;">
                复制JSON
              </button>
              <div id="copy-json-msg-{selected_code}" style="margin-top:0.35rem;color:#2e4b6e;font-size:0.88rem;"></div>
            </div>
            <script>
              const btn = document.getElementById("copy-json-btn-{selected_code}");
              const msg = document.getElementById("copy-json-msg-{selected_code}");
              const text = {js_text};
              btn.onclick = async function () {{
                try {{
                  await navigator.clipboard.writeText(text);
                  msg.textContent = "已复制";
                }} catch (e) {{
                  msg.textContent = "复制失败，请重试";
                }}
              }};
            </script>
            """,
            height=90,
        )

    def _fmt(v, nd=2):
        return "N/A" if v is None else f"{v:.{nd}f}"

    macd_val = ind.get("macd_hist")
    rsi_val = ind.get("rsi6")
    ma20_val = ind.get("ma20")
    ref_val = quote.get("prev_close")

    macd_desc = "趋势偏强" if (macd_val is not None and macd_val > 0) else "趋势偏弱"
    rsi_desc = "超买区间" if (rsi_val is not None and rsi_val >= 70) else ("超卖区间" if (rsi_val is not None and rsi_val <= 30) else "强弱指标")

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(
        f'<div class="fast-card"><div class="t">MACD 柱</div><div class="v">{_fmt(macd_val, 3)}</div><div class="d">{macd_desc}</div></div>',
        unsafe_allow_html=True,
    )
    c2.markdown(
        f'<div class="fast-card"><div class="t">RSI (6)</div><div class="v">{_fmt(rsi_val, 2)}</div><div class="d">{rsi_desc}</div></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        f'<div class="fast-card"><div class="t">MA20 线</div><div class="v">{_fmt(ma20_val, 2)}</div><div class="d">生命线</div></div>',
        unsafe_allow_html=True,
    )
    c4.markdown(
        f'<div class="fast-card"><div class="t">昨收基准</div><div class="v">{_fmt(ref_val, 2)}</div><div class="d">PCT Ref</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="fast-panels-gap"></div>', unsafe_allow_html=True)
    left, right = st.columns([2, 1], vertical_alignment="top")
    with left:
        st.markdown('<div class="panel-title">资金分时</div>', unsafe_allow_html=True)
        if intraday_df.empty:
            st.info("暂无分时资金数据")
        else:
            chart_df = intraday_df.set_index("time")
            area_df = chart_df.reset_index()
            # A股配色: 涨红跌绿, 平盘中性灰
            area_color = "#ef4444" if (change_pct or 0) > 0 else ("#22c55e" if (change_pct or 0) < 0 else "#94a3b8")
            chart = (
                alt.Chart(area_df)
                .mark_area(color=area_color, opacity=0.9)
                .encode(
                    x=alt.X("time:T", title="time"),
                    y=alt.Y("volume_lot:Q", title="vol"),
                )
                .properties(height=330)
                .configure_view(strokeOpacity=0)
                .configure_axis(gridColor="#dbe4f0", labelColor="#4a5f7c", titleColor="#4a5f7c")
            )
            st.altair_chart(chart, use_container_width=True)

    with right:
        st.markdown('<div class="panel-title">实时盘口 (单位:手)</div>', unsafe_allow_html=True)
        sell_df = pd.DataFrame(order_book_5.get("sell", []))
        buy_df = pd.DataFrame(order_book_5.get("buy", []))

        if sell_df.empty or buy_df.empty:
            st.info("暂无盘口数据")
        else:
            sell_df = sell_df.sort_values("level", ascending=False).copy()
            buy_df = buy_df.sort_values("level", ascending=True).copy()
            vol_max = max(
                1.0,
                max(pd.to_numeric(sell_df["volume_lot"], errors="coerce").fillna(0).max(), pd.to_numeric(buy_df["volume_lot"], errors="coerce").fillna(0).max()),
            )

            def _ob_rows(df: pd.DataFrame, side: str) -> str:
                rows_html = ""
                for _, r in df.iterrows():
                    lvl = int(r.get("level", 0))
                    price = r.get("price")
                    vol = r.get("volume_lot")
                    vol_num = float(vol) if vol is not None and pd.notna(vol) else 0.0
                    width = int((vol_num / vol_max) * 100)
                    width = max(width, 1 if vol_num > 0 else 0)
                    lab_class = "ob-sell" if side == "sell" else "ob-buy"
                    side_txt = "卖" if side == "sell" else "买"
                    bar_class = "sell" if side == "sell" else "buy"
                    p_txt = f"{float(price):.2f}" if price is not None and pd.notna(price) else "--"
                    v_txt = f"{int(vol_num)}" if vol_num > 0 else "--"
                    rows_html += (
                        f'<div class="ob-row">'
                        f'<div class="ob-lab {lab_class}">{side_txt}{lvl}</div>'
                        f'<div class="ob-price {lab_class}">{p_txt}</div>'
                        f'<div class="ob-bar-wrap"><div class="ob-bar {bar_class}" style="width:{width}%"></div></div>'
                        f'<div class="ob-vol">{v_txt}</div>'
                        f"</div>"
                    )
                return rows_html

            html_text = (
                '<div class="ob-block">'
                + _ob_rows(sell_df, "sell")
                + '<div class="ob-sep"></div>'
                + _ob_rows(buy_df, "buy")
                + "</div>"
            )
            st.markdown(html_text, unsafe_allow_html=True)

    st.caption(panel.get("depth_note", ""))

def _render_fast_panel_fragment():
    selected_code = st.session_state.get("fast_selected_code", rows[0]["code"])
    selected_name = st.session_state.get("fast_selected_name", rows[0]["name"])
    market_open = _is_market_open(selected_code)
    cache_key = f"fast_panel_cache_{selected_code}"

    panel = None
    if market_open:
        panel = fetch_fast_panel(selected_code)
        st.session_state[cache_key] = panel
    else:
        panel = st.session_state.get(cache_key)
        if panel is None:
            # 闭市时允许抓取一次静态快照用于查看，但不进入自动刷新循环
            panel = fetch_fast_panel(selected_code)
            st.session_state[cache_key] = panel

    _render_fast_panel(selected_code, selected_name, panel=panel)

if auto_refresh_on and market_open_for_ctrl:
    @st.fragment(run_every=f"{int(auto_refresh_sec)}s")
    def _auto_fast_panel_fragment():
        _render_fast_panel_fragment()

    _auto_fast_panel_fragment()
else:
    _render_fast_panel_fragment()
