"""EML email converter."""
import email
from email.policy import default
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)

ACCEPTED_MIME_PREFIXES = ["message/rfc822"]
ACCEPTED_EXTENSIONS = [".eml"]


class EmlConverter(DocumentConverter):
    """EML → structured text with headers + body."""

    REQUIRED_PACKAGES = {}  # stdlib email, no external deps

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
            msg = email.message_from_string(text, policy=default)
        except Exception as e:
            return [DocumentElement(
                type="text", text=f"[email parse failed: {e}]", page_idx=0,
                meta={"source": "eml", "error": str(e)},
                source_format="eml",
            )]

        parts = [
            f"Subject: {msg.get('Subject', '(no subject)')}",
            f"From: {msg.get('From', '(unknown)')}",
            f"Date: {msg.get('Date', '(unknown)')}",
        ]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body += payload.decode("utf-8", errors="replace") + "\n"
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        if body.strip():
            parts.append(f"\nBody:\n{body.strip()}")

        return [DocumentElement(
            type="text", text="\n".join(parts), page_idx=0,
            meta={"source": "eml"},
            source_format="eml",
        )]
