"""
Model quality feedback — 闭环模型质量评估。

Usage:
  from core.harness.routing.model_feedback import record_model_quality

  # After auto-fill completes + audit runs:
  record_model_quality("qwen2.5-coder:7b", "agent_creation", audit_issues)

How it works:
  1. Compute raw quality score from audit issues
  2. Apply exponential moving average (alpha=0.3)
  3. Persist to ~/.aiplat/model_quality/{model_name}_{purpose}.json
  4. ModelManager.select_by_purpose() reads quality_scores during scoring
"""

from __future__ import annotations
import logging

import json as _json
import os as _os
from pathlib import Path as _Path
from typing import Any, Dict, List


def _quality_dir() -> _Path:
    d = _Path(_os.getenv("AIPLAT_HOME", _Path.home() / ".aiplat")) / "model_quality"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _quality_path(model_name: str, purpose: str) -> _Path:
    safe_name = model_name.replace("/", "_").replace(":", "_")
    return _quality_dir() / f"{safe_name}_{purpose}.json"


def _read_quality(model_name: str, purpose: str) -> float:
    p = _quality_path(model_name, purpose)
    if not p.exists():
        return 0.0
    try:
        data = _json.loads(p.read_text())
        return float(data.get("quality", 0.0))
    except Exception:
        return 0.0


def _write_quality(model_name: str, purpose: str, quality: float, samples: int = 1) -> None:
    p = _quality_path(model_name, purpose)
    data = {
        "model_name": model_name,
        "purpose": purpose,
        "quality": round(quality, 4),
        "samples": samples,
        "last_updated": int(__import__("time").time()),
    }
    p.write_text(_json.dumps(data, ensure_ascii=False, indent=2))


def compute_raw_quality(audit_issues: List[Dict[str, Any]]) -> float:
    """Compute raw quality score from audit issues (0.0 ~ 1.0).
    
    Weights (configurable, not hardcoded for specific categories):
      - severity=error:    0.4 penalty
      - severity=warning:  0.2 penalty
      - severity=info:     0.05 penalty
    """
    penalty = 0.0
    for issue in audit_issues:
        sev = str(issue.get("severity", "")).lower()
        if sev == "error":
            penalty += 0.4
        elif sev == "warning":
            penalty += 0.2
        elif sev == "info":
            penalty += 0.05
    raw = max(0.0, 1.0 - penalty)
    return raw


def raw_to_normalized(raw: float) -> float:
    """Convert raw quality (0-1) to normalized score (-1 to 1).
    
    0.5 = neutral → 0.0
    1.0 = perfect → +1.0
    0.0 = worst   → -1.0
    """
    sign = 1.0 if raw >= 0.5 else -1.0
    return sign * abs(raw - 0.5) * 2.0


def record_model_quality(model_name: str, purpose: str, audit_issues: List[Dict[str, Any]]) -> float:
    """Record model quality feedback from audit results.
    
    Uses exponential moving average: new = old * 0.7 + fresh * 0.3
    Returns the new quality score.
    """
    if not model_name or not purpose:
        return 0.0
    
    raw = compute_raw_quality(audit_issues)
    normalized = raw_to_normalized(raw)
    
    old = _read_quality(model_name, purpose)
    new = max(-1.0, min(1.0, old * 0.7 + normalized * 0.3))
    
    # Count samples
    p = _quality_path(model_name, purpose)
    samples = 1
    if p.exists():
        try:
            old_data = _json.loads(p.read_text())
            samples = old_data.get("samples", 0) + 1
        except Exception as e:
            logging.debug(str(e), exc_info=True)
    
    _write_quality(model_name, purpose, new, samples)
    return new
