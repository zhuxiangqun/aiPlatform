"""JSON document converter."""
import json as _json
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)


class JsonConverter(DocumentConverter):
    """JSON → pretty-printed text."""

    SOURCE_FORMAT = "json"
    REQUIRED_PACKAGES = {}  # stdlib json, no external deps
    ACCEPTED_EXTENSIONS = (".json",)
    ACCEPTED_MIME_PREFIXES = ("application/json",)

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
        text = data.decode("utf-8", errors="replace")
        try:
            obj = _json.loads(text)
            if isinstance(obj, list):
                text = "\n".join(_json.dumps(item, ensure_ascii=False) for item in obj[:200])
            elif isinstance(obj, dict):
                text = _json.dumps(obj, ensure_ascii=False, indent=2)
            else:
                text = str(obj)
            return [DocumentElement(
                type="text", text=text, page_idx=0,
                meta={"source": "json"},
                source_format="json",
            )]
        except Exception as e:
            return [DocumentElement(
                type="text", text=text, page_idx=0,
                meta={"source": "json", "error": str(e)},
                source_format="json",
            )]
