"""
utils/logger.py
===============
Logger reutilizable: escribe a consola Y a un archivo en logs/.
Cada módulo pide su logger con get_logger("nombre").
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, filename: str = "cryptobot.log") -> logging.Logger:
    """Devuelve un logger configurado (idempotente: no duplica handlers)."""
    logger = logging.getLogger(name)
    if logger.handlers:                      # ya estaba configurado
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    # Handler a archivo
    file_handler = logging.FileHandler(LOG_DIR / filename, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler a consola
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger.propagate = False
    return logger
