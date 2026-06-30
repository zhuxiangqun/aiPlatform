"""JSON document converter."""
import json as _json
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)

ACCEPTED_MIME_PREFIXES = ["application/json"]
ACCEPTED_EXTENSIONS = [".json"]


class JsonConverter(DocumentConverter):
    """JSON → pretty-printed text."""

    REQUIRED_PACKAGES = {}  # stdlib json, no external deps

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
