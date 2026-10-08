"""
PriceSense configuration module.

Centralizes environment-based configuration using python-dotenv.
Loads variables from a local .env file (never committed) and exposes
them as typed, documented settings for the rest of the application.

Application settings are read from environment variables and the optional
project-root `.env` file.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
# This must never fail hard if the file is missing (e.g. CI, fresh clone).
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)


# --- Application metadata -------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "PriceSense")
APP_TAGLINE = os.getenv(
    "APP_TAGLINE",
    "AI Product Price History & Smart Purchase Assistant",
)

# --- Filesystem paths -------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / os.getenv("DATABASE_FILENAME", "pricesense.db")
SAMPLE_PRICES_CSV = DATA_DIR / os.getenv("SAMPLE_PRICES_FILENAME", "sample_prices.csv")

# --- Local AI explanation configuration (Phase 6) ---------------------------
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

# --- Price analytics configuration (Phase 4) --------------------------------
# All thresholds/rules used by `analytics/price_stats.py` are centralized
# here so they can be tuned without touching the analytics engine itself.

# A price is classified LOW/HIGH when it differs from the historical average
# by at least this many percentage points; otherwise it is AVERAGE.
PRICE_STATUS_LOW_THRESHOLD_PERCENT = float(
    os.getenv("PRICE_STATUS_LOW_THRESHOLD_PERCENT", "-10")
)
PRICE_STATUS_HIGH_THRESHOLD_PERCENT = float(
    os.getenv("PRICE_STATUS_HIGH_THRESHOLD_PERCENT", "10")
)
# Minimum number of observations required before a LOW/AVERAGE/HIGH status
# is computed at all; below this, the status is always INSUFFICIENT_DATA.
MIN_OBSERVATIONS_FOR_STATUS = int(os.getenv("MIN_OBSERVATIONS_FOR_STATUS", "3"))

# Number of most-recent observations averaged together for the "recent
# average" statistic. If fewer observations exist than this, the recent
# average is computed over however many are actually available.
RECENT_AVERAGE_WINDOW_SIZE = int(os.getenv("RECENT_AVERAGE_WINDOW_SIZE", "3"))

# Number of most-recent observations compared (oldest vs. newest within the
# window) to compute the recent price trend. Same shrink-to-available-data
# behavior as RECENT_AVERAGE_WINDOW_SIZE.
TREND_WINDOW_SIZE = int(os.getenv("TREND_WINDOW_SIZE", "3"))
# A trend is only reported as upward/downward if the percentage change
# across the trend window is at least this large in magnitude; smaller
# changes are reported as "stable".
TREND_STABLE_THRESHOLD_PERCENT = float(os.getenv("TREND_STABLE_THRESHOLD_PERCENT", "2"))
