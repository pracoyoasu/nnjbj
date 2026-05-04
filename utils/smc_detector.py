"""
Smart Money Concepts (SMC) detection helpers.

Implements lightweight, deterministic versions of three classic SMC tools:

* Order Blocks  — last opposing candle before a strong impulse that
                  breaks recent structure.
* Fair Value Gaps (FVG) — 3-candle imbalance where bar i-1 and bar i+1
                  do not overlap.
* Market Structure — labels the leg as BULLISH / BEARISH / NEUTRAL based
                  on the sequence of swing pivots, plus detects BOS /
                  CHoCH events.

All functions accept a Binance-style OHLCV DataFrame with columns
``time, open, high, low, close, volume`` and degrade gracefully on empty
or malformed input.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════
#  Internal — swing pivots
# ══════════════════════════════════════════════════════════════
def _swing_pivots(df: pd.DataFrame, lookback: int = 3) -> tuple[list[int], list[int]]:
    """
    Return the integer indices of swing highs and swing lows.

    A bar is a swing high if its `high` is the maximum within
    ``[i-lookback, i+lookback]`` (and similarly for lows).
    """
    highs, lows = [], []
    n = len(df)
    if n < 2 * lookback + 1:
        return highs, lows

    h = df["high"].to_numpy()
    low = df["low"].to_numpy()

    for i in range(lookback, n - lookback):
        window_h = h[i - lookback : i + lookback + 1]
        window_l = low[i - lookback : i + lookback + 1]
        if h[i] == window_h.max() and (window_h == h[i]).sum() == 1:
            highs.append(i)
        if low[i] == window_l.min() and (window_l == low[i]).sum() == 1:
            lows.append(i)

    return highs, lows


# ══════════════════════════════════════════════════════════════
#  Order Blocks
# ══════════════════════════════════════════════════════════════
def detect_orderblocks(
    df: pd.DataFrame,
    impulse_lookahead: int = 3,
    impulse_mult: float = 1.5,
    max_results: int = 10,
) -> pd.DataFrame:
    """
    Detect bullish / bearish order blocks.

    A bullish OB is the last down candle (close < open) immediately
    followed by an up impulse that closes above that candle's high
    within ``impulse_lookahead`` bars. The impulse must be larger
    than ``impulse_mult`` × the rolling-mean body.

    Returns columns: time, ob_type, ob_top, ob_bottom.
    """
    cols = ["time", "ob_type", "ob_top", "ob_bottom"]
    if df is None or df.empty or len(df) < impulse_lookahead + 2:
        return pd.DataFrame(columns=cols)

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    low = df["low"].to_numpy()
    c = df["close"].to_numpy()
    t = df["time"].to_numpy()

    body = np.abs(c - o)
    avg_body = pd.Series(body).rolling(20, min_periods=5).mean().to_numpy()

    rows = []
    n = len(df)
    last_close = c[-1]

    for i in range(n - impulse_lookahead - 1):
        avg = avg_body[i] if not np.isnan(avg_body[i]) else body[i]
        if avg <= 0:
            continue

        # Bullish OB: down candle, then impulse up breaks the high
        if c[i] < o[i]:
            window_high = h[i + 1 : i + 1 + impulse_lookahead].max()
            window_close = c[i + 1 : i + 1 + impulse_lookahead].max()
            window_body = body[i + 1 : i + 1 + impulse_lookahead].max()
            if window_close > h[i] and window_body >= impulse_mult * avg:
                # Mitigation: skip if price has since closed below the OB low.
                if c[i + 1 :].min() > low[i] * 0.999 or last_close >= low[i]:
                    rows.append({
                        "time":      pd.Timestamp(t[i]),
                        "ob_type":   "bullish",
                        "ob_top":    float(h[i]),
                        "ob_bottom": float(low[i]),
                    })
                    continue

        # Bearish OB: up candle, then impulse down breaks the low
        if c[i] > o[i]:
            window_low = low[i + 1 : i + 1 + impulse_lookahead].min()
            window_close = c[i + 1 : i + 1 + impulse_lookahead].min()
            window_body = body[i + 1 : i + 1 + impulse_lookahead].max()
            if window_close < low[i] and window_body >= impulse_mult * avg:
                if c[i + 1 :].max() < h[i] * 1.001 or last_close <= h[i]:
                    rows.append({
                        "time":      pd.Timestamp(t[i]),
                        "ob_type":   "bearish",
                        "ob_top":    float(h[i]),
                        "ob_bottom": float(low[i]),
                    })

    if not rows:
        return pd.DataFrame(columns=cols)

    out = pd.DataFrame(rows).sort_values("time", ascending=False).reset_index(drop=True)
    return out.head(max_results)


# ══════════════════════════════════════════════════════════════
#  Fair Value Gaps
# ══════════════════════════════════════════════════════════════
def detect_fvg(
    df: pd.DataFrame,
    min_size_pct: float = 0.05,
    max_results: int = 15,
) -> pd.DataFrame:
    """
    Detect unmitigated fair-value gaps (3-candle imbalance).

    Bullish FVG: low[i+1] > high[i-1]   → gap = (high[i-1], low[i+1])
    Bearish FVG: high[i+1] < low[i-1]   → gap = (high[i+1], low[i-1])

    A gap is reported only if it has not been filled by a later candle
    and exceeds ``min_size_pct`` of the gap's lower bound.

    Returns columns: time, fvg_type, fvg_top, fvg_bottom, size_pct.
    """
    cols = ["time", "fvg_type", "fvg_top", "fvg_bottom", "size_pct"]
    if df is None or df.empty or len(df) < 4:
        return pd.DataFrame(columns=cols)

    h = df["high"].to_numpy()
    low = df["low"].to_numpy()
    t = df["time"].to_numpy()

    rows = []
    n = len(df)

    for i in range(1, n - 1):
        prev_high, prev_low = h[i - 1], low[i - 1]
        next_high, next_low = h[i + 1], low[i + 1]

        # Bullish FVG
        if next_low > prev_high:
            top, bottom = next_low, prev_high
            size_pct = (top - bottom) / bottom * 100 if bottom > 0 else 0
            if size_pct < min_size_pct:
                continue
            # Mitigated if any later low has dipped into the gap
            if i + 2 < n and low[i + 2 :].min() <= bottom:
                continue
            rows.append({
                "time":       pd.Timestamp(t[i]),
                "fvg_type":   "bullish",
                "fvg_top":    float(top),
                "fvg_bottom": float(bottom),
                "size_pct":   round(float(size_pct), 3),
            })

        # Bearish FVG
        elif next_high < prev_low:
            top, bottom = prev_low, next_high
            size_pct = (top - bottom) / bottom * 100 if bottom > 0 else 0
            if size_pct < min_size_pct:
                continue
            if i + 2 < n and h[i + 2 :].max() >= top:
                continue
            rows.append({
                "time":       pd.Timestamp(t[i]),
                "fvg_type":   "bearish",
                "fvg_top":    float(top),
                "fvg_bottom": float(bottom),
                "size_pct":   round(float(size_pct), 3),
            })

    if not rows:
        return pd.DataFrame(columns=cols)

    out = pd.DataFrame(rows).sort_values("time", ascending=False).reset_index(drop=True)
    return out.head(max_results)


# ══════════════════════════════════════════════════════════════
#  Market Structure
# ══════════════════════════════════════════════════════════════
def detect_market_structure(
    df: pd.DataFrame,
    lookback: int = 3,
) -> dict:
    """
    Classify market structure based on the last few swing pivots.

    Returns a dict with:
      - bias:       BULLISH | BEARISH | WATCH LONG | WATCH SHORT | NEUTRAL
      - structure:  short label (e.g. "HH+HL", "LL+LH", "BOS Up", "CHoCH")
      - last_swing_high / last_swing_low (floats, optional)
    """
    if df is None or df.empty or len(df) < 4 * lookback:
        return {"bias": "NEUTRAL", "structure": "Insufficient data"}

    highs_idx, lows_idx = _swing_pivots(df, lookback=lookback)

    if len(highs_idx) < 2 or len(lows_idx) < 2:
        return {"bias": "NEUTRAL", "structure": "Forming"}

    h = df["high"].to_numpy()
    low = df["low"].to_numpy()
    last_close = float(df["close"].iloc[-1])

    h1, h2 = h[highs_idx[-2]], h[highs_idx[-1]]   # h2 is most recent swing high
    l1, l2 = low[lows_idx[-2]], low[lows_idx[-1]] # l2 is most recent swing low

    higher_high = h2 > h1
    higher_low  = l2 > l1
    lower_high  = h2 < h1
    lower_low   = l2 < l1

    # Break of Structure / Change of Character via the latest close
    bos_up   = last_close > h2
    bos_down = last_close < l2

    if higher_high and higher_low:
        bias = "BULLISH"
        structure = "BOS Up" if bos_up else "HH + HL"
    elif lower_high and lower_low:
        bias = "BEARISH"
        structure = "BOS Down" if bos_down else "LL + LH"
    elif higher_high and lower_low:
        bias = "WATCH LONG" if bos_up else "NEUTRAL"
        structure = "Expansion"
    elif lower_high and higher_low:
        bias = "NEUTRAL"
        structure = "Compression"
    elif bos_up:
        bias = "WATCH LONG"
        structure = "CHoCH Up"
    elif bos_down:
        bias = "WATCH SHORT"
        structure = "CHoCH Down"
    else:
        bias = "NEUTRAL"
        structure = "Range"

    return {
        "bias":             bias,
        "structure":        structure,
        "last_swing_high":  float(h2),
        "last_swing_low":   float(l2),
    }
