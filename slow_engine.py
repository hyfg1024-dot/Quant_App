import json
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import akshare as ak
import pandas as pd
import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "quant_app.db"

STOCK_POOL: List[Tuple[str, str]] = [
    ("601088", "中国神华"),
    ("600598", "北大荒"),
]


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "None", "nan", "NaN"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _normalize_symbol_input(text: str) -> str:
    raw = str(text).strip().lower()
    digits = "".join(ch for ch in raw if ch.isdigit())

    if raw.startswith("hk"):
        if not digits:
            return ""
        return digits[-5:].zfill(5)

    if len(digits) == 5:
        return digits
    if len(digits) >= 6:
        return digits[-6:]
    return ""


def _is_hk_symbol(symbol: str) -> bool:
    s = str(symbol).strip()
    return s.isdigit() and len(s) == 5


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_info (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                bucket TEXT NOT NULL DEFAULT 'watch'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fundamental_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                pe REAL,
                pe_ttm REAL,
                pe_dynamic REAL,
                pb REAL,
                dividend_yield REAL,
                commodity_prices TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (code) REFERENCES stock_info(code)
            )
            """
        )
        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fundamental_data)").fetchall()
        }
        stock_info_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(stock_info)").fetchall()
        }
        if "bucket" not in stock_info_cols:
            conn.execute("ALTER TABLE stock_info ADD COLUMN bucket TEXT NOT NULL DEFAULT 'watch'")
        if "pe_ttm" not in existing_cols:
            conn.execute("ALTER TABLE fundamental_data ADD COLUMN pe_ttm REAL")
        if "pe_dynamic" not in existing_cols:
            conn.execute("ALTER TABLE fundamental_data ADD COLUMN pe_dynamic REAL")
        conn.commit()


def upsert_stock_pool(stock_pool: List[Tuple[str, str]] = STOCK_POOL) -> None:
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO stock_info(code, name, bucket) VALUES (?, ?, 'watch')",
            [(code, name) for code, name in stock_pool],
        )
        conn.commit()


def get_stock_pool() -> List[Tuple[str, str]]:
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT code, name
            FROM stock_info
            ORDER BY CASE bucket WHEN 'holding' THEN 0 ELSE 1 END, code
            """
        )
        rows = cur.fetchall()
        if rows:
            return [(str(row[0]), str(row[1])) for row in rows]

    upsert_stock_pool(STOCK_POOL)
    return STOCK_POOL.copy()


