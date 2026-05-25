"""
Image OCR — Tesseract / PaddleOCR model inference for image-to-text.
Uses InfraOCRAdapter for unified model loading through infra.
Legacy direct pytesseract fallback retained for backward compat.

Configuration:
  AIPLAT_VIDEO_OCR_LANG — language (eng+chi_sim, chi_sim, eng, default: eng+chi_sim)
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List


def ocr_keyframes(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Prefer InfraOCRAdapter
    try:
        from core.harness.infrastructure.base_model_adapter import create_adapter
        adapter = create_adapter("ocr")
        return adapter.ocr_frames(frames)
    except Exception:
        pass

    # Legacy pytesseract direct load (fallback)
    try:
        from PIL import Image
        import pytesseract  # type: ignore  # noqa: F401
    except Exception:
        return []

    lang = str(os.getenv("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim") or "eng+chi_sim")
    out: List[Dict[str, Any]] = []
    for fr in frames:
        p = str(fr.get("local_path") or "")
        if not p:
            continue
        try:
            with Image.open(p) as img:
                text = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            continue
        text = " ".join(str(text or "").split()).strip()
        if len(text) < 6:
            continue
        useful = len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", text))
        symbol = len(re.findall(r"[^A-Za-z0-9\u4e00-\u9fff\s]", text))
        quality = (useful / max(1, len(text))) - (symbol / max(1, len(text))) * 0.7
        if useful < max(6, len(text) // 4) or quality < 0.28:
            continue
        out.append({"time_ms": int(fr.get("time_ms") or 0), "text": text[:4000]})
    return out


__all__ = ["ocr_keyframes"]
