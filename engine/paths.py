"""Portable locations — works on Mac, Linux, and the original /agent layout."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    env = os.environ.get("PRIZMA_DATA")
    if env:
        return Path(env).expanduser().resolve()
    local = ROOT / "data"
    if (local / "eurojackpot_draws.csv").exists():
        return local
    sibling = ROOT.parent / "eurojackpot-data" / "data"
    if (sibling / "eurojackpot_draws.csv").exists():
        return sibling
    return local


def draws_csv() -> Path:
    return data_dir() / "eurojackpot_draws.csv"
