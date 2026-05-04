"""
Thin client around Coinglass v4 (futures / options data) and Binance public
spot OHLCV. All functions return tidy pandas DataFrames or plain dicts so
the dashboard can consume them directly.

Every call is wrapped in defensive error handling: a network or auth failure
returns an *empty* DataFrame / dict rather than raising, so the dashboard
keeps rendering with N/A placeholders.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import requests

from config import (
    BINANCE_BASE_URL,
    COINGLASS_API_KEY,
    COINGLASS_BASE_URL,
    HTTP_TIMEOUT,
)


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════
def _cg_headers() -> dict[str, str]:
    return {
        "accept": "application/json",
        "CG-API-KEY": COINGLASS_API_KEY,
    }


def _cg_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a Coinglass endpoint. Returns the parsed JSON envelope or {}."""
    url = f"{COINGLASS_BASE_URL.rstrip('/')}{path}"
    try:
        r = requests.get(
            url,
            headers=_cg_headers(),
            params=params or {},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        return r.json() or {}
    except Exception:
        return {}


def _cg_data(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Coinglass wraps results under `data`. Normalise to a list."""
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Some endpoints nest the list one level deeper.
        for key in ("list", "items", "result", "data"):
            inner = data.get(key)
            if isinstance(inner, list):
                return inner
        return [data]
    return []


def _ms_to_dt(series: pd.Series) -> pd.Series:
    """Coinglass timestamps come in milliseconds."""
    return pd.to_datetime(pd.to_numeric(series, errors="coerce"), unit="ms")


# ══════════════════════════════════════════════════════════════
#  Binance OHLCV  (public, no key required)
# ══════════════════════════════════════════════════════════════
def get_ohlcv(pair: str, tf: str, limit: int = 200) -> pd.DataFrame:
    """
    Fetch spot OHLCV from Binance.

    Returns columns: time, open, high, low, close, volume.
    """
    url = f"{BINANCE_BASE_URL.rstrip('/')}/api/v3/klines"
    params = {"symbol": pair.upper(), "interval": tf, "limit": int(limit)}
    try:
        r = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        rows = r.json()
    except Exception:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    if not rows:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(
        rows,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_base", "taker_quote", "ignore",
        ],
    )
    df["time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["time", "open", "high", "low", "close", "volume"]].dropna().reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Coinglass — Liquidation history (aggregated)
# ══════════════════════════════════════════════════════════════
def get_liquidation_history(symbol: str, cg_tf: str, limit: int = 200) -> pd.DataFrame:
    """
    Aggregated long/short liquidation per interval.

    Returns columns: time, long_liq_usd, short_liq_usd.
    """
    payload = _cg_get(
        "/api/futures/liquidation/aggregated-history",
        {"symbol": symbol.upper(), "interval": cg_tf, "limit": int(limit)},
    )
    rows = _cg_data(payload)
    if not rows:
        return pd.DataFrame(columns=["time", "long_liq_usd", "short_liq_usd"])

    df = pd.DataFrame(rows)

    ts_col = next((c for c in ("time", "t", "timestamp", "ts") if c in df.columns), None)
    long_col = next(
        (c for c in ("longLiquidationUsd", "long_liquidation_usd",
                     "longLiqUsd", "long_liq_usd", "longVolUsd") if c in df.columns),
        None,
    )
    short_col = next(
        (c for c in ("shortLiquidationUsd", "short_liquidation_usd",
                     "shortLiqUsd", "short_liq_usd", "shortVolUsd") if c in df.columns),
        None,
    )
    if ts_col is None or long_col is None or short_col is None:
        return pd.DataFrame(columns=["time", "long_liq_usd", "short_liq_usd"])

    out = pd.DataFrame({
        "time":           _ms_to_dt(df[ts_col]),
        "long_liq_usd":   pd.to_numeric(df[long_col],  errors="coerce").fillna(0),
        "short_liq_usd": pd.to_numeric(df[short_col], errors="coerce").fillna(0),
    })
    return out.dropna(subset=["time"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Coinglass — Long/Short account ratio
# ══════════════════════════════════════════════════════════════
def get_long_short_ratio(
    symbol: str, exchange: str, cg_tf: str, limit: int = 200,
) -> pd.DataFrame:
    """
    Long / short account ratio (per-exchange).

    Returns columns: time, long_ratio (%), short_ratio (%).
    """
    payload = _cg_get(
        "/api/futures/global-long-short-account-ratio/history",
        {
            "symbol":   symbol.upper(),
            "exchange": exchange,
            "interval": cg_tf,
            "limit":    int(limit),
        },
    )
    rows = _cg_data(payload)
    if not rows:
        return pd.DataFrame(columns=["time", "long_ratio", "short_ratio"])

    df = pd.DataFrame(rows)
    ts_col = next((c for c in ("time", "t", "timestamp", "ts") if c in df.columns), None)
    long_col = next(
        (c for c in ("longAccount", "long_account", "longRatio", "long_ratio") if c in df.columns),
        None,
    )
    short_col = next(
        (c for c in ("shortAccount", "short_account", "shortRatio", "short_ratio") if c in df.columns),
        None,
    )
    if ts_col is None or long_col is None or short_col is None:
        return pd.DataFrame(columns=["time", "long_ratio", "short_ratio"])

    longs  = pd.to_numeric(df[long_col],  errors="coerce")
    shorts = pd.to_numeric(df[short_col], errors="coerce")

    # Some endpoints return ratios as 0..1 — promote to percentage.
    if longs.dropna().between(0, 1).all() and shorts.dropna().between(0, 1).all():
        longs  = longs * 100
        shorts = shorts * 100

    out = pd.DataFrame({
        "time":        _ms_to_dt(df[ts_col]),
        "long_ratio":  longs.fillna(0),
        "short_ratio": shorts.fillna(0),
    })
    return out.dropna(subset=["time"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Coinglass — Open interest (aggregated)
# ══════════════════════════════════════════════════════════════
def get_open_interest(symbol: str, cg_tf: str, limit: int = 200) -> pd.DataFrame:
    """
    Aggregated open interest history.

    Returns columns: time, oi (USD).
    """
    payload = _cg_get(
        "/api/futures/open-interest/aggregated-history",
        {"symbol": symbol.upper(), "interval": cg_tf, "limit": int(limit)},
    )
    rows = _cg_data(payload)
    if not rows:
        return pd.DataFrame(columns=["time", "oi"])

    df = pd.DataFrame(rows)
    ts_col = next((c for c in ("time", "t", "timestamp", "ts") if c in df.columns), None)
    oi_col = next(
        (c for c in ("close", "openInterest", "open_interest", "oi", "value") if c in df.columns),
        None,
    )
    if ts_col is None or oi_col is None:
        return pd.DataFrame(columns=["time", "oi"])

    out = pd.DataFrame({
        "time": _ms_to_dt(df[ts_col]),
        "oi":   pd.to_numeric(df[oi_col], errors="coerce").fillna(0),
    })
    return out.dropna(subset=["time"]).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════
#  Coinglass — Funding rate (latest, per exchange)
# ══════════════════════════════════════════════════════════════
def get_funding_rate(symbol: str, exchange: str = "Binance") -> dict[str, Any]:
    """
    Latest funding rate. Returns {"funding_rate": float, "exchange": str} or {}.
    """
    payload = _cg_get(
        "/api/futures/funding-rate/exchange-list",
        {"symbol": symbol.upper()},
    )
    rows = _cg_data(payload)
    if not rows:
        return {}

    target = exchange.lower()
    for entry in rows:
        ex = str(entry.get("exchangeName", entry.get("exchange", ""))).lower()
        if ex != target:
            continue
        rate = entry.get("fundingRate", entry.get("funding_rate"))
        if rate is None:
            # Some payloads nest inside `usdtMargin` / `tokenMargin` lists.
            for k in ("usdtMargin", "tokenMargin"):
                inner = entry.get(k)
                if isinstance(inner, list) and inner:
                    rate = inner[0].get("fundingRate")
                    break
        try:
            return {"funding_rate": float(rate), "exchange": exchange}
        except (TypeError, ValueError):
            return {}

    # Fallback: take the first row.
    first = rows[0]
    rate = first.get("fundingRate", first.get("funding_rate"))
    try:
        return {"funding_rate": float(rate), "exchange": first.get("exchangeName", "")}
    except (TypeError, ValueError):
        return {}


# ══════════════════════════════════════════════════════════════
#  Coinglass — Option max pain
# ══════════════════════════════════════════════════════════════
def get_max_pain(symbol: str) -> dict[str, Any]:
    """
    Latest option max-pain price for the nearest expiry.

    Returns {"max_pain_price": float, "expiry": str} or {}.
    """
    payload = _cg_get(
        "/api/option/max-pain",
        {"symbol": symbol.upper()},
    )
    rows = _cg_data(payload)
    if not rows:
        return {}

    first = rows[0]
    price = first.get("maxPainPrice", first.get("max_pain_price"))
    try:
        return {
            "max_pain_price": float(price),
            "expiry": first.get("expiryDate", first.get("expiry", "")),
        }
    except (TypeError, ValueError):
        return {}
