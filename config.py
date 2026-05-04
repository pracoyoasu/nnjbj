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
COINGLASS_BASE_URL = os.getenv(
    "COINGLASS_BASE_URL",
    "https://open-api-v4.coinglass.com",
)
BINANCE_BASE_URL = os.getenv(
    "BINANCE_BASE_URL",
    "https://api.binance.com",
)

# ── API keys ──────────────────────────────────────────────────
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "").strip()

# ── Default UI selections ─────────────────────────────────────
DEFAULT_SYMBOL   = "BTC"
DEFAULT_PAIR     = "BTCUSDT"
DEFAULT_TF       = "4h"
DEFAULT_EXCHANGE = "Binance"

# ── Networking ────────────────────────────────────────────────
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "10"))
