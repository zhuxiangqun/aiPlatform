"""
Image OCR — single entry point for batch image-to-text via InfraOCRAdapter.

All OCR flows through InfraOCRAdapter (§5.31 — single model authority).
Configuration: AIPLAT_OCR_LANG (fallback: AIPLAT_VIDEO_OCR_LANG) — "eng+chi_sim".
"""

from __future__ import annotations
import logging
import os
import re
from typing import Any, Dict, List


def _env_ocr(name: str, default: str = "") -> str:
    """Resolve with migration: AIPLAT_OCR_* → AIPLAT_VIDEO_OCR_*."""
    val = os.getenv(name.replace("VIDEO_OCR_", "OCR_"), "")
    if not val:
        val = os.getenv(name, default)
    return val


def ocr_keyframes(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OCR a batch of image frames → list of {time_ms, text} via InfraOCRAdapter."""
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter
        adapter = create_adapter("ocr")
        raw = adapter.ocr_frames(frames)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
        return []

    # Quality filtering (same logic, now applied to adapter output)
    lang = _env_ocr("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim")
    out: List[Dict[str, Any]] = []
    for fr in raw:
        text = str(fr.get("ocr_text") or "").strip()
        text = " ".join(text.split())
        if len(text) < 6:
            continue
        useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))
        symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", text))
        quality = (useful / max(1, len(text))) - (symbol / max(1, len(text))) * 0.7
        if useful < max(6, len(text) // 4) or quality < 0.28:
            continue
        out.append({
            "time_ms": int(fr.get("time_ms") or 0),
            "text": text[:4000],
        })
    return out


__all__ = ["ocr_keyframes"]
