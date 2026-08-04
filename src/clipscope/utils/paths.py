"""Shared project path constants for ClipScope."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
COMMENTS_DIR = DATA_DIR / "comments"
TRACKING_DIR = DATA_DIR / "tracking"
LOGS_DIR = DATA_DIR / "logs"
TEMP_DIR = DATA_DIR / "temp"
COOKIES_DIR = PROJECT_ROOT / "cookies"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
