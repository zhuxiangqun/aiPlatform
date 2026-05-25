"""
InfraOCRAdapter — bridges core OCR to infra model management.

Wraps pytesseract / PaddleOCR through a managed adapter
consistent with other infra adapters.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


class InfraOCRAdapter:
    """OCR adapter through infra model management."""

    def __init__(self, *, backend: str = ""):
        self._backend = backend or os.getenv("AIPLAT_VIDEO_OCR_BACKEND", "tesseract")
        self._lang = os.getenv("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim")

    def ocr_frame(self, image_path: str) -> str:
        if self._backend in ("tesseract", "auto"):
            try:
                from PIL import Image
                import pytesseract
                with Image.open(image_path) as img:
                    return pytesseract.image_to_string(img, lang=self._lang) or ""
            except Exception:
                pass

        if self._backend in ("paddleocr", "auto"):
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(lang="ch", show_log=False)
                result = ocr.ocr(image_path)
                if result and result[0]:
                    return " ".join(line[1][0] for line in result[0])
            except Exception:
                pass

        return ""

    def ocr_frames(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for fr in frames:
            p = str(fr.get("local_path") or "")
            if not p:
                continue
            text = self.ocr_frame(p)
            if text.strip():
                out.append({**fr, "ocr_text": text, "ocr_engine": self._backend})
        return out


def create_infra_ocr_adapter() -> InfraOCRAdapter:
    return InfraOCRAdapter()


__all__ = ["InfraOCRAdapter", "create_infra_ocr_adapter"]
