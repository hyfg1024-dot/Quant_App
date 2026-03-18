from typing import Dict, List, Optional

import pandas as pd
import requests

TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={exchange}{symbol}"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={exchange}{symbol}"
TENCENT_DAILY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={exchange}{symbol},day,,,{count},qfq"


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "-", "--"}:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _resolve_exchange(symbol: str) -> str:
    return "sh" if str(symbol).startswith("6") else "sz"


def _build_order_book_10(bids_5: List[Dict], asks_5: List[Dict]) -> Dict[str, List[Dict]]:
    buy = []
    sell = []

    for i in range(10):
        level = i + 1
        if i < len(bids_5):
            buy.append(bids_5[i])
        else:
            buy.append({"level": level, "price": None, "volume_lot": None})

        if i < len(asks_5):
            sell.append(asks_5[i])
        else:
            sell.append({"level": level, "price": None, "volume_lot": None})

    return {"buy": buy, "sell": sell}


def _parse_tencent_fields(symbol: str, fields: List[str]) -> Dict:
    if len(fields) < 60:
        raise ValueError("Malformed Tencent payload")

    name = fields[1].strip() or symbol
    current_price = _to_float(fields[3])
    prev_close = _to_float(fields[4])
    volume_lot = _to_float(fields[36])  # 手
    amount_wan = _to_float(fields[37])  # 万元
    quote_time = fields[30].strip()

    change_amount = _to_float(fields[31])
    change_pct = _to_float(fields[32])

    if current_price is None and prev_close is not None:
        current_price = prev_close

    volume = volume_lot * 100 if volume_lot is not None else None
    amount = amount_wan * 10000 if amount_wan is not None else None

    vwap = _to_float(fields[51])
    if vwap is None:
        if volume and volume > 0 and amount and amount > 0:
            vwap = amount / volume
        else:
            vwap = current_price

    premium_pct = None
    if current_price is not None and vwap is not None and vwap > 0:
        premium_pct = (current_price - vwap) / vwap * 100

    bids_5: List[Dict] = []
    asks_5: List[Dict] = []
    for i in range(5):
        bid_price = _to_float(fields[9 + i * 2])
        bid_vol = _to_float(fields[10 + i * 2])
        ask_price = _to_float(fields[19 + i * 2])
        ask_vol = _to_float(fields[20 + i * 2])

        bids_5.append({"level": i + 1, "price": bid_price, "volume_lot": bid_vol})
        asks_5.append({"level": i + 1, "price": ask_price, "volume_lot": ask_vol})

    return {
        "symbol": symbol,
        "name": name,
        "current_price": current_price,
        "prev_close": prev_close,
        "change_amount": change_amount,
        "change_pct": change_pct,
        "high": _to_float(fields[33]),
        "low": _to_float(fields[34]),
        "volume": volume,
        "amount": amount,
        "vwap": vwap,
        "premium_pct": premium_pct,
        "quote_time": quote_time,
        "is_trading_data": bool(volume_lot and volume_lot > 0),
        "pe_dynamic": _to_float(fields[52]),
        "pe_ttm": _to_float(fields[53]),
        "pb": _to_float(fields[46]),
        "order_book_5": {"buy": bids_5, "sell": asks_5},
        "order_book_10": _build_order_book_10(bids_5, asks_5),
        "error": None,
    }


def _fetch_tencent_quote(symbol: str) -> Dict:
    exchange = _resolve_exchange(symbol)
    url = TENCENT_QUOTE_URL.format(exchange=exchange, symbol=symbol)
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    resp.raise_for_status()
    resp.encoding = "gbk"

    text = resp.text
    if '"' not in text or '~' not in text:
        raise ValueError("No Tencent quote payload")

    payload = text.split('"', 1)[1].rsplit('"', 1)[0]
    fields = payload.split("~")
    return _parse_tencent_fields(symbol, fields)


def fetch_realtime_quote(symbol: str) -> Dict:
    try:
        return _fetch_tencent_quote(symbol)
    except Exception as exc:
        return {
            "symbol": symbol,
            "name": symbol,
            "current_price": None,
            "prev_close": None,
            "change_amount": None,
            "change_pct": None,
            "high": None,
            "low": None,
            "volume": None,
            "amount": None,
            "vwap": None,
            "premium_pct": None,
            "quote_time": None,
            "is_trading_data": False,
            "pe_dynamic": None,
            "pe_ttm": None,
            "pb": None,
            "order_book_5": {"buy": [], "sell": []},
            "order_book_10": {
                "buy": [{"level": i + 1, "price": None, "volume_lot": None} for i in range(10)],
                "sell": [{"level": i + 1, "price": None, "volume_lot": None} for i in range(10)],
            },
            "error": str(exc),
        }


