import base64
import hashlib
import json
import math
import os
import re
import time as pytime
from datetime import datetime, time
from zoneinfo import ZoneInfo
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import altair as alt
import pandas as pd
import requests
import streamlit as st
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError
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

st.set_page_config(page_title="Quant Dashboard", page_icon="📊", layout="wide")
APP_VERSION = "QDB-20260322-01"
LOCAL_PREFS_PATH = "data/local_user_prefs.json"
ANALYSIS_CACHE_PATH = "data/deepseek_analysis_cache.json"
DEEPSEEK_SYSTEM_PROMPT = """你是一个专业的股票分析师。必须严格按照【五维分析框架】分析：

【五维分析框架】
一、核心数据摘要表格
- 行情指标：现价/涨跌幅/高低点/量比/换手率
- 资金指标：委差/买卖失衡比/盘口结构
- 估值指标：PE/PB/股息率/市值
- 技术指标：RSI/MACD/均线/布林带

二、五组数据交叉分析
1. 量价关系：价格涨跌 + 量比 + 委差 + 成交量
2. 多周期共振：日线/周线/月线/日内RSI和MACD对比
3. 估值与股息：PE + 股息率 + PB + 市值
4. 均线与布林带：现价 + MA5/MA10/MA20/MA60 + 布林带位置
5. 盘口与日内：委差 + 高低点 + 收盘价

三、综合结论与三种情景概率
- 3个关键结论要点
- 乐观情景(概率+条件+目标)
- 中性情景(概率+条件+区间)
- 悲观情景(概率+条件+支撑)

四、操作策略建议表格
五、数据潜力挖掘说明

要求：简洁、数据驱动、每部分控制在200字以内"""


