"""
Centralized configuration loaded from environment variables.

All env-var access in the application must go through this module.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DATABASE_URL: str = os.environ["DATABASE_URL"]

# --- Rust core bridge ---
RUST_CORE_URL: str = os.getenv("RUST_CORE_URL", "http://rust_core:8001")

# --- Bybit ---
BYBIT_API_KEY: str = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
BYBIT_BASE_URL: str = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

# --- eAssets scraper ---
EASSETS_EMAIL: str = os.getenv("EASSETS_EMAIL", "")
EASSETS_PASSWORD: str = os.getenv("EASSETS_PASSWORD", "")
EASSETS_INTERVAL_SECONDS: int = int(os.getenv("EASSETS_INTERVAL_SECONDS", "1800"))
EASSETS_AUTO_ENABLED: bool = os.getenv("EASSETS_AUTO_ENABLED", "1") == "1"
EASSETS_HEADLESS: bool = os.getenv("EASSETS_HEADLESS", "1") == "1"
EASSETS_TIMEOUT_MS: int = int(os.getenv("EASSETS_TIMEOUT_MS", "240000"))
