#!/usr/bin/env python3
"""Lightweight smoke test wrapper (delegates to coordinator smoke)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/smoke_test.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from coordinator import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["smoke"]))
