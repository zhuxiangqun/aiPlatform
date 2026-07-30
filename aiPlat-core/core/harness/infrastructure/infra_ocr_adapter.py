"""
InfraOCRAdapter — Unified OCR entry point for all text-recognition needs.
 
All OCR in the system must flow through this adapter (§5.31 — single model authority).
Direct ``import pytesseract`` or ``import paddleocr`` outside this file is forbidden.

Capabilities:
  - ocr_text(image_path) → str                          plain text (Tesseract or PaddleOCR)
  - ocr_structured(image_path) → List[OCRToken]          bbox + confidence (both backends)
  - ocr_pdf(pdf_path) → str                              PDF → render pages → OCR text
  - ocr_frames(frames) → List[Dict]                     batch processing (video keyframes)

Backend selection: AIPLAT_OCR_BACKEND (fallback: AIPLAT_VIDEO_OCR_BACKEND) — "tesseract"|"paddleocr"|"auto"
Language:         AIPLAT_OCR_LANG   (fallback: AIPLAT_VIDEO_OCR_LANG)   — "eng+chi_sim"
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .base_model_adapter import BaseModelAdapter

# ── OCRToken: structured OCR result (bbox + confidence) ──

BBox = Tuple[int, int, int, int]  # x1, y1, x2, y2 in pixels


@dataclass
class OCRToken:
    """Single OCR result with bounding box and confidence score."""
    text: str
    bbox: BBox
    conf: float = 0.0


# ── Thread-safe PaddleOCR instance cache ──

_PADDLE_OCR_LOCK = threading.RLock()
_PADDLE_OCR_CACHE: dict[str, object] = {}


def _get_paddle_ocr(*, lang: str = "ch") -> object:
    """Return a cached PaddleOCR instance. Keyed by lang ('ch'/'en')."""
    with _PADDLE_OCR_LOCK:
        if lang in _PADDLE_OCR_CACHE:
            return _PADDLE_OCR_CACHE[lang]
        from paddleocr import PaddleOCR  # type: ignore
        ocr = PaddleOCR(use_angle_cls=True, lang=lang)
        _PADDLE_OCR_CACHE[lang] = ocr
        return ocr


def _bbox_from_poly(poly) -> BBox:
    xs = [int(p[0]) for p in poly]
    ys = [int(p[1]) for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


# ── Env var resolution (new names, backward compat) ──

def _env_ocr(name: str, default: str = "") -> str:
    """Resolve env var with migration path: AIPLAT_OCR_* → AIPLAT_VIDEO_OCR_*."""
    new_key = name.replace("VIDEO_OCR_", "OCR_")
    val = os.getenv(new_key, "")
    if not val:
        val = os.getenv(name, default)
    return val


class InfraOCRAdapter(BaseModelAdapter):
    """Unified OCR adapter — the SINGLE entry point for all OCR in the system.
    
    Supports Tesseract and PaddleOCR backends, structured output with bbox,
    PDF→OCR pipeline, and thread-safe PaddleOCR instance caching.
    """

    capability = "ocr"

    def __init__(self, *, model_name: str = "", backend: str = ""):
        super().__init__(model_name=model_name)
        self._backend = backend or _env_ocr("AIPLAT_VIDEO_OCR_BACKEND", "tesseract")
        self._lang = _env_ocr("AIPLAT_VIDEO_OCR_LANG", "eng+chi_sim")

    def _load_model(self, name: str) -> Any:
        pass  # OCR engines loaded per-call / cached

    # ── Plain text OCR (existing, renamed + caching fix) ──

    def ocr_text(self, image_path: str) -> str:
        """OCR a single image → plain text string. Alias for ocr_frame()."""
        return self.ocr_frame(image_path)

    def ocr_frame(self, image_path: str) -> str:
        """OCR a single image → plain text string (video keyframe compatible)."""
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
                ocr = _get_paddle_ocr(lang="ch"
                    if self._lang.lower().startswith("zh") else "en")
                result = ocr.ocr(image_path)
                if result and result[0]:
                    return " ".join(
                        line[1][0] for line in result[0] if line[1][0]
                    )
            except Exception as e:
                logging.debug(str(e), exc_info=True)
        return ""

    # ── Structured OCR (bbox + confidence) ──

    def ocr_structured(self, image_path: str) -> List[OCRToken]:
        """OCR a single image → List[OCRToken] with bbox coordinates and confidence.
        
        PaddleOCR: polygon → bbox, per-line confidence.
        Tesseract: word-level image_to_data, bbox + confidence.
        """
        if self._backend in ("paddleocr", "auto"):
            try:
                ocr_lang = ("ch" if self._lang.lower().startswith("zh")
                            or self._lang.lower() in ("ch", "cn") else "en")
                ocr = _get_paddle_ocr(lang=ocr_lang)
                res = getattr(ocr, "ocr")(image_path) or []
                # Normalize PaddleOCR output format (single vs batch)
                lines: list = []
                if isinstance(res, list) and res:
                    if isinstance(res[0], list) and len(res[0]) == 2:
                        lines = res
                    elif isinstance(res[0], list):
                        lines = res[0]
                tokens: List[OCRToken] = []
                for line in lines:
                    try:
                        poly = line[0]
                        txt = str(line[1][0] or "").strip()
                        conf = float(line[1][1] or 0.0)
                        if not txt:
                            continue
                        tokens.append(OCRToken(
                            text=txt, bbox=_bbox_from_poly(poly), conf=conf))
                    except Exception:
                        continue
                if tokens:
                    return tokens
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        if self._backend in ("tesseract", "auto"):
            try:
                from PIL import Image
                import pytesseract
                lang_code = ("chi_sim+eng"
                             if self._lang.lower().startswith("zh") else "eng")
                img = Image.open(image_path)
                data = pytesseract.image_to_data(
                    img, lang=lang_code,
                    config="--psm 6 -c preserve_interword_spaces=1",
                    output_type=pytesseract.Output.DICT,
                )
                tokens: List[OCRToken] = []
                n = len(data.get("text") or [])
                for i in range(n):
                    txt = str((data.get("text") or [""])[i] or "").strip()
                    if not txt:
                        continue
                    try:
                        conf = float((data.get("conf") or ["0"])[i] or 0.0) / 100.0
                    except Exception:
                        conf = 0.0
                    try:
                        x = int((data.get("left") or [0])[i])
                        y = int((data.get("top") or [0])[i])
                        w = int((data.get("width") or [0])[i])
                        h = int((data.get("height") or [0])[i])
                        bbox: BBox = (x, y, x + w, y + h)
                    except Exception:
                        bbox = (0, 0, 0, 0)
                    tokens.append(OCRToken(text=txt, bbox=bbox, conf=conf))
                return tokens
            except Exception as e:
                logging.debug(str(e), exc_info=True)

        return []

    # ── PDF → OCR pipeline ──

    def ocr_pdf(self, pdf_path: str, *, dpi: int = 200) -> str:
        """OCR a PDF (scanned or digital) → plain text.
        
        Digital PDFs: native text extraction (fast path).
        Scanned PDFs: render each page as PNG → ocr_frame().
        """
        try:
            import fitz  # type: ignore  # PyMuPDF
        except ImportError:
            logging.debug("PyMuPDF not available for PDF OCR")
            return ""

        doc = fitz.open(pdf_path)
        page_count = doc.page_count

        # Fast path: native text
        native_texts = [p.get_text().strip() for p in doc]
        if any(t for t in native_texts):
            doc.close()
            return "\n\n".join(native_texts)

        # Scanned PDF: render + OCR
        texts: List[str] = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img_path = os.path.join(
                os.path.dirname(pdf_path) or "/tmp",
                f"_ocr_page_{page.number}.png"
            )
            pix.save(img_path)
            texts.append(self.ocr_frame(img_path))
            try:
                os.remove(img_path)
            except OSError:
                pass  # noqa: cleanup-best-effort
        doc.close()
        return "\n\n".join(texts)

    # ── Batch processing (video keyframes, etc.) ──

    def ocr_frames(self, frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OCR a batch of images — enriches each frame dict with ocr_text + ocr_engine."""
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


__all__ = [
    "InfraOCRAdapter", "create_infra_ocr_adapter",
    "OCRToken", "BBox",
]

