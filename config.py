import os
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
#  API KEYS
# ──────────────────────────────────────────────
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "YOUR_COINGLASS_API_KEY")

# ──────────────────────────────────────────────
#  DEFAULT TRADING PAIR & TIMEFRAME
# ──────────────────────────────────────────────
DEFAULT_SYMBOL   = "BTC"          # BTC | ETH | dll
DEFAULT_PAIR     = "BTCUSDT"
DEFAULT_EXCHANGE = "Binance"
DEFAULT_TF       = "4h"           # 15m | 1h | 4h | 1d

# ──────────────────────────────────────────────
#  SMC SETTINGS
# ──────────────────────────────────────────────
OB_LOOKBACK      = 20   # candle lookback untuk deteksi OB
FVG_MIN_SIZE_PCT = 0.05 # minimum FVG size 0.05% dari harga

# ──────────────────────────────────────────────
#  COINGLASS ENDPOINTS
# ──────────────────────────────────────────────
CG_BASE_URL = "https://open-api.coinglass.com"
CG_HEADERS  = {
    "accept":        "application/json",
    "coinglassSecret": COINGLASS_API_KEY,
}

# ──────────────────────────────────────────────
#  BINANCE (price data, no API key needed)
# ──────────────────────────────────────────────
BINANCE_BASE_URL = "https://api.binance.com"

TIMEFRAME_MAP = {
    "15m": "15m",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1d",
}
