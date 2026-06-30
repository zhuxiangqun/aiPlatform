"""XLSX/XLS converter — delegates to MarkItDown."""
import os
import re
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo, detect_structure_role,
)

ACCEPTED_MIME_PREFIXES = [
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
]
ACCEPTED_EXTENSIONS = [".xlsx", ".xls"]


class XlsxConverter(DocumentConverter):
    """XLSX/XLS → Markdown via MarkItDown."""

    REQUIRED_PACKAGES = {}  # markitdown is soft dep; handled with ImportError

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        extension = (stream_info.extension or "").lower()
        if extension in ACCEPTED_EXTENSIONS:
            return True
        mimetype = (stream_info.mimetype or "").lower()
        for prefix in ACCEPTED_MIME_PREFIXES:
            if mimetype.startswith(prefix):
                return True
        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> List[DocumentElement]:
        file_path = stream_info.local_path
        if not file_path:
            return []

        try:
            from markitdown import MarkItDown
        except ImportError:
            return self._fallback_text(file_path)

        return self._convert_via_markitdown(file_path)

    def _convert_via_markitdown(self, file_path: str) -> List[DocumentElement]:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content or ""

        if not text.strip():
            return []

        sections = re.split(r"\n(?=#{1,6}\s)", text)
        elements: List[DocumentElement] = []
        for si, section in enumerate(sections):
            if section.strip():
                elements.append(DocumentElement(
                    type="text",
                    text=section.strip(),
                    page_idx=si,
                    meta={"source": "xlsx", "parser": "markitdown"},
                    source_format="xlsx",
                    structure_role=detect_structure_role(section.strip()),
                ))
        return elements or [DocumentElement(
            type="text", text=text.strip(), page_idx=0,
            meta={"source": "xlsx", "parser": "markitdown"},
            source_format="xlsx",
        )]

    def _fallback_text(self, file_path: str) -> List[DocumentElement]:
        with open(file_path, "rb") as f:
            data = f.read()
        text = data.decode("utf-8", errors="ignore")
        if not text.strip():
            return []
        return [DocumentElement(
            type="text", text=text.strip(), page_idx=0,
            meta={"source": "xlsx", "fallback": True},
            source_format="xlsx",
        )]
