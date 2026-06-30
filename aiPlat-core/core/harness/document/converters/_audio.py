"""Audio converter — Whisper transcription."""
import os
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)

ACCEPTED_MIME_PREFIXES = ["audio/"]
ACCEPTED_EXTENSIONS = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".wma"]


class AudioConverter(DocumentConverter):
    """Audio → Whisper transcription."""

    REQUIRED_PACKAGES = {
        # Transcribed through infra adapter (faster-whisper or openai-whisper)
    }

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
        ext = (stream_info.extension or "").lower().strip(".")
        if ext not in ("mp3", "wav", "m4a", "ogg", "flac", "aac", "opus", "wma"):
            return [DocumentElement(
                type="text", text=f"[unsupported audio format: .{ext}]",
                page_idx=0, meta={"source": "audio", "error": "unsupported_format"},
                source_format="audio",
            )]

        if not file_path or not os.path.isfile(file_path):
            return [DocumentElement(
                type="text", text="[audio file not found]", page_idx=0,
                meta={"source": "audio", "error": "file_not_found"},
                source_format="audio",
            )]

        try:
            from core.harness.document.transcriber import transcribe_audio
            segments = transcribe_audio(file_path, language="zh")
            text = " ".join(s.get("text", "") for s in segments if s.get("text"))
            if text:
                return [DocumentElement(
                    type="text", text=text, page_idx=0,
                    meta={"source": "audio"},
                    source_format="audio",
                    confidence=0.85,
                )]
            return [DocumentElement(
                type="text", text="[no speech detected]", page_idx=0,
                meta={"source": "audio"},
                source_format="audio",
            )]
        except Exception as e:
            return [DocumentElement(
                type="text", text=f"[audio transcription failed: {e}]",
                page_idx=0, meta={"source": "audio", "error": str(e)},
                source_format="audio",
            )]