def fetch_intraday_flow(symbol: str) -> pd.DataFrame:
    exchange = _resolve_exchange(symbol)
    url = TENCENT_MINUTE_URL.format(exchange=exchange, symbol=symbol)
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    resp.raise_for_status()
    payload = resp.json()

    code_key = f"{exchange}{symbol}"
    target = payload.get("data", {}).get(code_key, {})
    data_obj = target.get("data", {})
    raw_lines = data_obj.get("data", [])
    trade_date = str(data_obj.get("date", ""))

    rows = []
    for line in raw_lines:
        parts = str(line).split()
        if len(parts) < 4:
            continue
        hhmm, price_text, vol_text, amount_text = parts[:4]
        time_text = f"{trade_date}{hhmm}" if trade_date else hhmm
        rows.append(
            {
                "time": pd.to_datetime(time_text, format="%Y%m%d%H%M", errors="coerce"),
                "price": _to_float(price_text),
                "volume_lot_cum": _to_float(vol_text),
                "amount": _to_float(amount_text),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["time", "price", "volume_lot", "amount"])

    df = pd.DataFrame(rows).dropna(subset=["time"]).reset_index(drop=True)
    df["volume_lot"] = df["volume_lot_cum"].diff().fillna(df["volume_lot_cum"])
    df["volume_lot"] = df["volume_lot"].clip(lower=0)
    return df[["time", "price", "volume_lot", "amount"]]


def _calc_rsi(close: pd.Series, period: int = 6) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def fetch_technical_indicators(symbol: str, count: int = 120) -> Dict[str, Optional[float]]:
    exchange = _resolve_exchange(symbol)
    url = TENCENT_DAILY_URL.format(exchange=exchange, symbol=symbol, count=count)
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
    resp.raise_for_status()
    payload = resp.json()

    code_key = f"{exchange}{symbol}"
    kline_data = payload.get("data", {}).get(code_key, {}).get("qfqday", [])
    if not kline_data:
        raise ValueError("No daily kline data")

    normalized = [row[:6] for row in kline_data if len(row) >= 6]
    if not normalized:
        raise ValueError("Invalid daily kline payload")

    cols = ["date", "open", "close", "high", "low", "volume"]
    df = pd.DataFrame(normalized, columns=cols)
    for col in ["open", "close", "high", "low", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd_hist = (dif - dea) * 2

    rsi6 = _calc_rsi(close, period=6)
    ma20 = close.rolling(20, min_periods=20).mean()

    return {
        "macd_hist": _to_float(macd_hist.iloc[-1]),
        "rsi6": _to_float(rsi6.iloc[-1]),
        "ma20": _to_float(ma20.iloc[-1]),
    }


def fetch_fast_panel(symbol: str) -> Dict:
    quote = fetch_realtime_quote(symbol)

    intraday_df = pd.DataFrame(columns=["time", "price", "volume_lot", "amount"])
    indicators = {"macd_hist": None, "rsi6": None, "ma20": None}
    errors = []

    try:
        intraday_df = fetch_intraday_flow(symbol)
    except Exception as exc:
        errors.append(f"intraday: {exc}")

    try:
        indicators = fetch_technical_indicators(symbol)
    except Exception as exc:
        errors.append(f"indicators: {exc}")

    if quote.get("error"):
        errors.append(f"quote: {quote['error']}")

    return {
        "symbol": symbol,
        "quote": quote,
        "indicators": indicators,
        "intraday": intraday_df,
        "order_book_10": quote.get("order_book_10", {"buy": [], "sell": []}),
        "depth_note": "公开免费接口稳定提供买5卖5；买6-买10/卖6-卖10当前显示为占位。",
        "error": " | ".join(errors) if errors else None,
    }


def run_realtime_demo(symbol: str = "601088") -> None:
    panel = fetch_fast_panel(symbol)
    quote = panel["quote"]
    print(
        f"[FastEngine] {quote.get('symbol')} {quote.get('name')} "
        f"price={quote.get('current_price')} vwap={quote.get('vwap')} "
        f"macd={panel['indicators'].get('macd_hist')} rsi6={panel['indicators'].get('rsi6')}"
    )
    print("[FastEngine] orderbook buy levels:", panel["order_book_10"].get("buy", [])[:5])


if __name__ == "__main__":
    run_realtime_demo("601088")
