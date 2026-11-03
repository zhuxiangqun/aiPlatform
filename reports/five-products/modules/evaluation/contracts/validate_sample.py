#!/usr/bin/env python3
"""Shim — EVAL contracts SSOT is packages/aiplat-evaluation/contracts/ (ARCH v1.3)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_PKG = (
    Path(__file__).resolve().parents[5]
    / "packages"
    / "aiplat-evaluation"
    / "contracts"
    / "validate_sample.py"
)
if not _PKG.is_file():
    raise SystemExit(f"FAIL missing contracts SSOT: {_PKG}")
ns = runpy.run_path(str(_PKG), run_name="aiplat_eval_contracts_shim")
sys.exit(int(ns["main"]()))
