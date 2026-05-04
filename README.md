# SMC Trading Dashboard

Streamlit dashboard combining **Smart Money Concepts** (Order Blocks, Fair
Value Gaps, market structure) with **Coinglass** derivatives data
(liquidations, long/short ratio, open interest, funding rate, option max
pain) on top of **Binance** spot OHLCV.

## Features

- 🕯️ Multi-pane price chart with Order Block & FVG zones
- 📐 Auto-detected market structure bias (BULLISH / BEARISH / WATCH / NEUTRAL)
- 💥 Aggregated long / short liquidation history
- ⚖️ Long / short account ratio
- 💸 Latest funding rate per exchange
- 💰 Option max-pain reference line
- 📊 Aggregated open interest

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add your Coinglass API key (optional)
streamlit run app.py
```

The Binance OHLCV feed is public — the dashboard renders even without a
Coinglass key, with Coinglass-backed panels showing `N/A` placeholders.

## Project layout

```
.
├── app.py                  # Streamlit entry-point
├── config.py               # env / endpoint / defaults
├── api/
│   └── coinglass_client.py # Coinglass v4 + Binance OHLCV client
├── utils/
│   └── smc_detector.py     # Order blocks / FVG / structure detection
├── requirements.txt
└── .env.example
```

## Disclaimer

For research and analysis only. Not financial advice. DYOR.
