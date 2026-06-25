"""Shared project path constants for ClipScope."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = PROJECT_ROOT / "app"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
DATA_DIR = PROJECT_ROOT / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
COMMENTS_DIR = DATA_DIR / "comments"
TRACKING_DIR = DATA_DIR / "tracking"
LOGS_DIR = DATA_DIR / "logs"
TEMP_DIR = DATA_DIR / "temp"
LIB_DIR = PROJECT_ROOT / "lib"
COOKIES_DIR = PROJECT_ROOT / "cookies"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def ensure_project_paths(include_lib: bool = True) -> None:
    """Add project paths needed by standalone scripts to sys.path."""
    paths = [PROJECT_ROOT, SCRIPTS_DIR]
    if include_lib:
        paths.append(LIB_DIR)

    for path in paths:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
