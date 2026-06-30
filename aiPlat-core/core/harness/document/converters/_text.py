"""Plain text fallback converter — lowest priority catch-all."""
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)


class TextConverter(DocumentConverter):
    """Catch-all converter for plain text files."""

    REQUIRED_PACKAGES = {}  # no external deps

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        return True  # Always accepts — ultimate fallback

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> List[DocumentElement]:
        data = file_stream.read()
        for enc in ("utf-8", "utf-8-sig", "latin-1", "gbk"):
            try:
                text = data.decode(enc, errors="replace")
                break
            except Exception:
                continue
        else:
            text = data.decode("utf-8", errors="ignore")

        if not text.strip():
            return []

        return [DocumentElement(
            type="text",
            text=text.strip(),
            page_idx=0,
            meta={"source": "text"},
            source_format="txt",
        )]
