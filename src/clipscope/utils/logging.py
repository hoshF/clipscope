"""Centralized logging setup for ClipScope modules."""

from __future__ import annotations

import logging
import sys

_log_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the clipscope package.

    Called once at CLI startup. Configures a single StreamHandler
    for all sub-loggers (clipscope.*).

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR.
    """
    global _log_configured
    if _log_configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname).1s] %(message)s", datefmt="%H:%M:%S")
    )

    root = logging.getLogger("clipscope")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False

    _log_configured = True
