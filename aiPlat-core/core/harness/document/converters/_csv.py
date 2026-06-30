"""CSV converter — simple tabular text to Markdown table."""
import csv as _csv_module
import io
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)

ACCEPTED_MIME_PREFIXES = ["text/csv", "application/csv"]
ACCEPTED_EXTENSIONS = [".csv"]


class CsvConverter(DocumentConverter):
    """CSV → formatted table elements."""

    REQUIRED_PACKAGES = {}  # stdlib csv module, no external deps

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
        data = file_stream.read()
        content = None
        for enc in ("utf-8", "utf-8-sig", "latin-1", "gbk"):
            try:
                content = data.decode(enc, errors="replace")
                break
            except Exception:
                continue
        if content is None:
            return []

        rows = [[c.strip() for c in row] for row in _csv_module.reader(content.splitlines())]
        if not rows:
            return []

        texts = [" | ".join(r) for r in rows]
        return [DocumentElement(
            type="table",
            text="\n".join(texts),
            page_idx=0,
            cells=rows,
            meta={"source": "csv", "rows": len(rows)},
            source_format="csv",
        )]
