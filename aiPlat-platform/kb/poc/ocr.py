"""OCR delegation layer — delegates to InfraOCRAdapter (single model authority).

All OCR in the system flows through ``InfraOCRAdapter`` (§5.31).
This module exists for backward compatibility with existing callers
that expect the old ``ocr_image()`` + ``choose_best_ocr_engine()`` API.

Do NOT add new OCR logic here. Add it to ``InfraOCRAdapter`` instead.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from core.harness.infrastructure.infra_ocr_adapter import (
    BBox,
    OCRToken,
    create_infra_ocr_adapter,
)


def ocr_image(
    image_path: str,
    *,
    engine: Literal["paddleocr", "tesseract"] = "paddleocr",
    ocr_engine: Optional[str] = None,
    lang: str = "ch",
    **_kwargs,
) -> List[OCRToken]:
    """OCR a single image → List[OCRToken] with bbox.

    Delegates to ``InfraOCRAdapter.ocr_structured()``.
    """
    backend = (ocr_engine or engine or "paddleocr").strip().lower()
    # Map legacy lang to adapter lang
    adapter_lang = "chi_sim" if lang.lower().startswith("zh") else "eng"
    adapter = create_infra_ocr_adapter(backend=backend, model_name=adapter_lang)
    return adapter.ocr_structured(image_path)


def choose_best_ocr_engine() -> str:
    """Return the best available OCR engine.
    
    Probes InfraOCRAdapter — Tesseract first, then PaddleOCR fallback.
    No direct model imports.
    """
    try:
        adapter = create_infra_ocr_adapter(backend="paddleocr")
        return "paddleocr"
    except Exception:
        return "tesseract"
