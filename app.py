"""
SMC Trading Dashboard
Powered by: Coinglass API + Binance OHLCV + Smart Money Concepts Engine
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os

sys.path.append(os.path.dirname(__file__))

from config import DEFAULT_SYMBOL, DEFAULT_PAIR, DEFAULT_TF
from api.coinglass_client import (
    get_ohlcv, get_liquidation_history, get_long_short_ratio,
    get_open_interest, get_funding_rate, get_max_pain,
)
from utils.smc_detector import detect_orderblocks, detect_fvg, detect_market_structure


# ══════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="SMC Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background: #1e2130;
        border-radius: 8px;
        padding: 12px 16px;
        border-left: 3px solid #00d4aa;
    }
    .bearish { border-left-color: #ff4b4b; }
    .bullish { border-left-color: #00d4aa; }
    .neutral { border-left-color: #ffd700; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("⚙️ Settings")
    symbol   = st.selectbox("Symbol", ["BTC", "ETH", "SOL", "BNB"], index=0)
    pair     = f"{symbol}USDT"
    exchange = st.selectbox("Exchange", ["Binance", "OKX", "Bybit"], index=0)
    tf       = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=2)
    limit    = st.slider("Candles", 50, 500, 200, 50)

    # CG timeframe mapping
    cg_tf_map = {"15m": "m15", "1h": "h1", "4h": "h4", "1d": "h24"}
    cg_tf = cg_tf_map.get(tf, "h4")

    st.divider()
    refresh = st.button("🔄 Refresh Data", use_container_width=True)
    st.caption("Data: Coinglass + Binance")


# ══════════════════════════════════════════════════════════════
#  LOAD DATA  (cached 60s)
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=60)
def load_all(symbol, pair, exchange, tf, cg_tf, limit):
    df_ohlcv = get_ohlcv(pair, tf, limit)
    df_liq   = get_liquidation_history(symbol, cg_tf, limit)
    df_ls    = get_long_short_ratio(symbol, exchange, cg_tf, limit)
    df_oi    = get_open_interest(symbol, cg_tf, limit)
    funding  = get_funding_rate(symbol, exchange)
    max_pain = get_max_pain(symbol)
    return df_ohlcv, df_liq, df_ls, df_oi, funding, max_pain

if refresh:
    st.cache_data.clear()

df_ohlcv, df_liq, df_ls, df_oi, funding, max_pain = load_all(
    symbol, pair, exchange, tf, cg_tf, limit
)


# ══════════════════════════════════════════════════════════════
#  SMC ANALYSIS
# ══════════════════════════════════════════════════════════════
ob_df       = detect_orderblocks(df_ohlcv) if not df_ohlcv.empty else pd.DataFrame()
fvg_df      = detect_fvg(df_ohlcv)          if not df_ohlcv.empty else pd.DataFrame()
ms          = detect_market_structure(df_ohlcv) if not df_ohlcv.empty else {}

current_price = df_ohlcv["close"].iloc[-1] if not df_ohlcv.empty else 0


# ══════════════════════════════════════════════════════════════
#  HEADER
# ══════════════════════════════════════════════════════════════
st.title(f"📊 SMC Dashboard — {pair} / {tf.upper()}")

bias = ms.get("bias", "NEUTRAL")
bias_color = {"BULLISH": "🟢", "BEARISH": "🔴", "WATCH LONG": "🟡",
              "WATCH SHORT": "🟠", "NEUTRAL": "⚪"}.get(bias, "⚪")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("💲 Current Price",  f"${current_price:,.2f}")
col2.metric("📐 Structure",      f"{bias_color} {bias}")
col3.metric("💰 Max Pain",       f"${float(max_pain.get('max_pain_price') or 0):,.0f}" if max_pain.get("max_pain_price") else "N/A")
col4.metric("💸 Funding Rate",   f"{funding.get('funding_rate', 0)*100:.4f}%" if funding else "N/A")
col5.metric("🔥 Market Bias",    ms.get("structure", "N/A"))


st.divider()


# ══════════════════════════════════════════════════════════════
#  MAIN CHART — OHLCV + OB + FVG
# ══════════════════════════════════════════════════════════════
st.subheader("🕯️ Price Chart + Orderblocks + FVG")

if not df_ohlcv.empty:
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.6, 0.2, 0.2],
        vertical_spacing=0.03,
        subplot_titles=["Price + SMC Levels", "Volume", "Open Interest"],
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_ohlcv["time"], open=df_ohlcv["open"],
        high=df_ohlcv["high"], low=df_ohlcv["low"], close=df_ohlcv["close"],
        name="Price",
        increasing_line_color="#00d4aa",
        decreasing_line_color="#ff4b4b",
    ), row=1, col=1)

    # ── Orderblocks ──────────────────────────────────────────
    for _, ob in ob_df.iterrows():
        color = "rgba(0,212,170,0.15)" if ob["ob_type"] == "bullish" else "rgba(255,75,75,0.15)"
        border = "#00d4aa" if ob["ob_type"] == "bullish" else "#ff4b4b"
        label  = f"{'🟢 Bullish OB' if ob['ob_type'] == 'bullish' else '🔴 Bearish OB'}"

        fig.add_hrect(
            y0=ob["ob_bottom"], y1=ob["ob_top"],
            fillcolor=color, line_color=border, line_width=1,
            annotation_text=label, annotation_position="top right",
            row=1, col=1,
        )

    # ── Fair Value Gaps ───────────────────────────────────────
    for _, fvg in fvg_df.iterrows():
        color = "rgba(0,150,255,0.10)" if fvg["fvg_type"] == "bullish" else "rgba(255,165,0,0.10)"
        border = "#0096ff" if fvg["fvg_type"] == "bullish" else "#ffa500"
        label  = f"FVG {fvg['size_pct']}%"

        fig.add_hrect(
            y0=fvg["fvg_bottom"], y1=fvg["fvg_top"],
            fillcolor=color, line_color=border, line_width=0.5,
            line_dash="dot",
            annotation_text=label, annotation_position="top left",
            row=1, col=1,
        )

    # Max Pain line
    mp = max_pain.get("max_pain_price")
    if mp:
        fig.add_hline(y=float(mp), line_dash="dash", line_color="#ffd700",
                      annotation_text=f"Max Pain ${float(mp):,.0f}",
                      row=1, col=1)

    # Volume
    vol_colors = ["#00d4aa" if c >= o else "#ff4b4b"
                  for c, o in zip(df_ohlcv["close"], df_ohlcv["open"])]
    fig.add_trace(go.Bar(
        x=df_ohlcv["time"], y=df_ohlcv["volume"],
        marker_color=vol_colors, name="Volume", showlegend=False,
    ), row=2, col=1)

    # Open Interest
    if not df_oi.empty:
        fig.add_trace(go.Scatter(
            x=df_oi["time"], y=df_oi["oi"],
            fill="tozeroy", line_color="#7b68ee",
            name="Open Interest", fillcolor="rgba(123,104,238,0.15)",
        ), row=3, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=700,
        xaxis_rangeslider_visible=False,
        showlegend=True,
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ OHLCV data tidak tersedia. Periksa koneksi / API key.")


# ══════════════════════════════════════════════════════════════
#  ROW 2 — LIQUIDATION + LONG/SHORT
# ══════════════════════════════════════════════════════════════
col_a, col_b = st.columns(2)

# ── Liquidation Chart ─────────────────────────────────────────
with col_a:
    st.subheader("💥 Liquidation History")
    if not df_liq.empty:
        fig_liq = go.Figure()
        fig_liq.add_trace(go.Bar(
            x=df_liq["time"], y=df_liq["long_liq_usd"] / 1e6,
            name="Long Liq (M$)", marker_color="#ff4b4b",
        ))
        fig_liq.add_trace(go.Bar(
            x=df_liq["time"], y=df_liq["short_liq_usd"] / 1e6,
            name="Short Liq (M$)", marker_color="#00d4aa",
        ))
        fig_liq.update_layout(
            template="plotly_dark", height=280,
            barmode="overlay", margin=dict(l=0,r=0,t=10,b=0),
            yaxis_title="USD (Millions)",
        )
        st.plotly_chart(fig_liq, use_container_width=True)
    else:
        st.info("Liquidation data tidak tersedia.")

# ── Long / Short Ratio ────────────────────────────────────────
with col_b:
    st.subheader("⚖️ Long / Short Ratio")
    if not df_ls.empty:
        fig_ls = go.Figure()
        fig_ls.add_trace(go.Scatter(
            x=df_ls["time"], y=df_ls["long_ratio"],
            fill="tozeroy", name="Long %",
            line_color="#00d4aa", fillcolor="rgba(0,212,170,0.2)",
        ))
        fig_ls.add_trace(go.Scatter(
            x=df_ls["time"], y=df_ls["short_ratio"],
            fill="tozeroy", name="Short %",
            line_color="#ff4b4b", fillcolor="rgba(255,75,75,0.2)",
        ))
        fig_ls.add_hline(y=50, line_dash="dash", line_color="white", opacity=0.3)
        fig_ls.update_layout(
            template="plotly_dark", height=280,
            margin=dict(l=0,r=0,t=10,b=0),
            yaxis_title="Ratio (%)",
        )
        st.plotly_chart(fig_ls, use_container_width=True)
    else:
        st.info("Long/Short data tidak tersedia.")


# ══════════════════════════════════════════════════════════════
#  ROW 3 — OB TABLE + FVG TABLE
# ══════════════════════════════════════════════════════════════
col_c, col_d = st.columns(2)

with col_c:
    st.subheader("🧱 Active Orderblocks")
    if not ob_df.empty:
        display_ob = ob_df.copy()
        display_ob["distance_%"] = ((display_ob["ob_top"] + display_ob["ob_bottom"]) / 2
                                     - current_price) / current_price * 100
        display_ob["distance_%"] = display_ob["distance_%"].round(2)
        display_ob["ob_top"]    = display_ob["ob_top"].round(2)
        display_ob["ob_bottom"] = display_ob["ob_bottom"].round(2)

        def color_ob(row):
            if row["ob_type"] == "bullish":
                return ["background-color: rgba(0,212,170,0.1)"] * len(row)
            return ["background-color: rgba(255,75,75,0.1)"] * len(row)

        st.dataframe(
            display_ob[["time","ob_type","ob_top","ob_bottom","distance_%"]]
            .style.apply(color_ob, axis=1),
            use_container_width=True, height=250,
        )
    else:
        st.info("Tidak ada OB aktif terdeteksi.")

with col_d:
    st.subheader("🌌 Fair Value Gaps (Unmitigated)")
    if not fvg_df.empty:
        display_fvg = fvg_df.copy()
        display_fvg["distance_%"] = ((display_fvg["fvg_top"] + display_fvg["fvg_bottom"]) / 2
                                      - current_price) / current_price * 100
        display_fvg["distance_%"] = display_fvg["distance_%"].round(2)
        display_fvg["fvg_top"]    = display_fvg["fvg_top"].round(2)
        display_fvg["fvg_bottom"] = display_fvg["fvg_bottom"].round(2)

        def color_fvg(row):
            if row["fvg_type"] == "bullish":
                return ["background-color: rgba(0,150,255,0.1)"] * len(row)
            return ["background-color: rgba(255,165,0,0.1)"] * len(row)

        st.dataframe(
            display_fvg[["time","fvg_type","fvg_top","fvg_bottom","size_pct","distance_%"]]
            .style.apply(color_fvg, axis=1),
            use_container_width=True, height=250,
        )
    else:
        st.info("Tidak ada FVG aktif terdeteksi.")


# ══════════════════════════════════════════════════════════════
#  FOOTER
# ══════════════════════════════════════════════════════════════
st.divider()
st.caption("⚠️ Dashboard ini hanya untuk analisis — bukan financial advice. DYOR.")
