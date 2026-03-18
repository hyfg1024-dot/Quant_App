import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import akshare as ak
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


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_info (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL
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
                pb REAL,
                dividend_yield REAL,
                commodity_prices TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (code) REFERENCES stock_info(code)
            )
            """
        )
        conn.commit()


def upsert_stock_pool(stock_pool: List[Tuple[str, str]] = STOCK_POOL) -> None:
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO stock_info(code, name) VALUES (?, ?)",
            stock_pool,
        )
        conn.commit()


def _fetch_pb_from_baidu(symbol: str) -> Optional[float]:
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
    name = default_name or symbol
    pe = None
    pb = None
    dividend_yield = None

    # 主通道：东方财富快照（AkShare）
    try:
        spot_df = ak.stock_zh_a_spot_em()
        row_df = spot_df[spot_df["代码"] == symbol]
        if not row_df.empty:
            row = row_df.iloc[0]
            name = str(row.get("名称", name))
            pe = _to_float(row.get("市盈率-动态") or row.get("市盈率动态") or row.get("市盈率"))
            pb = _to_float(row.get("市净率"))
            dividend_yield = _to_float(row.get("股息率") or row.get("股息率(%)"))
    except Exception:
        pass

    # 兜底：至少补足 PB，保证慢引擎可持续写库。
    if pb is None:
        pb = _fetch_pb_from_baidu(symbol)

    commodity_prices = _fetch_related_commodity_prices(symbol)
    trade_date = datetime.now().strftime("%Y-%m-%d")

    return {
        "trade_date": trade_date,
        "code": symbol,
        "name": name,
        "pe": pe,
        "pb": pb,
        "dividend_yield": dividend_yield,
        "commodity_prices": commodity_prices,
    }


def save_fundamental(record: Dict) -> None:
    with _connect() as conn:
        cur = conn.cursor()
        for field in ("pe", "pb", "dividend_yield"):
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
                trade_date, code, pe, pb, dividend_yield, commodity_prices, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["trade_date"],
                record["code"],
                record["pe"],
                record["pb"],
                record["dividend_yield"],
                json.dumps(record["commodity_prices"], ensure_ascii=False),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def update_fundamental_data(stock_pool: List[Tuple[str, str]] = STOCK_POOL) -> List[Dict]:
    init_db()
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
            f.pb,
            f.dividend_yield,
            f.commodity_prices,
            f.created_at,
            ROW_NUMBER() OVER (PARTITION BY f.code ORDER BY f.created_at DESC, f.id DESC) AS rn
        FROM fundamental_data f
        JOIN stock_info s ON s.code = f.code
    )
    SELECT trade_date, code, name, pe, pb, dividend_yield, commodity_prices, created_at
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
            f"PE={row['pe']} PB={row['pb']} DY={row['dividend_yield']}"
        )


if __name__ == "__main__":
    run_smoke_test()
