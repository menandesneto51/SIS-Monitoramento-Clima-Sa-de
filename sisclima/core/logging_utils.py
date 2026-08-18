from __future__ import annotations
import logging
from pathlib import Path
from .config import ROOT, env


def get_logger(name: str = 'sisclima') -> logging.Logger:
    level = getattr(logging, (env('LOG_LEVEL','INFO') or 'INFO').upper(), logging.INFO)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    logs_dir = ROOT / 'logs'
    logs_dir.mkdir(exist_ok=True)
    fh = logging.FileHandler(logs_dir / 'sisclima.log', encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    return logger
