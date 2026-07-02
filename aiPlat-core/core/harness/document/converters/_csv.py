"""CSV converter — simple tabular text to Markdown table."""
import csv as _csv_module
import io
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)


class CsvConverter(DocumentConverter):
    """CSV → formatted table elements."""

    SOURCE_FORMAT = "csv"
    REQUIRED_PACKAGES = {}  # stdlib csv module, no external deps
    ACCEPTED_EXTENSIONS = (".csv",)
    ACCEPTED_MIME_PREFIXES = ("text/csv", "application/csv")

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
