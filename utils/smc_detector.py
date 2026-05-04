"""
SMC Detector
Deteksi: Orderblock (Bullish/Bearish) & Fair Value Gap (FVG)
Input  : DataFrame OHLCV dari Binance
"""

import pandas as pd
import numpy as np
from config import OB_LOOKBACK, FVG_MIN_SIZE_PCT


# ══════════════════════════════════════════════════════════════
#  SWING HIGH / LOW  (struktur dasar SMC)
# ══════════════════════════════════════════════════════════════
def detect_swing_points(df: pd.DataFrame, swing_len: int = 5) -> pd.DataFrame:
    """
    Tandai swing high & swing low.
    swing_high = candle dengan high tertinggi dalam window [i-n, i+n]
    swing_low  = candle dengan low terendah dalam window [i-n, i+n]
    """
    df = df.copy()
    df["swing_high"] = False
    df["swing_low"]  = False

    for i in range(swing_len, len(df) - swing_len):
        window_high = df["high"].iloc[i - swing_len: i + swing_len + 1]
        window_low  = df["low"].iloc[i - swing_len: i + swing_len + 1]

        if df["high"].iloc[i] == window_high.max():
            df.at[df.index[i], "swing_high"] = True
        if df["low"].iloc[i] == window_low.min():
            df.at[df.index[i], "swing_low"]  = True

    return df


# ══════════════════════════════════════════════════════════════
#  ORDERBLOCK DETECTION
# ══════════════════════════════════════════════════════════════
def detect_orderblocks(df: pd.DataFrame, lookback: int = OB_LOOKBACK) -> pd.DataFrame:
    """
    Bearish OB : candle bullish terakhir sebelum impulse bearish yang menembus swing low
    Bullish OB : candle bearish terakhir sebelum impulse bullish yang menembus swing high

    Returns DataFrame dengan kolom tambahan:
      ob_type   : 'bullish' | 'bearish' | None
      ob_top    : harga atas OB
      ob_bottom : harga bawah OB
      ob_valid  : apakah OB belum temitigasi (harga belum masuk kembali)
    """
    df = df.copy().reset_index(drop=True)
    df["ob_type"]   = None
    df["ob_top"]    = np.nan
    df["ob_bottom"] = np.nan
    df["ob_valid"]  = False

    current_price = df["close"].iloc[-1]

    for i in range(2, len(df) - 1):
        # ── Bearish OB ───────────────────────────────────────
        # Kondisi: candle i bullish, candle i+1 bearish kuat
        #          body candle i+1 menembus low candle i-1
        if (
            df["close"].iloc[i]   > df["open"].iloc[i]   and   # candle i bullish
            df["close"].iloc[i+1] < df["open"].iloc[i+1] and   # candle i+1 bearish
            df["close"].iloc[i+1] < df["low"].iloc[i-1]        # tembus ke bawah
        ):
            ob_top    = df["high"].iloc[i]
            ob_bottom = df["open"].iloc[i]          # body OB
            valid     = current_price < ob_top      # belum masuk OB dari bawah

            df.at[i, "ob_type"]   = "bearish"
            df.at[i, "ob_top"]    = ob_top
            df.at[i, "ob_bottom"] = ob_bottom
            df.at[i, "ob_valid"]  = valid

        # ── Bullish OB ───────────────────────────────────────
        # Kondisi: candle i bearish, candle i+1 bullish kuat
        #          body candle i+1 menembus high candle i-1
        elif (
            df["close"].iloc[i]   < df["open"].iloc[i]   and   # candle i bearish
            df["close"].iloc[i+1] > df["open"].iloc[i+1] and   # candle i+1 bullish
            df["close"].iloc[i+1] > df["high"].iloc[i-1]       # tembus ke atas
        ):
            ob_top    = df["open"].iloc[i]          # body OB
            ob_bottom = df["low"].iloc[i]
            valid     = current_price > ob_bottom   # belum masuk OB dari atas

            df.at[i, "ob_type"]   = "bullish"
            df.at[i, "ob_top"]    = ob_top
            df.at[i, "ob_bottom"] = ob_bottom
            df.at[i, "ob_valid"]  = valid

    # Ambil OB valid saja, lookback candle terakhir
    ob_df = df[
        (df["ob_type"].notna()) &
        (df["ob_valid"] == True)
    ].tail(lookback)[["time","ob_type","ob_top","ob_bottom","ob_valid"]]

    return ob_df


