"""Crawler config loader with user-override support.

Loading order:
  1. crawler_configs/{platform}/{subdir}/config.yaml  (user cookie overrides)
  2. src/clipscope/crawler/{platform}/{subdir}/config.yaml  (default template)

Nested dicts are deep-merged so the override only needs to specify
the fields it changes (typically just Cookie).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from clipscope.utils.paths import PROJECT_ROOT

CONFIG_OVERRIDE_DIR = Path(str(PROJECT_ROOT)) / "crawler_configs"

PACKAGE_DIR = Path(__file__).resolve().parents[1]


def load_crawler_config(platform: str, subdir: str = "web") -> dict:
    default_path = PACKAGE_DIR / "crawler" / platform / subdir / "config.yaml"
    override_path = CONFIG_OVERRIDE_DIR / platform / subdir / "config.yaml"

    config: dict = {}
    if os.path.exists(default_path):
        with open(default_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    if os.path.exists(override_path):
        with open(override_path, encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
        if override:
            _deep_merge(config, override)

    return config


def _deep_merge(base: dict, override: dict) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
