"""XLSX/XLS converter — delegates to MarkItDown."""
import os
import re
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo, detect_structure_role,
)


class XlsxConverter(DocumentConverter):
    """XLSX/XLS → Markdown via MarkItDown."""

    SOURCE_FORMAT = "xlsx"
    REQUIRED_PACKAGES = {}  # markitdown is soft dep; handled with ImportError
    ACCEPTED_EXTENSIONS = (".xlsx", ".xls")
    ACCEPTED_MIME_PREFIXES = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    )

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
        if not file_path:
            return []

        try:
            from markitdown import MarkItDown
        except ImportError:
            return self._fallback_text_from_file(file_path)

        return self._convert_via_markitdown(file_path)
