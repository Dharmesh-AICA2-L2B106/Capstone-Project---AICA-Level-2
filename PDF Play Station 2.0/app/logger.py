"""Logging to logs\\pdf_play_station.log next to the application (rotated, kept local).

Logs record what was done and any errors; they never contain document text or
passwords."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
# [EXE build, change 2] A one-file EXE runs from a temporary folder that is deleted on
# exit, so the log goes to the user's own application-data folder instead.
if getattr(sys, "frozen", False):
    LOG_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "PDF Play Station 2.0" / "logs"


def setup() -> logging.Logger:
    log = logging.getLogger("pps")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(name)s: %(message)s")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(LOG_DIR / "pdf_play_station.log", maxBytes=2_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass                                   # read-only folder: run without a log file
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        log.addHandler(sh)

    def excepthook(kind, value, tb):
        log.critical("Unhandled error", exc_info=(kind, value, tb))
        sys.__excepthook__(kind, value, tb)
    sys.excepthook = excepthook
    return log
