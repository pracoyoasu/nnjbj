"""
Application configuration.

Loads API keys from environment (or a local .env file when python-dotenv
is installed) and exposes default symbols / endpoints used across the app.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ── API endpoints ─────────────────────────────────────────────
CG_BASE_URL = os.getenv(
    "COINGLASS_BASE_URL",
    "https://open-api-v4.coinglass.com",
)
BINANCE_BASE_URL = os.getenv(
    "BINANCE_BASE_URL",
    "https://api.binance.com",
)

# ── API keys / headers ────────────────────────────────────────
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "").strip()

CG_HEADERS = {
    "accept": "application/json",
    "CG-API-KEY": COINGLASS_API_KEY,
}

# ── Default UI selections ─────────────────────────────────────
DEFAULT_SYMBOL   = "BTC"
DEFAULT_PAIR     = "BTCUSDT"
DEFAULT_TF       = "4h"
DEFAULT_EXCHANGE = "Binance"
