"""
Core Document Processing Module

Provides format-agnostic document ingestion:
  protocol   — DocumentConverter ABC + ConverterRegistry (single source of truth)
  converters — per-format converter implementations
  parsers    — thin wrappers delegating to registry (backward compatible)
  chunker    — text → overlapping/semantic/recursive chunks
  video      — video → audio + keyframes (ffmpeg wrappers)
  transcriber — audio → Whisper transcript (AI model inference)
  ocr        — image → Tesseract text (AI model inference)
"""
from .protocol import (
    DocumentConverter,
    DocumentElement,
    ConverterRegistry,
    get_document_registry,
    StreamInfo,
    FileConversionException,
    UnsupportedFormatException,
    MissingDependencyException,
    PRIORITY_SPECIFIC_FORMAT,
    PRIORITY_GENERIC_FORMAT,
)
from .parsers import (
    parse_docx, parse_pptx, parse_markdown, parse_csv,
    parse_audio, parse_image, parse_json_document, parse_eml,
    parse_markitdown, parse_html,
    extract_images_from_document, describe_images,
)
from .chunker import fixed_size_chunks, semantic_chunks, recursive_chunks, chunk_document
from .video import probe_duration_ms, extract_audio, extract_keyframes
from .transcriber import transcribe_audio
from .ocr import ocr_keyframes

__all__ = [
    # Protocol + Registry
    "DocumentConverter", "DocumentElement", "ConverterRegistry",
    "get_document_registry", "StreamInfo",
    "FileConversionException", "UnsupportedFormatException",
    "MissingDependencyException",
    "PRIORITY_SPECIFIC_FORMAT", "PRIORITY_GENERIC_FORMAT",
    # Parsers (backward compatible)
    "parse_docx", "parse_pptx", "parse_markdown", "parse_csv",
    "parse_audio", "parse_image", "parse_json_document", "parse_eml",
    "parse_markitdown", "parse_html",
    "extract_images_from_document", "describe_images",
    # Chunking
    "fixed_size_chunks", "semantic_chunks", "recursive_chunks", "chunk_document",
    # Media
    "probe_duration_ms", "extract_audio", "extract_keyframes",
    "transcribe_audio",
    "ocr_keyframes",
]
