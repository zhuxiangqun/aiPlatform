"""Video converter — extract audio via ffmpeg, transcribe via Whisper."""
import os
import tempfile
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)


class VideoConverter(DocumentConverter):
    """Video → audio extract + Whisper transcription."""

    SOURCE_FORMAT = "video"
    REQUIRED_PACKAGES = {
        # Uses core.harness.document.video (ffmpeg subprocess)
        # and core.harness.document.transcriber (Whisper via infra)
    }
    ACCEPTED_EXTENSIONS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")
    ACCEPTED_MIME_PREFIXES = ("video/",)

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
        ext = (stream_info.extension or "").lower().strip(".")
        if ext not in ("mp4", "mov", "mkv", "avi", "webm", "m4v"):
            return [DocumentElement(
                type="text", text=f"[unsupported video format: .{ext}]",
                page_idx=0, meta={"source": "video", "error": "unsupported_format"},
                source_format="video",
            )]

        if not file_path or not os.path.isfile(file_path):
            return [DocumentElement(
                type="text", text="[video file not found]", page_idx=0,
                meta={"source": "video", "error": "file_not_found"},
                source_format="video",
            )]

        try:
            from core.harness.document.video import extract_audio
            from core.harness.document.transcriber import transcribe_audio

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_path = tmp.name
            try:
                extract_audio(file_path, audio_path)
                if not os.path.isfile(audio_path) or os.path.getsize(audio_path) == 0:
                    return [DocumentElement(
                        type="text", text="[no audio track found in video]",
                        page_idx=0, meta={"source": "video"},
                        source_format="video",
                    )]
                segments = transcribe_audio(audio_path, language="zh")
                text = " ".join(s.get("text", "") for s in segments if s.get("text"))
                if text:
                    return [DocumentElement(
                        type="text", text=text, page_idx=0,
                        meta={"source": "video"},
                        source_format="video",
                        confidence=0.85,
                    )]
                return [DocumentElement(
                    type="text", text="[no speech detected in video]", page_idx=0,
                    meta={"source": "video"},
                    source_format="video",
                )]
            finally:
                if os.path.isfile(audio_path):
                    os.unlink(audio_path)
        except Exception as e:
            return [DocumentElement(
                type="text", text=f"[video transcription failed: {e}]",
                page_idx=0, meta={"source": "video", "error": str(e)},
                source_format="video",
            )]
