"""
Coinglass API Client
Endpoints: Liquidation, Long/Short Ratio, Open Interest,
           Funding Rate, Liquidation Heatmap
"""

import requests
import pandas as pd
from config import CG_BASE_URL, CG_HEADERS, BINANCE_BASE_URL


# ══════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════
def _get(endpoint: str, params: dict = None) -> dict:
    url = f"{CG_BASE_URL}{endpoint}"
    try:
        r = requests.get(url, headers=CG_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        print(f"[CoinGlass] Error: {e}")
        return {}


# ══════════════════════════════════════════════════════════════
#  1. LIQUIDATION DATA
# ══════════════════════════════════════════════════════════════
def get_liquidation_history(symbol: str = "BTC", timeframe: str = "h4", limit: int = 100) -> pd.DataFrame:
    """
    Liquidation history – jumlah long/short yang terliquid per candle.
    Timeframe: m5 | h1 | h4 | h8 | h24
    """
    data = _get("/api/futures/liquidation/v2/chart", {
        "symbol": symbol,
        "timeType": timeframe,
    })
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["t"], unit="ms")
    df = df.rename(columns={
        "longLiquidationUsd":  "long_liq_usd",
        "shortLiquidationUsd": "short_liq_usd",
    })
    df["total_liq_usd"] = df["long_liq_usd"] + df["short_liq_usd"]
    return df[["time", "long_liq_usd", "short_liq_usd", "total_liq_usd"]].tail(limit)


# ══════════════════════════════════════════════════════════════
#  2. LIQUIDATION LEVELS (harga krusial)
# ══════════════════════════════════════════════════════════════
def get_liquidation_levels(symbol: str = "BTC") -> pd.DataFrame:
    """
    Liquidation levels – kumpulan posisi yang akan terliquid pada harga tertentu.
    Berguna untuk identifikasi liquidity pool target.
    """
    data = _get("/api/futures/liquidation/detail/chart", {
        "symbol": symbol,
    })
    rows = data.get("data", {}).get("dataMap", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df


# ══════════════════════════════════════════════════════════════
#  3. LONG / SHORT RATIO
# ══════════════════════════════════════════════════════════════
def get_long_short_ratio(symbol: str = "BTC", exchange: str = "Binance",
                         timeframe: str = "h4", limit: int = 100) -> pd.DataFrame:
    """
    Long/Short account ratio – sentiment pasar.
    """
    data = _get("/api/futures/longShortRatio/chart", {
        "symbol":    symbol,
        "exchangeName": exchange,
        "timeType":  timeframe,
        "limit":     limit,
    })
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["time"]       = pd.to_datetime(df["t"], unit="ms")
    df["long_ratio"]  = df["longRatio"].astype(float)
    df["short_ratio"] = df["shortRatio"].astype(float)
    return df[["time", "long_ratio", "short_ratio"]]


# ══════════════════════════════════════════════════════════════
#  4. OPEN INTEREST
# ══════════════════════════════════════════════════════════════
def get_open_interest(symbol: str = "BTC", timeframe: str = "h4",
                      limit: int = 100) -> pd.DataFrame:
    """
    Aggregated Open Interest dari semua exchange.
    """
    data = _get("/api/futures/openInterest/chart", {
        "symbol":   symbol,
        "timeType": timeframe,
        "limit":    limit,
    })
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["t"], unit="ms")
    df["oi"]   = df["o"].astype(float)
    return df[["time", "oi"]]


# ══════════════════════════════════════════════════════════════
#  5. FUNDING RATE
# ══════════════════════════════════════════════════════════════
def get_funding_rate(symbol: str = "BTC", exchange: str = "Binance") -> dict:
    """
    Funding rate terkini.
    """
    data = _get("/api/futures/funding-rate/chart", {
        "symbol":       symbol,
        "exchangeName": exchange,
    })
    rows = data.get("data", [])
    if not rows:
        return {}

    last = rows[-1]
    return {
        "funding_rate": float(last.get("r", 0)),
        "time": pd.to_datetime(last.get("t", 0), unit="ms"),
    }


# ══════════════════════════════════════════════════════════════
#  6. LIQUIDATION MAX PAIN
# ══════════════════════════════════════════════════════════════
def get_max_pain(symbol: str = "BTC") -> dict:
    """
    Max pain price – harga di mana total kerugian trader (long+short) minimum.
    Digunakan SMC untuk menentukan target institusional.
    """
    data = _get("/api/futures/liquidation/detail/chart", {
        "symbol": symbol,
    })
    detail = data.get("data", {})
    return {
        "max_pain_price":     detail.get("maxPainPrice", None),
        "long_dominant_price":  detail.get("longDominantPrice", None),
        "short_dominant_price": detail.get("shortDominantPrice", None),
    }


# ══════════════════════════════════════════════════════════════
#  7. PRICE DATA (Binance – no key needed)
# ══════════════════════════════════════════════════════════════
def get_ohlcv(symbol: str = "BTCUSDT", interval: str = "4h",
              limit: int = 200) -> pd.DataFrame:
    """
    OHLCV dari Binance Futures – dipakai untuk deteksi OB & FVG.
    """
    url = f"{BINANCE_BASE_URL}/api/v3/klines"
    try:
        r = requests.get(url, params={
            "symbol":   symbol,
            "interval": interval,
            "limit":    limit,
        }, timeout=10)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        print(f"[Binance] Error: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(raw, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbbav","tbqav","ignore"
    ])
    df["time"]   = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    return df[["time","open","high","low","close","volume"]]
