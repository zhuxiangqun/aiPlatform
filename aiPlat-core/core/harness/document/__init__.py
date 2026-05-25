"""
Core Document Processing Module

Provides format-agnostic document ingestion:
  parsers     — docx/pptx/markdown → text elements
  chunker     — text → overlapping/semantic/recursive chunks
  video       — video → audio + keyframes (ffmpeg wrappers)
  transcriber — audio → Whisper transcript (AI model inference)
  ocr         — image → Tesseract text (AI model inference)
"""
from .parsers import parse_docx, parse_pptx, parse_markdown
from .chunker import fixed_size_chunks, semantic_chunks, recursive_chunks, chunk_document
from .video import probe_duration_ms, extract_audio, extract_keyframes
from .transcriber import transcribe_audio
from .ocr import ocr_keyframes

__all__ = [
    "parse_docx", "parse_pptx", "parse_markdown",
    "fixed_size_chunks", "semantic_chunks", "recursive_chunks", "chunk_document",
    "probe_duration_ms", "extract_audio", "extract_keyframes",
    "transcribe_audio",
    "ocr_keyframes",
]