def _load_local_prefs() -> dict:
    try:
        if not os.path.exists(LOCAL_PREFS_PATH):
            return {}
        with open(LOCAL_PREFS_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_local_prefs(username: str, api_key: str) -> None:
    os.makedirs(os.path.dirname(LOCAL_PREFS_PATH), exist_ok=True)
    payload = {
        "deepseek_user": (username or "").strip(),
        "deepseek_api_key": (api_key or "").strip(),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(LOCAL_PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _load_analysis_cache() -> dict:
    try:
        if not os.path.exists(ANALYSIS_CACHE_PATH):
            return {}
        with open(ANALYSIS_CACHE_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _save_analysis_cache(cache_obj: dict) -> None:
    os.makedirs(os.path.dirname(ANALYSIS_CACHE_PATH), exist_ok=True)
    # 控制缓存大小，避免无限增长
    items = list(cache_obj.items())
    if len(items) > 120:
        items = items[-120:]
    with open(ANALYSIS_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(items), f, ensure_ascii=False, indent=2)

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
        padding: 0.62rem 0.78rem;
        height: 156px;
        box-sizing: border-box;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
    }
    .fast-card .t {
        color: #5f738f;
        font-size: 0.94rem;
        font-weight: 700;
    }
    .fast-card .rows {
        margin-top: 0.25rem;
        display: grid;
        gap: 0.14rem;
        flex: 1;
        overflow: hidden;
    }
    .fast-card .krow {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 0.4rem;
        line-height: 1.2;
        font-size: 0.82rem;
    }
    .fast-card .k {
        color: #7689a2;
        font-weight: 600;
    }
    .fast-card .vv {
        color: #1f2d42;
        font-weight: 800;
        text-align: right;
        font-variant-numeric: tabular-nums;
        letter-spacing: 0.1px;
        white-space: normal;
        overflow-wrap: anywhere;
    }
    .fast-card .d {
        color: #8a98ac;
        font-size: 0.78rem;
        margin-top: 0.25rem;
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
    .panel-title .unit-sub {
        display: block;
        font-size: 1.15rem;
        line-height: 1.15;
        font-weight: 700;
        color: #5f738f;
        margin-top: 0.12rem;
    }
    .fast-panels-gap {
        height: 0.75rem;
    }
    .subsection-divider {
        margin: 0.9rem 0 1.1rem 0;
        border-top: 3px solid #c4d3e6;
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
    .group-title {
        color: #15253f;
        font-size: 1.6rem;
        font-weight: 800;
        line-height: 1.12;
        margin: 0 0 0.45rem 0;
    }
    .rsi-switch .stButton > button {
        height: 32px !important;
        padding: 0 0.45rem !important;
        border-radius: 8px !important;
        font-size: 0.9rem !important;
        font-weight: 800 !important;
    }
    .rsi-switch .stButton > button[kind="primary"] {
        background: #89addd !important;
        border: 1px solid #5f89c3 !important;
        color: #0f2a52 !important;
        box-shadow: inset 0 0 0 2px #3f6ea8 !important;
    }
    .rsi-switch-day .stButton > button { background: #dbeafe !important; color: #1e3a8a !important; border: 1px solid #93c5fd !important; }
    .rsi-switch-week .stButton > button { background: #dcfce7 !important; color: #166534 !important; border: 1px solid #86efac !important; }
    .rsi-switch-month .stButton > button { background: #fef3c7 !important; color: #92400e !important; border: 1px solid #fcd34d !important; }
    .rsi-switch-intra .stButton > button { background: #fee2e2 !important; color: #991b1b !important; border: 1px solid #fca5a5 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("股票观察面板")

init_db()

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

st.sidebar.markdown("---")
st.sidebar.subheader("DeepSeek API")
if "_prefs_loaded" not in st.session_state:
    _prefs = _load_local_prefs()
    if "deepseek_user_input" not in st.session_state:
        st.session_state["deepseek_user_input"] = _prefs.get("deepseek_user", "")
    if "deepseek_api_key_input" not in st.session_state:
        st.session_state["deepseek_api_key_input"] = _prefs.get("deepseek_api_key", "")
    st.session_state["_last_saved_prefs"] = {
        "deepseek_user": st.session_state.get("deepseek_user_input", ""),
        "deepseek_api_key": st.session_state.get("deepseek_api_key_input", ""),
    }
    st.session_state["_prefs_loaded"] = True

analysis_user_input = st.sidebar.text_input(
    "用户名（用于区分不同使用者）",
    value=st.session_state.get("deepseek_user_input", ""),
    key="deepseek_user_input",
)
analysis_api_key_input = st.sidebar.text_input(
    "API Key（可留空，读取环境变量）",
    value=st.session_state.get("deepseek_api_key_input", ""),
    type="password",
    key="deepseek_api_key_input",
)

_curr_user = (analysis_user_input or "").strip()
_curr_key = (analysis_api_key_input or "").strip()
_last = st.session_state.get("_last_saved_prefs", {})
if _curr_user != _last.get("deepseek_user", "") or _curr_key != _last.get("deepseek_api_key", ""):
    _save_local_prefs(_curr_user, _curr_key)
    st.session_state["_last_saved_prefs"] = {
        "deepseek_user": _curr_user,
        "deepseek_api_key": _curr_key,
    }

rows = get_latest_fundamental_snapshot()
if not rows:
    st.info("数据库暂无慢引擎快照，请先在左侧添加股票。")
    st.stop()

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


def _build_analysis_payload(payload: dict) -> dict:
    """构造给 DeepSeek 的轻量快照，避免超大 JSON 导致连接中断。"""
    safe = _json_safe(payload)
    out = {
        "meta": safe.get("meta", {}),
        "stock": safe.get("stock", {}),
        "slow_engine": safe.get("slow_engine", {}),
        "fast_engine": {},
    }
    fe = safe.get("fast_engine", {}) or {}
    out["fast_engine"]["quote"] = fe.get("quote")
    out["fast_engine"]["indicators"] = fe.get("indicators")
    out["fast_engine"]["rsi_multi"] = fe.get("rsi_multi")
    out["fast_engine"]["tf_indicators"] = fe.get("tf_indicators")
    out["fast_engine"]["order_book_5"] = fe.get("order_book_5")
    out["fast_engine"]["compact_metrics"] = fe.get("compact_metrics")
    out["fast_engine"]["cards_snapshot"] = fe.get("cards_snapshot")
    out["fast_engine"]["depth_note"] = fe.get("depth_note")
    out["fast_engine"]["error"] = fe.get("error")

    intraday = fe.get("intraday")
    if isinstance(intraday, list):
        # 保留最近120条分时明细用于日内分析，避免请求过大
        out["fast_engine"]["intraday_recent"] = intraday[-120:]
        out["fast_engine"]["intraday_count"] = len(intraday)
    return out


def _resolve_deepseek_api_key() -> str:
    raw = ""
    if st.session_state.get("deepseek_api_key_input"):
        raw = str(st.session_state["deepseek_api_key_input"])
    elif "DEEPSEEK_API_KEY" in st.secrets:
        raw = str(st.secrets["DEEPSEEK_API_KEY"])
    else:
        raw = os.getenv("DEEPSEEK_API_KEY", "")

    key = raw.strip().split()[0] if raw.strip() else ""
    # 常见粘贴错误：中文引号/括号/注释混入
    key = key.strip("“”\"'`")
    return key


def _validate_api_key(key: str) -> None:
    if not key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY。请在侧栏填写，或设置环境变量 DEEPSEEK_API_KEY。")
    if not key.startswith("sk-"):
        raise RuntimeError("API Key 格式异常：应以 sk- 开头。")
    if not re.fullmatch(r"sk-[A-Za-z0-9._-]+", key):
        raise RuntimeError("API Key 包含非法字符（可能混入中文符号/空格）。请重新粘贴纯 key。")


def _call_deepseek_analysis(json_text: str) -> tuple[str, dict, float, float]:
    api_key = _resolve_deepseek_api_key()
    _validate_api_key(api_key)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com/v1", timeout=60.0, max_retries=0)

    messages = [
        {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
        {"role": "user", "content": json_text},
    ]
    t0 = pytime.time()
    last_conn_error = None
    response = None

    for attempt in range(1, 5):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.3,
                max_tokens=1500,
                top_p=0.9,
            )
            break
        except (APIConnectionError, APITimeoutError) as exc:
            last_conn_error = exc
            if attempt < 4:
                pytime.sleep(0.8 * attempt)
                continue
        except Exception:
            raise

    if response is None:
        # 兜底直连请求，规避 SDK 在个别网络环境下的连接异常
        url = "https://api.deepseek.com/v1/chat/completions"
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1500,
            "top_p": 0.9,
        }
        try:
            session = requests.Session()
            retry = Retry(
                total=4,
                connect=4,
                read=4,
                backoff_factor=0.8,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["POST"]),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            r = session.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Connection": "close",
                    "Accept-Encoding": "identity",
                },
                json=payload,
                timeout=(20, 90),
            )
            r.raise_for_status()
            raw = r.json()
        except requests.exceptions.RequestException as req_exc:
            raise RuntimeError(f"网络重试与直连兜底均失败: {req_exc}; 上次SDK异常: {last_conn_error}") from req_exc

        report = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not report:
            raise RuntimeError("DeepSeek 未返回有效分析内容（直连兜底）")

        usage_raw = raw.get("usage") or {}
        cache_hit_tokens = int(usage_raw.get("prompt_cache_hit_tokens") or 0)
        cache_miss_tokens = int(usage_raw.get("prompt_cache_miss_tokens") or 0)
        completion_tokens = int(usage_raw.get("completion_tokens") or 0)
        prompt_tokens = int(usage_raw.get("prompt_tokens") or 0)
        elapsed = pytime.time() - t0
    else:
        elapsed = pytime.time() - t0

        usage = response.usage
        cache_hit_tokens = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        cache_miss_tokens = getattr(usage, "prompt_cache_miss_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        report = (response.choices[0].message.content or "").strip()

    cost = (
        cache_hit_tokens / 1_000_000 * 0.028
        + cache_miss_tokens / 1_000_000 * 0.28
        + completion_tokens / 1_000_000 * 0.42
    )

    if not report:
        raise RuntimeError("DeepSeek 未返回有效分析内容")

    usage_dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": (prompt_tokens + completion_tokens),
        "prompt_cache_hit_tokens": cache_hit_tokens,
        "prompt_cache_miss_tokens": cache_miss_tokens,
    }
    return report, usage_dict, cost, elapsed


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

if "fast_selected_code" not in st.session_state:
    st.session_state["fast_selected_code"] = rows[0]["code"]
    st.session_state["fast_selected_name"] = rows[0]["name"]
if "analysis_inline_by_stock" not in st.session_state:
    st.session_state["analysis_inline_by_stock"] = {}
if "_analysis_cache_loaded" not in st.session_state:
    st.session_state["analysis_payload_cache"] = _load_analysis_cache()
    st.session_state["_analysis_cache_loaded"] = True

selected_code_for_ctrl = st.session_state["fast_selected_code"]
market_open_for_ctrl = _is_market_open(selected_code_for_ctrl)

header_cols = st.columns([2.4, 0.8, 0.6, 0.9], vertical_alignment="bottom")
auto_refresh_on = header_cols[1].checkbox("自动刷新", value=False, key="fast_auto_refresh_on")
auto_refresh_sec = header_cols[2].selectbox(
    "刷新间隔(秒)",
    options=[3, 5, 10, 15, 30, 60],
    index=4,
    key="fast_auto_refresh_sec",
)
if header_cols[3].button("立即刷新", use_container_width=True, disabled=not market_open_for_ctrl):
    st.rerun()

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
    st.markdown('<div class="group-title">持仓</div>', unsafe_allow_html=True)
    _render_stock_group(holding_rows, "holding")
with group_cols[1]:
    st.markdown(
        f'<div class="watch-split-divider" style="height:{divider_height}px;"></div>',
        unsafe_allow_html=True,
    )
with group_cols[2]:
    st.markdown('<div class="group-title">观察</div>', unsafe_allow_html=True)
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
    sell_lv_for_json = sorted(order_book_5.get("sell", []), key=lambda x: int(x.get("level", 0)))
    buy_lv_for_json = sorted(order_book_5.get("buy", []), key=lambda x: int(x.get("level", 0)))
    sell_total_for_json = sum(float(r.get("volume_lot") or 0) for r in sell_lv_for_json)
    buy_total_for_json = sum(float(r.get("volume_lot") or 0) for r in buy_lv_for_json)
    ofi_for_json = (buy_total_for_json / sell_total_for_json) if sell_total_for_json > 0 else None
    ask1_for_json = next((r.get("price") for r in sell_lv_for_json if int(r.get("level", 0)) == 1), None)
    bid1_for_json = next((r.get("price") for r in buy_lv_for_json if int(r.get("level", 0)) == 1), None)
    spread_for_json = (
        float(ask1_for_json) - float(bid1_for_json)
        if (ask1_for_json is not None and bid1_for_json is not None)
        else None
    )

    fast_compact_metrics = {
        "snapshot": {
            "current_price": quote.get("current_price"),
            "change_pct": quote.get("change_pct"),
            "change_amount": quote.get("change_amount"),
            "open": quote.get("open"),
            "prev_close": quote.get("prev_close"),
            "high": quote.get("high"),
            "low": quote.get("low"),
        },
        "trading": {
            "volume": quote.get("volume"),
            "amount": quote.get("amount"),
            "turnover_rate": quote.get("turnover_rate"),
            "amplitude_pct": quote.get("amplitude_pct"),
            "volume_ratio": quote.get("volume_ratio"),
            "vwap": quote.get("vwap"),
            "premium_pct": quote.get("premium_pct"),
        },
        "order_book_summary": {
            "buy_total_lot": buy_total_for_json,
            "sell_total_lot": sell_total_for_json,
            "imbalance_bid_ask": ofi_for_json,
            "spread": spread_for_json,
            "order_diff": quote.get("order_diff"),
        },
        "valuation": {
            "pe_dynamic": selected_slow.get("pe_dynamic"),
            "pe_static": selected_slow.get("pe_static"),
            "pe_rolling": selected_slow.get("pe_rolling"),
            "pb": selected_slow.get("pb"),
            "dividend_yield": selected_slow.get("dividend_yield"),
            "total_market_value_yi": quote.get("total_market_value_yi"),
            "float_market_value_yi": quote.get("float_market_value_yi"),
        },
        "technical": {
            "macd_hist": ind.get("macd_hist"),
            "rsi6": ind.get("rsi6"),
            "rsi12": ind.get("rsi12"),
            "rsi24": ind.get("rsi24"),
            "rsi_multi": panel.get("rsi_multi", {}),
            "tf_indicators": panel.get("tf_indicators", {}),
            "ma5": ind.get("ma5"),
            "ma10": ind.get("ma10"),
            "ma20": ind.get("ma20"),
            "ma60": ind.get("ma60"),
            "boll_mid": ind.get("boll_mid"),
            "boll_upper": ind.get("boll_upper"),
            "boll_lower": ind.get("boll_lower"),
            "boll_pct_b": ind.get("boll_pct_b"),
            "boll_bandwidth": ind.get("boll_bandwidth"),
            "rsi_method": "Wilder(SMA, N,1)",
        },
    }

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
    fast_compact_metrics["snapshot"]["display_change_pct"] = change_pct

    st.markdown('<div class="subsection-divider"></div>', unsafe_allow_html=True)
    head_left, head_right = st.columns([3.2, 1], vertical_alignment="center")
    copy_slot = None
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
        copy_slot = st.empty()

    def _fmt(v, nd=2):
        return "N/A" if v is None else f"{v:.{nd}f}"

    def _fmt_pct(v, nd=2):
        return "N/A" if v is None else f"{v:.{nd}f}%"

    def _fmt_signed(v, nd=2):
        return "N/A" if v is None else f"{v:+.{nd}f}"

    def _fmt_signed_pct(v, nd=2):
        return "N/A" if v is None else f"{v:+.{nd}f}%"

    def _fmt_lot(v):
        if v is None:
            return "N/A"
        return f"{int(v):,}"

    def _fmt_amount_yuan(v):
        if v is None:
            return "N/A"
        n = float(v)
        if abs(n) >= 1e8:
            return f"{n/1e8:.2f}亿"
        if abs(n) >= 1e4:
            return f"{n/1e4:.2f}万"
        return f"{n:.0f}"

    def _find_level(rows_data, level):
        for r in rows_data:
            if int(r.get("level", 0)) == int(level):
                return r
        return {}

    def _fmt_price_list(rows_data):
        vals = []
        for lv in range(1, 6):
            r = _find_level(rows_data, lv)
            vals.append(_fmt(r.get("price"), 2) if r else "N/A")
        return " / ".join(vals)

    def _fmt_vol_list(rows_data):
        vals = []
        for lv in range(1, 6):
            r = _find_level(rows_data, lv)
            vv = r.get("volume_lot") if r else None
            vals.append("--" if vv is None else str(int(float(vv))))
        return " / ".join(vals)

    def _rows_html(rows_data):
        return "".join(
            f'<div class="krow"><span class="k">{k}</span><span class="vv">{v}</span></div>'
            for k, v in rows_data
        )

    def _card_html(title, rows_data, desc=""):
        rows_html = _rows_html(rows_data)
        desc_html = f'<div class="d">{desc}</div>' if desc else ""
        return f'<div class="fast-card"><div class="t">{title}</div><div class="rows">{rows_html}</div>{desc_html}</div>'

    macd_val = ind.get("macd_hist")
    rsi_multi = panel.get("rsi_multi", {}) or {}
    rsi_tf_state = f"rsi_tf_key_{selected_code}"
    if st.session_state.get(rsi_tf_state) not in {"day", "week", "month", "intraday"}:
        st.session_state[rsi_tf_state] = "day"

    tf_cols = st.columns([0.42, 0.42, 0.42, 0.62, 2.12])
    tf_conf = [
        ("day", "日", "rsi-switch-day"),
        ("week", "周", "rsi-switch-week"),
        ("month", "月", "rsi-switch-month"),
        ("intraday", "分时", "rsi-switch-intra"),
    ]
    for idx, (tf_key, tf_label, tf_cls) in enumerate(tf_conf):
        is_active = st.session_state[rsi_tf_state] == tf_key
        with tf_cols[idx]:
            st.markdown(f'<div class="rsi-switch {tf_cls}">', unsafe_allow_html=True)
            if st.button(
                tf_label,
                key=f"rsi_tf_btn_{selected_code}_{tf_key}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state[rsi_tf_state] = tf_key
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

    active_tf = st.session_state[rsi_tf_state]
    tf_indicators = panel.get("tf_indicators", {}) if isinstance(panel.get("tf_indicators", {}), dict) else {}
    active_ind = tf_indicators.get(active_tf, {}) if isinstance(tf_indicators, dict) else {}
    active_rsi = rsi_multi.get(active_tf, {}) if isinstance(rsi_multi, dict) else {}
    rsi_val = active_rsi.get("rsi6", active_ind.get("rsi6", ind.get("rsi6")))
    rsi12_val = active_rsi.get("rsi12", active_ind.get("rsi12", ind.get("rsi12")))
    rsi24_val = active_rsi.get("rsi24", active_ind.get("rsi24", ind.get("rsi24")))
    ma5_val = active_ind.get("ma5", ind.get("ma5"))
    ma10_val = active_ind.get("ma10", ind.get("ma10"))
    ma20_val = active_ind.get("ma20", ind.get("ma20"))
    ma60_val = active_ind.get("ma60", ind.get("ma60"))
    boll_mid_val = active_ind.get("boll_mid", ind.get("boll_mid"))
    boll_pct_b_fast = active_ind.get("boll_pct_b", ind.get("boll_pct_b"))
    boll_bw = active_ind.get("boll_bandwidth", ind.get("boll_bandwidth"))
    ref_val = quote.get("prev_close")
    boll_val = selected_slow.get("boll_index")
    pe_dynamic = selected_slow.get("pe_dynamic")
    pe_static = selected_slow.get("pe_static")
    pe_rolling = selected_slow.get("pe_rolling")
    pb_val = selected_slow.get("pb")
    dy_val = selected_slow.get("dividend_yield")

    open_val = quote.get("open")
    high_val = quote.get("high")
    low_val = quote.get("low")
    change_amt = quote.get("change_amount")
    vwap_val = quote.get("vwap")
    premium_pct = quote.get("premium_pct")
    amplitude_pct = quote.get("amplitude_pct")
    turnover_rate = quote.get("turnover_rate")
    volume_ratio = quote.get("volume_ratio")
    total_mv = quote.get("total_market_value_yi")
    float_mv = quote.get("float_market_value_yi")
    order_diff = quote.get("order_diff")

    volume_shares = quote.get("volume")
    volume_lot = (float(volume_shares) / 100.0) if volume_shares is not None else None
    amount_yuan = quote.get("amount")

    macd_tf_val = active_ind.get("macd_hist", macd_val)
    macd_desc = "趋势偏强" if (macd_tf_val is not None and macd_tf_val > 0) else "趋势偏弱"
    rsi_desc = "超买区间" if (rsi_val is not None and rsi_val >= 70) else ("超卖区间" if (rsi_val is not None and rsi_val <= 30) else "强弱指标")
    tf_name_map = {"day": "日线", "week": "周线", "month": "月线", "intraday": "分时"}
    rsi_desc = f"{tf_name_map.get(active_tf, '日线')} · {rsi_desc}"
    tf_caption = tf_name_map.get(active_tf, "日线")

    sell_lv = sorted(order_book_5.get("sell", []), key=lambda x: int(x.get("level", 0)))
    buy_lv = sorted(order_book_5.get("buy", []), key=lambda x: int(x.get("level", 0)))
    sell_total = sum(float(r.get("volume_lot") or 0) for r in sell_lv)
    buy_total = sum(float(r.get("volume_lot") or 0) for r in buy_lv)
    ofi = (buy_total / sell_total) if sell_total > 0 else None
    ask1 = _find_level(sell_lv, 1).get("price")
    bid1 = _find_level(buy_lv, 1).get("price")
    spread = (float(ask1) - float(bid1)) if (ask1 is not None and bid1 is not None) else None

    cards = [
        (
            "实时快照",
            [
                ("现价", _fmt(price_now, 2)),
                ("涨跌幅", _fmt_signed_pct(change_pct, 2)),
                ("涨跌额", _fmt_signed(change_amt, 2)),
            ],
            "Now / Pct / Chg",
        ),
        (
            "日内区间",
            [
                ("今开", _fmt(open_val, 2)),
                ("昨收", _fmt(ref_val, 2)),
                ("最高", _fmt(high_val, 2)),
                ("最低", _fmt(low_val, 2)),
            ],
            "",
        ),
        (
            "成交活跃",
            [
                ("成交量(手)", _fmt_lot(volume_lot)),
                ("成交额(元)", _fmt_amount_yuan(amount_yuan)),
                ("量比", _fmt(volume_ratio, 2)),
                ("换手率", _fmt_pct(turnover_rate, 2)),
            ],
            "",
        ),
        (
            "波动与均价",
            [
                ("VWAP", _fmt(vwap_val, 2)),
                ("偏离", _fmt_signed_pct(premium_pct, 2)),
                ("振幅", _fmt_pct(amplitude_pct, 2)),
            ],
            "",
        ),
        (
            "盘口结构",
            [
                ("买总量", _fmt_lot(buy_total)),
                ("卖总量", _fmt_lot(sell_total)),
                ("失衡比(B/A)", _fmt(ofi, 2)),
                ("买卖价差", _fmt(spread, 3)),
                ("委差", _fmt_signed(order_diff, 0)),
            ],
            "",
        ),
        (
            "PE 三口径",
            [
                ("PE(动)", _fmt(pe_dynamic, 2)),
                ("PE(静)", _fmt(pe_static, 2)),
                ("PE(滚)", _fmt(pe_rolling, 2)),
            ],
            "Eastmoney 口径",
        ),
        (
            "估值与规模",
            [
                ("PB", _fmt(pb_val, 2)),
                ("股息率", _fmt_pct(dy_val, 2)),
                ("总市值(亿)", _fmt(total_mv, 2)),
                ("流通市值(亿)", _fmt(float_mv, 2)),
            ],
            "",
        ),
        (
            "RSI 组合",
            [
                ("RSI(6)", _fmt(rsi_val, 2)),
                ("RSI(12)", _fmt(rsi12_val, 2)),
                ("RSI(24)", _fmt(rsi24_val, 2)),
            ],
            rsi_desc,
        ),
        (
            "均线组合",
            [
                ("MA5", _fmt(ma5_val, 2)),
                ("MA10", _fmt(ma10_val, 2)),
                ("MA20", _fmt(ma20_val, 2)),
                ("MA60", _fmt(ma60_val, 2)),
            ],
            f"{tf_caption}口径",
        ),
        (
            "MACD",
            [
                ("MACD柱", _fmt(macd_tf_val, 3)),
            ],
            f"{tf_caption} · {macd_desc}",
        ),
        (
            "BOLL",
            [
                ("BOLL %B", _fmt(boll_pct_b_fast if boll_pct_b_fast is not None else boll_val, 2)),
                ("BOLL带宽", _fmt_pct(boll_bw, 2)),
                ("BOLL中轨", _fmt(boll_mid_val, 2)),
            ],
            f"{tf_caption} · 布林带",
        ),
    ]

    cards_snapshot = {
        "timeframe_selected": active_tf,
        "timeframe_label": tf_caption,
        "snapshot": {
            "current_price": price_now,
            "change_pct_display": change_pct,
            "change_amount": change_amt,
            "open": open_val,
            "prev_close": ref_val,
            "high": high_val,
            "low": low_val,
            "quote_time": quote.get("quote_time"),
        },
        "trading": {
            "volume_lot": volume_lot,
            "amount_yuan": amount_yuan,
            "volume_ratio": volume_ratio,
            "turnover_rate": turnover_rate,
            "vwap": vwap_val,
            "premium_pct": premium_pct,
            "amplitude_pct": amplitude_pct,
        },
        "order_book_summary": {
            "buy_total_lot": buy_total,
            "sell_total_lot": sell_total,
            "imbalance_bid_ask": ofi,
            "spread": spread,
            "order_diff": order_diff,
        },
        "valuation": {
            "pe_dynamic": pe_dynamic,
            "pe_static": pe_static,
            "pe_rolling": pe_rolling,
            "pb": pb_val,
            "dividend_yield": dy_val,
            "total_market_value_yi": total_mv,
            "float_market_value_yi": float_mv,
        },
        "technical_current_tf": {
            "macd_hist": macd_tf_val,
            "rsi6": rsi_val,
            "rsi12": rsi12_val,
            "rsi24": rsi24_val,
            "ma5": ma5_val,
            "ma10": ma10_val,
            "ma20": ma20_val,
            "ma60": ma60_val,
            "boll_pct_b": boll_pct_b_fast if boll_pct_b_fast is not None else boll_val,
            "boll_bandwidth": boll_bw,
            "boll_mid": boll_mid_val,
        },
        "cards": {title: {k: v for k, v in kv_rows} for title, kv_rows, _ in cards},
    }

    fast_compact_metrics["ui_state"] = {
        "selected_timeframe": active_tf,
        "selected_timeframe_label": tf_caption,
    }
    fast_compact_metrics["cards_snapshot"] = cards_snapshot

    export_payload = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "app": "Quant",
            "analysis_user": (st.session_state.get("deepseek_user_input", "") or "").strip(),
        },
        "stock": {"code": selected_code, "name": selected_name},
        "slow_engine": selected_slow,
        "fast_engine": {
            "quote": quote,
            "indicators": ind,
            "rsi_multi": panel.get("rsi_multi", {}),
            "tf_indicators": panel.get("tf_indicators", {}),
            "order_book_5": order_book_5,
            "intraday": intraday_df,
            "depth_note": panel.get("depth_note"),
            "error": panel.get("error"),
            "compact_metrics": fast_compact_metrics,
            "cards_snapshot": cards_snapshot,
        },
    }
    export_json = json.dumps(_json_safe(export_payload), ensure_ascii=False, indent=2)
    analysis_payload = _build_analysis_payload(export_payload)
    analysis_json = json.dumps(analysis_payload, ensure_ascii=True, separators=(",", ":"))
    json_b64 = base64.b64encode(export_json.encode("utf-8")).decode("ascii")

    if copy_slot is not None:
        with copy_slot:
            html(
                f"""
                <div style="margin:0.1rem 0 0.45rem 0;">
                  <button id="copy-json-btn-{selected_code}"
                    style="width:100%;height:44px;padding:0 0.95rem;border-radius:10px;border:1px solid #a8c2e8;background:#dbeafe;color:#0f2a52;font-size:1.05rem;font-weight:700;cursor:pointer;white-space:nowrap;">
                    复制JSON
                  </button>
                  <div id="copy-json-msg-{selected_code}" style="margin-top:0.35rem;color:#2e4b6e;font-size:0.88rem;"></div>
                </div>
                <script>
                  const btn = document.getElementById("copy-json-btn-{selected_code}");
                  const msg = document.getElementById("copy-json-msg-{selected_code}");
                  const b64 = "{json_b64}";
                  const text = decodeURIComponent(escape(window.atob(b64)));
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
                height=96,
            )
            if st.button("DeepSeek分析", key=f"deepseek_analyze_{selected_code}", use_container_width=True):
                progress = st.progress(0, text="准备快照...")
                snapshot_hash = hashlib.sha256(analysis_json.encode("utf-8")).hexdigest()
                cache_store = st.session_state.get("analysis_payload_cache", {})
                cache_item = cache_store.get(snapshot_hash)
                try:
                    if cache_item and isinstance(cache_item, dict):
                        progress.progress(100, text="快照未变化，复用上次分析")
                        result = str(cache_item.get("result", "") or "")
                        usage_stats = cache_item.get("usage", {}) or {}
                        est_cost = 0.0
                        elapsed = 0.0
                        from_cache = True
                    else:
                        progress.progress(45, text="调用 DeepSeek 分析中...")
                        with st.spinner("正在分析，请稍候..."):
                            result, usage_stats, est_cost, elapsed = _call_deepseek_analysis(json_text=analysis_json)
                        cache_store[snapshot_hash] = {
                            "result": result,
                            "usage": usage_stats,
                            "saved_at": datetime.now().strftime("%m-%d %H:%M:%S"),
                            "stock_code": selected_code,
                            "stock_name": selected_name,
                        }
                        st.session_state["analysis_payload_cache"] = cache_store
                        _save_analysis_cache(cache_store)
                        from_cache = False
                    progress.progress(100, text="分析完成")
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": result,
                        "stats": {
                            "usage": usage_stats,
                            "cost": est_cost,
                            "elapsed": elapsed,
                        },
                        "snapshot_hash": snapshot_hash,
                        "from_cache": from_cache,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map
                    progress.empty()
                except AuthenticationError:
                    progress.empty()
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": "DeepSeek 认证失败：API Key 无效或已过期。",
                        "stats": {},
                        "snapshot_hash": snapshot_hash,
                        "from_cache": False,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map
                except RateLimitError:
                    progress.empty()
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": "DeepSeek 限流：请求过快，请稍后重试。",
                        "stats": {},
                        "snapshot_hash": snapshot_hash,
                        "from_cache": False,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map
                except APIConnectionError as exc:
                    progress.empty()
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": f"DeepSeek 连接失败：{type(exc).__name__}\n请检查网络/VPN，稍后重试。",
                        "stats": {},
                        "snapshot_hash": snapshot_hash,
                        "from_cache": False,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map
                except APIStatusError as exc:
                    progress.empty()
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": (
                            f"DeepSeek 服务返回异常状态：HTTP {getattr(exc, 'status_code', 'N/A')}\n"
                            f"{exc}"
                        ),
                        "stats": {},
                        "snapshot_hash": snapshot_hash,
                        "from_cache": False,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map
                except Exception as exc:
                    progress.empty()
                    analysis_map = st.session_state.get("analysis_inline_by_stock", {})
                    analysis_map[str(selected_code)] = {
                        "title": f"{selected_name} ({selected_code})",
                        "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                        "text": f"DeepSeek 分析失败: {type(exc).__name__}: {exc}",
                        "stats": {},
                        "snapshot_hash": snapshot_hash,
                        "from_cache": False,
                    }
                    st.session_state["analysis_inline_by_stock"] = analysis_map

    for i in range(0, len(cards), 4):
        cols = st.columns(4)
        for col, (title, kv_rows, desc) in zip(cols, cards[i : i + 4]):
            col.markdown(_card_html(title, kv_rows, desc), unsafe_allow_html=True)

    st.markdown('<div class="subsection-divider"></div>', unsafe_allow_html=True)
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
        st.markdown('<div class="panel-title">实时盘口<span class="unit-sub">单位：手</span></div>', unsafe_allow_html=True)
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

    analysis_item = (st.session_state.get("analysis_inline_by_stock", {}) or {}).get(str(selected_code))
    if analysis_item and str(analysis_item.get("text", "")).strip():
        analysis_text = str(analysis_item.get("text", ""))
        analysis_title = str(analysis_item.get("title", f"{selected_name} ({selected_code})"))
        analysis_time = str(analysis_item.get("time", ""))
        analysis_stats = analysis_item.get("stats", {}) or {}
        usage = analysis_stats.get("usage", {}) or {}
        elapsed = analysis_stats.get("elapsed")
        cost = analysis_stats.get("cost")
        from_cache = bool(analysis_item.get("from_cache", False))

        st.markdown('<div class="subsection-divider"></div>', unsafe_allow_html=True)
        st.markdown("### DeepSeek 分析")
        st.caption(f"{analysis_title} · {analysis_time}")
        if from_cache:
            st.caption("本次为同快照复用结果（未调用 API）。")
        if elapsed is not None and cost is not None:
            st.caption(
                f"耗时: {elapsed:.2f}s | 输入: {usage.get('prompt_tokens', 0)} | 输出: {usage.get('completion_tokens', 0)} | "
                f"缓存命中: {usage.get('prompt_cache_hit_tokens', 0)} | 预估成本: {cost:.4f} 元"
            )

        st.text_area(
            "分析文档",
            value=analysis_text,
            height=320,
            key=f"analysis_inline_{selected_code}_{analysis_item.get('snapshot_hash', '')[:12]}",
            label_visibility="collapsed",
        )
        analysis_doc_b64 = base64.b64encode(analysis_text.encode("utf-8")).decode("ascii")
        html(
            f"""
            <div style="margin-top:0.2rem;">
              <button id="copy-analysis-doc-{selected_code}"
                style="height:38px;padding:0 0.9rem;border-radius:8px;border:1px solid #a8c2e8;background:#dbeafe;color:#0f2a52;font-size:0.95rem;font-weight:700;cursor:pointer;">
                复制分析文档
              </button>
              <span id="copy-analysis-msg-{selected_code}" style="margin-left:0.55rem;color:#2e4b6e;font-size:0.86rem;"></span>
            </div>
            <script>
              const b = document.getElementById("copy-analysis-doc-{selected_code}");
              const m = document.getElementById("copy-analysis-msg-{selected_code}");
              const t = decodeURIComponent(escape(window.atob("{analysis_doc_b64}")));
              b.onclick = async function () {{
                try {{
                  await navigator.clipboard.writeText(t);
                  m.textContent = "已复制";
                }} catch (e) {{
                  m.textContent = "复制失败";
                }}
              }};
            </script>
            """,
            height=64,
        )

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
