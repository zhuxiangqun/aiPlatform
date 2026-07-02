"""Image converter — OCR via Tesseract/PaddleOCR."""
import os
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)


class ImageConverter(DocumentConverter):
    """Image → OCR text."""

    SOURCE_FORMAT = "image"
    REQUIRED_PACKAGES = {
        # OCR through infra adapter (Tesseract/PaddleOCR)
    }
    ACCEPTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp")
    ACCEPTED_MIME_PREFIXES = ("image/",)

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        return self._accepts_by_format(stream_info)

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> List[DocumentElement]:
        file_path = stream_info.local_path
        ext = (stream_info.extension or "").lower().strip(".")
        if ext not in ("png", "jpg", "jpeg", "bmp", "tiff", "tif", "webp"):
            return [DocumentElement(
                type="text", text=f"[unsupported image format: .{ext}]",
                page_idx=0, meta={"source": "image", "error": "unsupported_format"},
                source_format="image",
            )]

        if not file_path or not os.path.isfile(file_path):
            return [DocumentElement(
                type="text", text="[image file not found]", page_idx=0,
                meta={"source": "image", "error": "file_not_found"},
                source_format="image",
            )]

        try:
            from core.harness.document.ocr import ocr_keyframes
            segments = ocr_keyframes([file_path])
            text = " ".join(s.get("text", "") for s in segments if s.get("text"))
            if text:
                return [DocumentElement(
                    type="text", text=text, page_idx=0,
                    meta={"source": "image"},
                    source_format="image",
                    confidence=0.7,
                )]
            return [DocumentElement(
                type="text", text="[no text detected]", page_idx=0,
                meta={"source": "image"},
                source_format="image",
            )]
        except Exception as e:
            return [DocumentElement(
                type="text", text=f"[image OCR failed: {e}]",
                page_idx=0, meta={"source": "image", "error": str(e)},
                source_format="image",
            )]
