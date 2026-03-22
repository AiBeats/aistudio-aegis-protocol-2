"""ABV Sovereign Stack — Logging Utilities.

Provides a consistent, structured logging setup across all modules.
Log level is controlled via the ABV_LOG_LEVEL environment variable.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional


_LOG_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized: bool = False


def _init_root_logger() -> None:
    """Configure the root ABV logger once."""
    global _initialized
    if _initialized:
        return

    level_name = os.environ.get("ABV_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger("abv")
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False

    _initialized = True


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a child logger under the ``abv`` namespace.

    Args:
        name: Dot-separated logger name (e.g. ``fortress.thermal``).
        level: Optional override for this specific logger's level.

    Returns:
        A configured :class:`logging.Logger`.
    """
    _init_root_logger()
    logger = logging.getLogger(f"abv.{name}")
    if level is not None:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger
