"""HTML converter — delegates to MarkItDown."""
import os
import re
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo, detect_structure_role,
)


class HtmlConverter(DocumentConverter):
    """HTML → Markdown via MarkItDown."""

    SOURCE_FORMAT = "html"
    REQUIRED_PACKAGES = {}  # markitdown + beautifulsoup4 are soft deps
    ACCEPTED_EXTENSIONS = (".html", ".htm")
    ACCEPTED_MIME_PREFIXES = ("text/html", "application/xhtml")

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
            return self._convert_stream_html(file_stream, stream_info)

        try:
            from markitdown import MarkItDown
        except ImportError:
            return self._fallback_text_from_file(file_path)

        return self._convert_via_markitdown(file_path)

    def _convert_stream_html(self, file_stream: BinaryIO, stream_info: StreamInfo) -> List[DocumentElement]:
        data = file_stream.read()
        text = data.decode("utf-8", errors="ignore")
        if not text.strip():
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            body = soup.get_text("\n", strip=True)
            return [DocumentElement(
                type="text", text=body, page_idx=0,
                meta={"source": "html", "parser": "beautifulsoup"},
                source_format="html",
            )]
        except ImportError:
            return [DocumentElement(
                type="text", text=text.strip(), page_idx=0,
                meta={"source": "html", "fallback": True},
                source_format="html",
            )]
