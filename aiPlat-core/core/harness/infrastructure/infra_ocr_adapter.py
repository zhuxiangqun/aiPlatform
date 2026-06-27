"""
InfraOCRAdapter — OCR through infra model management.
Inherits BaseModelAdapter for shared model resolution + caching.
"""

from __future__ import annotations
import logging

import os
from typing import Any, Dict, List

from .base_model_adapter import BaseModelAdapter


class InfraOCRAdapter(BaseModelAdapter):
    capability = "ocr"

    def __init__(self, *, model_name: str = "", backend: str = ""):
        super().__init__(model_name=model_name)
        self._backend = backend or os.getenv("AIPLAT_VIDEO_OCR_BACKEND", "tesseract")
        self._lang = os.getenv("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim")

    def _load_model(self, name: str) -> Any:
        pass  # OCR engines loaded per-call

    def ocr_frame(self, image_path: str) -> str:
        if self._backend in ("tesseract", "auto"):
            try:
                from PIL import Image
                import pytesseract
                with Image.open(image_path) as img:
                    return pytesseract.image_to_string(img, lang=self._lang) or ""
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        if self._backend in ("paddleocr", "auto"):
            try:
                from paddleocr import PaddleOCR
                ocr = PaddleOCR(lang="ch", show_log=False)
                result = ocr.ocr(image_path)
                if result and result[0]:
                    return " ".join(line[1][0] for line in result[0])
            except Exception as e:
                logging.debug(str(e), exc_info=True)
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


def create_infra_ocr_adapter(**kwargs) -> InfraOCRAdapter:
    return InfraOCRAdapter(**kwargs)


__all__ = ["InfraOCRAdapter", "create_infra_ocr_adapter"]