def get_stock_pool_with_bucket() -> List[Tuple[str, str, str]]:
    init_db()
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT code, name, COALESCE(bucket, 'watch') AS bucket
            FROM stock_info
            ORDER BY CASE bucket WHEN 'holding' THEN 0 ELSE 1 END, code
            """
        )
        return [(str(row[0]), str(row[1]), str(row[2])) for row in cur.fetchall()]


def add_stock_to_pool(code: str, name: str, bucket: str = "watch") -> None:
    normalized_code = str(code).strip()
    normalized_name = str(name).strip()
    normalized_bucket = str(bucket).strip().lower()
    if not normalized_code.isdigit() or len(normalized_code) not in {5, 6}:
        raise ValueError("股票代码必须是 5 位(港股)或 6 位(A股)数字")
    if not normalized_name:
        raise ValueError("股票名称不能为空")
    if normalized_bucket not in {"holding", "watch"}:
        raise ValueError("bucket 必须是 holding 或 watch")

    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO stock_info(code, name, bucket) VALUES (?, ?, ?)",
            (normalized_code, normalized_name, normalized_bucket),
        )
        conn.commit()


def _normalize_name(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text))
    return normalized.replace(" ", "").replace("\u3000", "").upper()


def resolve_stock_identity(query: str) -> Tuple[str, str]:
    init_db()
    q = str(query).strip()
    if not q:
        raise ValueError("请输入股票代码或股票名称")

    # 代码输入兼容: 600036 / sh600036 / sz000001 / 00700 / hk00700
    code_candidate = _normalize_symbol_input(q)

    # 优先在本地库解析
    with _connect() as conn:
        if code_candidate and len(code_candidate) in {5, 6}:
            row = conn.execute(
                "SELECT code, name FROM stock_info WHERE code = ?",
                (code_candidate,),
            ).fetchone()
            if row:
                return str(row[0]), str(row[1])

        row = conn.execute(
            "SELECT code, name FROM stock_info WHERE name = ?",
            (q,),
        ).fetchone()
        if row:
            return str(row[0]), str(row[1])

    # A股按代码精确查
    if code_candidate and len(code_candidate) == 6:
        try:
            code_name_df = ak.stock_info_a_code_name()
            code_name_df["code"] = code_name_df["code"].astype(str).str.strip()
            code_name_df["name"] = code_name_df["name"].astype(str).str.strip()
            matched = code_name_df[code_name_df["code"] == code_candidate]
            if not matched.empty:
                row = matched.iloc[0]
                return str(row["code"]), str(row["name"])
        except Exception:
            pass
        raise ValueError(f"未找到代码为 {code_candidate} 的 A 股标的")

    # 港股按代码精确查
    if code_candidate and len(code_candidate) == 5:
        try:
            hk_df = ak.stock_hk_spot()
            hk_df["代码"] = hk_df["代码"].astype(str).str.strip().str.zfill(5)
            name_col = "中文名称" if "中文名称" in hk_df.columns else "名称"
            hk_df[name_col] = hk_df[name_col].astype(str).str.strip()
            matched = hk_df[hk_df["代码"] == code_candidate]
            if not matched.empty:
                row = matched.iloc[0]
                return str(row["代码"]), str(row[name_col])
        except Exception:
            pass
        raise ValueError(f"未找到代码为 {code_candidate} 的港股标的")

    # 名称查询: 先A股再港股
    q_norm = _normalize_name(q)

    try:
        code_name_df = ak.stock_info_a_code_name()
        code_name_df["code"] = code_name_df["code"].astype(str).str.strip()
        code_name_df["name"] = code_name_df["name"].astype(str).str.strip()
        code_name_df["name_norm"] = code_name_df["name"].map(_normalize_name)

        matched_exact = code_name_df[code_name_df["name_norm"] == q_norm]
        if not matched_exact.empty:
            row = matched_exact.iloc[0]
            return str(row["code"]), str(row["name"])

        matched_contains = code_name_df[code_name_df["name_norm"].str.contains(q_norm, na=False)]
        if not matched_contains.empty:
            row = matched_contains.iloc[0]
            return str(row["code"]), str(row["name"])
    except Exception:
        pass

    try:
        hk_df = ak.stock_hk_spot()
        hk_df["代码"] = hk_df["代码"].astype(str).str.strip().str.zfill(5)
        name_col = "中文名称" if "中文名称" in hk_df.columns else "名称"
        hk_df[name_col] = hk_df[name_col].astype(str).str.strip()
        hk_df["name_norm"] = hk_df[name_col].map(_normalize_name)

        matched_exact = hk_df[hk_df["name_norm"] == q_norm]
        if not matched_exact.empty:
            row = matched_exact.iloc[0]
            return str(row["代码"]), str(row[name_col])

        matched_contains = hk_df[hk_df["name_norm"].str.contains(q_norm, na=False)]
        if not matched_contains.empty:
            row = matched_contains.iloc[0]
            return str(row["代码"]), str(row[name_col])
    except Exception:
        pass

    raise ValueError(f"未找到名称为 {q} 的A股/港股标的")


def add_stock_by_query(query: str, bucket: str = "watch") -> Tuple[str, str]:
    code, name = resolve_stock_identity(query)
    add_stock_to_pool(code, name, bucket=bucket)
    return code, name


def remove_stock_from_pool(code: str, delete_history: bool = False) -> None:
    target = str(code).strip()
    if not target:
        raise ValueError("股票代码不能为空")

    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM stock_info WHERE code = ?", (target,))
        if delete_history:
            conn.execute("DELETE FROM fundamental_data WHERE code = ?", (target,))
        conn.commit()


def _fetch_pb_from_baidu(symbol: str) -> Optional[float]:
    if _is_hk_symbol(symbol):
        return _fetch_hk_valuation_from_baidu(symbol, "市净率")
    try:
        df = ak.stock_zh_valuation_baidu(
            symbol=symbol,
            indicator="市净率",
            period="近一年",
        )
        if df is None or df.empty:
            return None
        return _to_float(df.iloc[-1]["value"])
    except Exception:
        return None


def _fetch_hk_valuation_from_baidu(symbol: str, indicator: str) -> Optional[float]:
    try:
        df = ak.stock_hk_valuation_baidu(
            symbol=str(symbol).zfill(5),
            indicator=indicator,
            period="近一年",
        )
        if df is None or df.empty:
            return None
        return _to_float(df.iloc[-1]["value"])
    except Exception:
        return None


def _fetch_metrics_from_eastmoney_direct(symbol: str) -> Dict[str, Optional[float]]:
    secid = ("1." if str(symbol).startswith("6") else "0.") + str(symbol)
    fields = "f57,f58,f9,f162,f167"
    urls = [
        "https://push2.eastmoney.com/api/qt/stock/get",
        "http://push2.eastmoney.com/api/qt/stock/get",
    ]

    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com"}
    for _ in range(3):
        for url in urls:
            try:
                resp = requests.get(
                    url,
                    params={"invt": "2", "fltt": "2", "secid": secid, "fields": fields},
                    headers=headers,
                    timeout=8,
                )
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data") or {}
                return {
                    "pe_dynamic": _to_float(data.get("f162")),  # 动态市盈率
                    "pe_ttm": _to_float(data.get("f9")),        # 近似按 TTM 口径
                    "pb": _to_float(data.get("f167")),  # 市净率
                }
            except Exception:
                continue

    return {"pe_dynamic": None, "pe_ttm": None, "pb": None}


def _fetch_metrics_from_tencent(symbol: str) -> Dict[str, Optional[float]]:
    symbol_text = str(symbol).strip()
    if _is_hk_symbol(symbol_text):
        exchange = "hk"
    elif symbol_text.startswith(("5", "6", "9")):
        exchange = "sh"
    else:
        exchange = "sz"
    url = f"https://qt.gtimg.cn/q={exchange}{symbol_text}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
        resp.raise_for_status()
        resp.encoding = "gbk"
        text = resp.text
        if '"' not in text or "~" not in text:
            return {"pe": None, "pb": None}
        payload = text.split('"', 1)[1].rsplit('"', 1)[0]
        fields = payload.split("~")
        # 腾讯字段: 46=PB, 52=动态PE, 53=TTM PE
        pe_dynamic = _to_float(fields[52]) if len(fields) > 52 else None
        pe_ttm = _to_float(fields[53]) if len(fields) > 53 else None
        pb = _to_float(fields[46]) if len(fields) > 46 else None
        return {"pe_dynamic": pe_dynamic, "pe_ttm": pe_ttm, "pb": pb}
    except Exception:
        return {"pe_dynamic": None, "pe_ttm": None, "pb": None}


def _fetch_hk_metrics_from_em(symbol: str) -> Dict[str, Optional[float]]:
    try:
        df = ak.stock_hk_financial_indicator_em(symbol=str(symbol).zfill(5))
        if df is None or df.empty:
            return {"pe_dynamic": None, "pe_ttm": None, "pb": None, "dividend_yield": None}

        row = df.iloc[0]
        pe = _to_float(row.get("市盈率"))
        pb = _to_float(row.get("市净率"))
        dividend = _to_float(row.get("股息率TTM(%)"))

        # 有些源返回 0.8 表示 0.8%，也可能返回 0.008，做一次容错归一化
        if dividend is not None and 0 < dividend < 0.2:
            dividend = dividend * 100

        return {
            "pe_dynamic": pe,
            "pe_ttm": pe,
            "pb": pb,
            "dividend_yield": dividend,
        }
    except Exception:
        return {"pe_dynamic": None, "pe_ttm": None, "pb": None, "dividend_yield": None}


def _fetch_dividend_yield_from_em(symbol: str) -> Optional[float]:
    try:
        df = ak.stock_fhps_detail_em(symbol=str(symbol))
        if df is None or df.empty:
            return None
        if "现金分红-股息率" not in df.columns:
            return None

        tmp = df.copy()
        tmp["现金分红-股息率"] = pd.to_numeric(tmp["现金分红-股息率"], errors="coerce")
        tmp = tmp.dropna(subset=["现金分红-股息率"])
        if tmp.empty:
            return None

        # 优先使用年报(12-31)，避免中报分红导致股息率偏低。
        annual = tmp[tmp["报告期"].astype(str).str.endswith("12-31")]
        chosen = annual if not annual.empty else tmp
        val = _to_float(chosen.iloc[-1]["现金分红-股息率"])
        if val is None:
            return None
        # 接口返回小数口径(0.055)，统一转换为百分比口径(5.50)。
        return val * 100
    except Exception:
        return None


def _fetch_related_commodity_prices(symbol: str) -> Dict[str, Dict[str, Optional[float]]]:
    # Sina 内盘连续合约代码；不同品种可按策略需要继续扩展。
    contracts_map = {
        "601088": ["ZC0", "JM0"],  # 动力煤、焦煤（能源相关）
        "600598": ["M0", "C0"],    # 豆粕、玉米（农业相关）
    }
    contracts = contracts_map.get(symbol, [])
    result: Dict[str, Dict[str, Optional[float]]] = {}

    for contract in contracts:
        try:
            df = ak.futures_zh_daily_sina(symbol=contract)
            if df is None or df.empty:
                result[contract] = {"date": None, "close": None}
                continue
            last = df.iloc[-1]
            result[contract] = {
                "date": str(last.get("date")),
                "close": _to_float(last.get("close")),
            }
        except Exception:
            result[contract] = {"date": None, "close": None}

    return result


def fetch_latest_fundamental(symbol: str, default_name: str = "") -> Dict:
    symbol = str(symbol).strip()
    name = default_name or symbol
    pe = None
    pe_ttm = None
    pe_dynamic = None
    pb = None
    dividend_yield = None

    if _is_hk_symbol(symbol):
        # 港股主通道：新浪港股列表（名称）+ 东方财富财务指标（PE/PB/股息率）
        try:
            hk_df = ak.stock_hk_spot()
            hk_df["代码"] = hk_df["代码"].astype(str).str.strip().str.zfill(5)
            name_col = "中文名称" if "中文名称" in hk_df.columns else "名称"
            row_df = hk_df[hk_df["代码"] == symbol]
            if not row_df.empty:
                row = row_df.iloc[0]
                name = str(row.get(name_col, name))
        except Exception:
            pass

        hk_metrics = _fetch_hk_metrics_from_em(symbol)
        pe_dynamic = hk_metrics.get("pe_dynamic")
        pe_ttm = hk_metrics.get("pe_ttm")
        pb = hk_metrics.get("pb")
        dividend_yield = hk_metrics.get("dividend_yield")

        # 港股估值兜底：百度估值 + 腾讯快照
        if pe_ttm is None:
            pe_ttm = _fetch_hk_valuation_from_baidu(symbol, "市盈率(TTM)")
        if pb is None:
            pb = _fetch_hk_valuation_from_baidu(symbol, "市净率")

        tx_metrics = _fetch_metrics_from_tencent(symbol)
        if pe_dynamic is None:
            pe_dynamic = tx_metrics.get("pe_dynamic")
        if pe_ttm is None:
            pe_ttm = tx_metrics.get("pe_ttm")
        if pb is None:
            pb = tx_metrics.get("pb")
    else:
        # A股主通道：东方财富快照（AkShare）
        try:
            spot_df = ak.stock_zh_a_spot_em()
            row_df = spot_df[spot_df["代码"] == symbol]
            if not row_df.empty:
                row = row_df.iloc[0]
                name = str(row.get("名称", name))
                pe_dynamic = _to_float(row.get("市盈率-动态") or row.get("市盈率动态") or row.get("市盈率"))
                pb = _to_float(row.get("市净率"))
                dividend_yield = _to_float(row.get("股息率") or row.get("股息率(%)"))
        except Exception:
            pass

        # A股兜底：东方财富接口 + 腾讯 + 百度
        if pe_dynamic is None or pe_ttm is None or pb is None:
            em_metrics = _fetch_metrics_from_eastmoney_direct(symbol)
            if pe_dynamic is None:
                pe_dynamic = em_metrics.get("pe_dynamic")
            if pe_ttm is None:
                pe_ttm = em_metrics.get("pe_ttm")
            if pb is None:
                pb = em_metrics.get("pb")

        if pe_dynamic is None or pe_ttm is None or pb is None:
            tx_metrics = _fetch_metrics_from_tencent(symbol)
            if pe_dynamic is None:
                pe_dynamic = tx_metrics.get("pe_dynamic")
            if pe_ttm is None:
                pe_ttm = tx_metrics.get("pe_ttm")
            if pb is None:
                pb = tx_metrics.get("pb")

        if pb is None:
            pb = _fetch_pb_from_baidu(symbol)

        if dividend_yield is None:
            dividend_yield = _fetch_dividend_yield_from_em(symbol)

    # 与中信口径对齐：优先使用 TTM PE，拿不到再退化为动态 PE
    pe = pe_ttm if pe_ttm is not None else pe_dynamic

    commodity_prices = _fetch_related_commodity_prices(symbol)
    trade_date = datetime.now().strftime("%Y-%m-%d")

    return {
        "trade_date": trade_date,
        "code": symbol,
        "name": name,
        "pe": pe,
        "pe_ttm": pe_ttm,
        "pe_dynamic": pe_dynamic,
        "pb": pb,
        "dividend_yield": dividend_yield,
        "commodity_prices": commodity_prices,
    }


def save_fundamental(record: Dict) -> None:
    with _connect() as conn:
        cur = conn.cursor()
        for field in ("pe", "pe_ttm", "pe_dynamic", "pb", "dividend_yield"):
            if record.get(field) is None:
                cur.execute(
                    f"""
                    SELECT {field}
                    FROM fundamental_data
                    WHERE code = ? AND {field} IS NOT NULL
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (record["code"],),
                )
                row = cur.fetchone()
                if row:
                    record[field] = row[0]

        conn.execute(
            """
            INSERT INTO fundamental_data(
                trade_date, code, pe, pe_ttm, pe_dynamic, pb, dividend_yield, commodity_prices, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["trade_date"],
                record["code"],
                record["pe"],
                record.get("pe_ttm"),
                record.get("pe_dynamic"),
                record["pb"],
                record["dividend_yield"],
                json.dumps(record["commodity_prices"], ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def update_fundamental_data(stock_pool: Optional[List[Tuple[str, str]]] = None) -> List[Dict]:
    init_db()
    if stock_pool is None:
        stock_pool = get_stock_pool()
    else:
        upsert_stock_pool(stock_pool)

    rows: List[Dict] = []
    for code, name in stock_pool:
        row = fetch_latest_fundamental(code, name)
        save_fundamental(row)
        rows.append(row)
    return rows


def get_latest_fundamental_snapshot() -> List[Dict]:
    sql = """
    WITH ranked AS (
        SELECT
            f.trade_date,
            f.code,
            s.name,
            f.pe,
            f.pe_ttm,
            f.pe_dynamic,
            f.pb,
            f.dividend_yield,
            f.commodity_prices,
            f.created_at,
            ROW_NUMBER() OVER (PARTITION BY f.code ORDER BY f.created_at DESC, f.id DESC) AS rn
        FROM fundamental_data f
        JOIN stock_info s ON s.code = f.code
    )
    SELECT trade_date, code, name, pe, pe_ttm, pe_dynamic, pb, dividend_yield, commodity_prices, created_at
    FROM ranked
    WHERE rn = 1
    ORDER BY code
    """

    with _connect() as conn:
        cur = conn.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.add_job(
        func=update_fundamental_data,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18, minute=5),
        id="slow_engine_daily_update",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler


def run_smoke_test() -> None:
    print("[SlowEngine] init_db + update_fundamental_data ...")
    rows = update_fundamental_data(STOCK_POOL)

    if len(rows) != 2:
        raise RuntimeError(f"Expected 2 rows, got {len(rows)}")

    snapshot = get_latest_fundamental_snapshot()
    codes = {row["code"] for row in snapshot}
    expected = {"601088", "600598"}
    if not expected.issubset(codes):
        raise RuntimeError(f"Missing expected codes in DB snapshot: {expected - codes}")

    print("[SlowEngine] DB write OK. Latest snapshot:")
    for row in snapshot:
        print(
            f"  - {row['code']} {row['name']} | date={row['trade_date']} "
            f"PE(TTM)={row['pe']} PE(动)={row.get('pe_dynamic')} PB={row['pb']} DY={row['dividend_yield']}"
        )


if __name__ == "__main__":
    run_smoke_test()