# ══════════════════════════════════════════════════════════════
#  FAIR VALUE GAP (FVG)
# ══════════════════════════════════════════════════════════════
def detect_fvg(df: pd.DataFrame, min_size_pct: float = FVG_MIN_SIZE_PCT) -> pd.DataFrame:
    """
    FVG terjadi ketika ada gap antara:
      Bullish FVG : high candle [i-1] < low candle [i+1]  → gap naik (demand zone)
      Bearish FVG : low candle [i-1]  > high candle [i+1] → gap turun (supply zone)

    min_size_pct : minimum gap size sebagai % dari harga (filter noise)
    """
    df = df.copy().reset_index(drop=True)
    fvg_list = []
    current_price = df["close"].iloc[-1]

    for i in range(1, len(df) - 1):
        mid_price = df["close"].iloc[i]

        # ── Bullish FVG ──────────────────────────────────────
        gap_top    = df["low"].iloc[i + 1]
        gap_bottom = df["high"].iloc[i - 1]
        if gap_top > gap_bottom:
            size_pct = (gap_top - gap_bottom) / mid_price * 100
            if size_pct >= min_size_pct:
                # Mitigated jika harga sudah masuk ke dalam gap
                mitigated = current_price <= gap_top
                fvg_list.append({
                    "time":      df["time"].iloc[i],
                    "fvg_type":  "bullish",
                    "fvg_top":   gap_top,
                    "fvg_bottom": gap_bottom,
                    "size_pct":  round(size_pct, 3),
                    "mitigated": mitigated,
                })

        # ── Bearish FVG ──────────────────────────────────────
        gap_top    = df["low"].iloc[i - 1]
        gap_bottom = df["high"].iloc[i + 1]
        if gap_top > gap_bottom:
            size_pct = (gap_top - gap_bottom) / mid_price * 100
            if size_pct >= min_size_pct:
                mitigated = current_price >= gap_bottom
                fvg_list.append({
                    "time":      df["time"].iloc[i],
                    "fvg_type":  "bearish",
                    "fvg_top":   gap_top,
                    "fvg_bottom": gap_bottom,
                    "size_pct":  round(size_pct, 3),
                    "mitigated": mitigated,
                })

    fvg_df = pd.DataFrame(fvg_list)
    if fvg_df.empty:
        return fvg_df

    # Kembalikan FVG yang belum termitigasi
    return fvg_df[fvg_df["mitigated"] == False].tail(20)


# ══════════════════════════════════════════════════════════════
#  MARKET STRUCTURE (CHoCH & BOS)
# ══════════════════════════════════════════════════════════════
def detect_market_structure(df: pd.DataFrame) -> dict:
    """
    Deteksi sederhana:
      BOS  (Break of Structure) – konfirmasi trend
      CHoCH (Change of Character) – sinyal reversal
    """
    df = detect_swing_points(df.copy())
    highs = df[df["swing_high"]]["high"].values
    lows  = df[df["swing_low"]]["low"].values

    if len(highs) < 2 or len(lows) < 2:
        return {"structure": "INSUFFICIENT DATA", "bias": "NEUTRAL"}

    hh = highs[-1] > highs[-2]   # Higher High
    lh = highs[-1] < highs[-2]   # Lower High
    hl = lows[-1]  > lows[-2]    # Higher Low
    ll = lows[-1]  < lows[-2]    # Lower Low

    if hh and hl:
        structure = "BOS BULLISH"
        bias      = "BULLISH"
    elif ll and lh:
        structure = "BOS BEARISH"
        bias      = "BEARISH"
    elif lh and hl:
        structure = "CHoCH → Potential Bullish Reversal"
        bias      = "WATCH LONG"
    elif hh and ll:
        structure = "CHoCH → Potential Bearish Reversal"
        bias      = "WATCH SHORT"
    else:
        structure = "RANGING / CONSOLIDATION"
        bias      = "NEUTRAL"

    return {
        "structure": structure,
        "bias":      bias,
        "last_hh":   float(highs[-1]),
        "last_ll":   float(lows[-1]),
    }
