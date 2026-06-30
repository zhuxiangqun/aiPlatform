"""
Document Converter Protocol & Registry — unified document format → text elements.

Inspired by markitdown's DocumentConverter design:
  - Each converter implements accepts() + convert()
  - Registry provides priority-based dispatch with fallback chain
  - All dispatch points reference this single registry (no duplicated hardcoded dicts)

Public API:
  - get_document_registry() → ConverterRegistry (global singleton)
  - registry.find_converter(stream_info) → optional converter
  - registry.get_supported_categories() → list[str] (single source of truth)

Callers:
  - core/api/core_facade.py   (via registry, not hardcoded dict)
  - core/api/facades/kb_facade.py (via registry)
  - platform/kb/service.py    (via registry)
  - platform/api/rest/routes.py (via registry)
"""
from __future__ import annotations

import logging
import os
import sys
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Dict, List, Optional, Type


# ── StreamInfo: file metadata for dispatch decisions ──

# File header signatures for content-based format detection
_FILE_SIGNATURES = [
    (b"%PDF-", ".pdf"),
    (b"PK\x03\x04", None),  # ZIP-based (DOCX/PPTX/XLSX) — needs filename check
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".doc"),  # OLE2 (old DOC/PPT/XLS)
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF89a", ".gif"),
    (b"GIF87a", ".gif"),
    (b"RIFF", ".wav"),  # Also AVI — check sub-type
    (b"ID3", ".mp3"),
    (b"\xff\xfb", ".mp3"),
    (b"fLaC", ".flac"),
    (b"OggS", ".ogg"),
    (b"<!DOCTYPE html", ".html"),
    (b"<html", ".html"),
    (b"From:", ".eml"),
    (b"Return-Path:", ".eml"),
    (b"Date:", ".eml"),
]


def _guess_extension_from_header(data: bytes) -> Optional[str]:
    """Guess file extension from binary header magic bytes."""
    for magic, ext in _FILE_SIGNATURES:
        if data[:len(magic)] == magic:
            return ext
    return None


def _guess_zip_subtype(filename: str, data: bytes) -> Optional[str]:
    """For ZIP-based files (DOCX/PPTX/XLSX), guess subtype from filename or content."""
    if data[:4] != b"PK\x03\x04":
        return None
    fn = filename.lower()
    if ".docx" in fn or ".doc" in fn:
        return ".docx"
    if ".pptx" in fn or ".ppt" in fn:
        return ".pptx"
    if ".xlsx" in fn or ".xls" in fn:
        return ".xlsx"
    # Check internal ZIP structure
    if b"word/" in data[:4096]:
        return ".docx"
    if b"ppt/" in data[:4096]:
        return ".pptx"
    if b"xl/" in data[:4096]:
        return ".xlsx"
    return None

@dataclass
class StreamInfo:
    """Metadata about a file/stream used for converter dispatch.
    
    Designed to be extended with magika-based content detection (Phase 1.3).
    """
    extension: Optional[str] = None
    mimetype: Optional[str] = None
    charset: Optional[str] = None
    filename: Optional[str] = None
    local_path: Optional[str] = None
    url: Optional[str] = None

    def copy_and_update(self, **kwargs: Any) -> "StreamInfo":
        """Immutable update helper (functional pattern from markitdown)."""
        d = {
            "extension": self.extension,
            "mimetype": self.mimetype,
            "charset": self.charset,
            "filename": self.filename,
            "local_path": self.local_path,
            "url": self.url,
        }
        d.update(kwargs)
        return StreamInfo(**d)


# ── DocumentElement: unified output format ──

@dataclass
class DocumentElement:
    """Single parsed element from a document.
    
    Fields preserved from existing parsers.py format:
      type: "text" | "table" | "heading" | "image"
      text: text content
      page_idx: page/segment index (0-based)
      cells: 2D cell array for tables
    
    Fields added for enhanced downstream strategy selection (Phase 3):
      source_format: original document format (e.g. "pdf", "docx")
      structure_role: heading level / caption / list_item
      confidence: OCR/ASR confidence 0-1
    """
    type: str = "text"
    text: str = ""
    page_idx: int = 0
    cells: Optional[List[List[str]]] = None
    meta: Dict[str, Any] = field(default_factory=dict)
    source_format: str = ""
    structure_role: str = ""
    confidence: float = 1.0


# ── Converter Protocol ──

class DocumentConverter(ABC):
    """Convert a specific file format to a list of DocumentElements.
    
    Each converter must implement:
      accepts(stream, stream_info, **kwargs) → bool  — can this converter handle this file?
      convert(stream, stream_info, **kwargs) → List[DocumentElement]  — do the conversion
    
    Converter lifecycle in the registry:
      1. accepts() checked → if True, convert() called
      2. If convert() raises → exception collected, next converter tried
      3. If no converter succeeds → FileConversionException raised (aggregated errors)
    """

    # Dependency declarations for centralized management (Phase 1.2)
    REQUIRED_PACKAGES: Dict[str, str] = {}  # {package_name: pip_install_spec}

    @classmethod
    def check_dependencies(cls) -> bool:
        """Verify all REQUIRED_PACKAGES are importable. Returns True if all satisfied."""
        for pkg in cls.REQUIRED_PACKAGES:
            try:
                __import__(pkg)
            except ImportError:
                return False
        return True

    @abstractmethod
    def accepts(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> bool:
        """Return True if this converter can handle the given file.
        
        MUST NOT change the file_stream position.
        """
        ...

    @abstractmethod
    def convert(self, file_stream: BinaryIO, stream_info: StreamInfo, **kwargs: Any) -> List[DocumentElement]:
        """Parse the file and return a list of DocumentElements.
        
        May advance file_stream position; registry will seek back after failure.
        """
        ...

    @property
    def name(self) -> str:
        return type(self).__name__


# ── Converter Registration ──

@dataclass(kw_only=True, frozen=True)
class ConverterRegistration:
    """A registered converter with its priority."""
    converter: DocumentConverter
    priority: float = 0.0  # lower = tried first


# ── Exceptions ──

class DocumentConverterException(Exception):
    """Base exception for document conversion failures."""
    pass


class MissingDependencyException(DocumentConverterException):
    """A converter's required packages are not installed."""
    pass


@dataclass
class FailedConversionAttempt:
    """Record of a single converter failure."""
    converter: DocumentConverter
    exc_type: Type[BaseException]
    exc_value: BaseException
    exc_traceback: Any


class FileConversionException(DocumentConverterException):
    """All converters failed for this file."""
    def __init__(self, attempts: List[FailedConversionAttempt]):
        self.attempts = attempts
        msgs = []
        for a in attempts:
            msgs.append(f"  {a.converter.name}: {a.exc_type.__name__}: {a.exc_value}")
        super().__init__("File conversion failed with all converters:\n" + "\n".join(msgs))


class UnsupportedFormatException(DocumentConverterException):
    """No converter accepted this file format."""
    pass


# ── Converter Registry ──

# Priority constants (lower = tried first, same as markitdown)
PRIORITY_SPECIFIC_FORMAT = 0.0   # e.g., .docx, .pdf, .xlsx — format-specific converters
PRIORITY_GENERIC_FORMAT = 10.0   # e.g., plain text — catch-all converters


class ConverterRegistry:
    """Central registry for document converters.
    
    SINGLE SOURCE OF TRUTH for:
      - Which converters are available
      - Which formats are supported
      - Priority-based dispatch order
      - Fallback chain on failure
    
    Usage:
        registry = get_document_registry()
        registry.register(MyConverter(), priority=0.0)
        
        stream_info = StreamInfo(extension=".pdf")
        converter = registry.find_converter(stream_info)
        if converter:
            elements = converter.convert(file_stream, stream_info)
    """

    def __init__(self):
        self._registrations: List[ConverterRegistration] = []

    def register(
        self,
        converter: DocumentConverter,
        *,
        priority: float = PRIORITY_SPECIFIC_FORMAT,
    ) -> None:
        """Register a converter. Later registrations with same priority are tried first."""
        self._registrations.insert(
            0, ConverterRegistration(converter=converter, priority=priority)
        )

    def _sorted_registrations(self) -> List[ConverterRegistration]:
        """Return registrations sorted by priority (lower = first), stable sort."""
        return sorted(self._registrations, key=lambda x: x.priority)

    def find_converter(
        self,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> Optional[DocumentConverter]:
        """Find the first available converter that accepts this file.
        
        Checks converters in priority order. Returns None if no converter accepts.
        
        Enhanced with content-based detection: if stream_info has a local_path,
        reads file header to validate extension and uses multi-guess resolution.
        """
        guesses = self._generate_guesses(stream_info)
        for guess_info in guesses:
            for reg in self._sorted_registrations():
                conv = reg.converter
                _accepts = False
                try:
                    _accepts = self._check_accepts_metadata(conv, guess_info)
                except NotImplementedError:
                    pass
                if _accepts and conv.check_dependencies():
                    return conv
        return None

    def _generate_guesses(self, stream_info: StreamInfo) -> List[StreamInfo]:
        """Generate ordered stream info guesses: validated extension first, then fallbacks.
        
        Strategy:
          1. If file header confirms the extension → use extension info
          2. If file header contradicts extension → try content-based first, then extension
          3. If no file header match → use extension info as-is
        """
        guesses = [stream_info]
        
        if stream_info.local_path is None:
            return guesses
        
        try:
            with open(stream_info.local_path, "rb") as f:
                header = f.read(64)
        except (IOError, OSError):
            return guesses
        
        content_ext = _guess_extension_from_header(header)
        if content_ext is None and header[:4] == b"PK\x03\x04":
            content_ext = _guess_zip_subtype(
                stream_info.filename or os.path.basename(stream_info.local_path),
                header,
            )
        
        if content_ext and content_ext != stream_info.extension:
            # Content contradicts extension — try content-based first
            content_info = stream_info.copy_and_update(extension=content_ext)
            guesses = [content_info, stream_info]
            logging.debug(
                "Content-based detection: header=%s, extension=%s",
                content_ext, stream_info.extension,
            )
        
        return guesses

    def find_all_converters(
        self,
        stream_info: StreamInfo,
    ) -> List[DocumentConverter]:
        """Return all converters that accept this file, sorted by priority."""
        result = []
        for reg in self._sorted_registrations():
            conv = reg.converter
            _accepts = False
            try:
                _accepts = self._check_accepts_metadata(conv, stream_info)
            except NotImplementedError:
                pass
            if _accepts:
                result.append(conv)
        return result

    @staticmethod
    def _check_accepts_metadata(
        converter: DocumentConverter,
        stream_info: StreamInfo,
    ) -> bool:
        """Check accepts() using metadata only (no stream).
        
        Returns True if converter.accepts() is implemented and accepts the metadata.
        If accepts() requires a stream (raises NotImplementedError), returns False.
        """
        try:
            return converter.accepts(None, stream_info)  # type: ignore[arg-type]
        except NotImplementedError:
            return False
        except Exception:
            return False

    def convert_with_fallback(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> List[DocumentElement]:
        """Convert a file stream with full fallback chain.
        
        Tries all accepting converters in priority order. Each failure is collected.
        If no converter succeeds, raises FileConversionException with all failures.
        
        Args:
            file_stream: A seekable binary stream positioned at the start.
            stream_info: File metadata for dispatch.
            **kwargs: Passed through to converter.convert().
        
        Returns:
            List of DocumentElements from the first successful converter.
        
        Raises:
            FileConversionException: All converters failed.
            UnsupportedFormatException: No converter accepted the format.
        """
        res: Optional[List[DocumentElement]] = None
        failed_attempts: List[FailedConversionAttempt] = []
        cur_pos = file_stream.tell()

        for reg in self._sorted_registrations():
            conv = reg.converter

            # Check if converter is available (dependencies)
            if not conv.check_dependencies():
                continue

            # Check if converter accepts this file
            _accepts = False
            try:
                _accepts = conv.accepts(file_stream, stream_info, **kwargs)
            except NotImplementedError:
                pass

            assert (
                cur_pos == file_stream.tell()
            ), f"{conv.name}.accepts() changed stream position!"

            if _accepts:
                try:
                    res = conv.convert(file_stream, stream_info, **kwargs)
                except Exception:
                    failed_attempts.append(
                        FailedConversionAttempt(
                            converter=conv,
                            exc_type=type(sys.exc_info()[1]),
                            exc_value=sys.exc_info()[1],  # type: ignore[arg-type]
                            exc_traceback=sys.exc_info()[2],
                        )
                    )
                    logging.debug(
                        "Converter %s failed: %s",
                        conv.name,
                        traceback.format_exc(),
                    )
                finally:
                    file_stream.seek(cur_pos)

                if res is not None and len(res) > 0:
                    return res
                elif res is not None:
                    # Empty result — try next converter
                    continue

        if failed_attempts:
            raise FileConversionException(attempts=failed_attempts)

        raise UnsupportedFormatException(
            f"No converter accepted file: ext={stream_info.extension}, "
            f"mimetype={stream_info.mimetype}"
        )

    def get_supported_categories(self) -> List[str]:
        """Return all supported document categories (single source of truth).
        
        Eliminates the old bug where core_facade and kb_facade had different lists.
        """
        cats: List[str] = []
        seen: set = set()
        for reg in self._sorted_registrations():
            cat = self._converter_category(reg.converter)
            if cat and cat not in seen:
                cats.append(cat)
                seen.add(cat)
        return cats

    def get_available_categories(self) -> List[str]:
        """Return categories whose converters have all dependencies satisfied."""
        cats: List[str] = []
        seen: set = set()
        for reg in self._sorted_registrations():
            if reg.converter.check_dependencies():
                cat = self._converter_category(reg.converter)
                if cat and cat not in seen:
                    cats.append(cat)
                    seen.add(cat)
        return cats

    def diagnostics(self) -> Dict[str, Any]:
        """Return full diagnostics on converter availability."""
        available: List[str] = []
        unavailable: List[Dict[str, Any]] = []
        for reg in self._sorted_registrations():
            conv = reg.converter
            cat = self._converter_category(conv)
            if conv.check_dependencies():
                available.append(cat)
            else:
                missing = [pkg for pkg in conv.REQUIRED_PACKAGES]
                unavailable.append({
                    "category": cat,
                    "converter": conv.name,
                    "missing_packages": missing,
                    "required": conv.REQUIRED_PACKAGES,
                })
        return {"available": available, "unavailable": unavailable}

    @staticmethod
    def _converter_category(converter: DocumentConverter) -> str:
        """Extract a human-readable category from a converter instance."""
        name = converter.name.lower()
        mapping = {
            "pdfconverter": "pdf",
            "docxconverter": "docx",
            "pptxconverter": "pptx",
            "xlsxconverter": "xlsx",
            "xlsconverter": "xlsx",
            "htmlconverter": "html",
            "csvconverter": "csv",
            "markdownconverter": "markdown",
            "textconverter": "txt",
            "audioconverter": "audio",
            "imageconverter": "image",
            "videoconverter": "video",
            "jsonconverter": "json",
            "emlconverter": "eml",
        }
        return mapping.get(name, name.replace("converter", ""))


def detect_structure_role(text: str) -> str:
    """Detect the structural role of a text element from its content.
    
    Returns one of: "h1", "h2", "h3", "h4", "h5", "h6", "table", "list_item", "caption", 
    "paragraph", "code_block", or "" (unknown).
    
    Used by converters to populate DocumentElement.structure_role for downstream
    chunking and retrieval strategy selection.
    """
    import re
    lines = text.strip().split("\n", 1)
    first = lines[0].strip()
    
    # Markdown headings
    m = re.match(r"^(#{1,6})\s", first)
    if m:
        return f"h{len(m.group(1))}"
    
    # Table detection (pipe-separated columns)
    if "|" in first and "---" in text[:200]:
        return "table"
    
    # List items
    if re.match(r"^[-*+]\s|^\d+\.\s", first):
        return "list_item"
    
    # Code blocks
    if first.startswith("```"):
        return "code_block"
    
    # Figure/table caption patterns
    if re.match(r"^(Figure|Table|图|表)\s*\d+", first, re.IGNORECASE):
        return "caption"
    
    return "paragraph"


# ── Global singleton ──

_registry: Optional[ConverterRegistry] = None
_plugins_loaded: bool = False


def _load_plugins(registry: ConverterRegistry) -> None:
    """Lazy-load converter plugins via entry_points.
    
    Plugins register via setup.cfg/pyproject.toml:
        [project.entry-points."aiplat.document_converter"]
        my_format = "my_package:MyFormatConverter"
    
    Each plugin module must expose a register(registry: ConverterRegistry) function.
    """
    global _plugins_loaded
    if _plugins_loaded:
        return

    try:
        from importlib.metadata import entry_points
    except ImportError:
        return

    for ep in entry_points(group="aiplat.document_converter"):
        try:
            plugin = ep.load()
            if callable(plugin):
                plugin(registry)
            elif hasattr(plugin, "register"):
                plugin.register(registry)
            logging.info("[DocParser] Plugin loaded: %s", ep.name)
        except Exception:
            logging.debug(
                "[DocParser] Plugin '%s' failed to load: %s",
                ep.name, traceback.format_exc(),
            )

    _plugins_loaded = True


def _log_availability(registry: ConverterRegistry) -> None:
    """Log which converters are available/unavailable at startup."""
    available = []
    unavailable = []
    for reg in registry._sorted_registrations():
        conv = reg.converter
        cat = registry._converter_category(conv)
        if conv.check_dependencies():
            available.append(cat)
        else:
            missing = [pkg for pkg in conv.REQUIRED_PACKAGES if not _check_importable(pkg)]
            unavailable.append(f"{cat}(missing: {','.join(missing)})")

    logging.info("[DocParser] Available: %s", ", ".join(available))
    if unavailable:
        logging.warning("[DocParser] Unavailable: %s", ", ".join(unavailable))


def _check_importable(pkg: str) -> bool:
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


def get_document_registry() -> ConverterRegistry:
    """Get the global ConverterRegistry singleton.
    
    On first call, auto-registers all built-in converters.
    Subsequent calls return the same instance.
    """
    global _registry
    if _registry is None:
        _registry = ConverterRegistry()
        _register_builtins(_registry)
    return _registry


def _register_builtins(registry: ConverterRegistry) -> None:
    """Register all built-in converters with appropriate priorities."""
    from core.harness.document.converters._pdf import PdfConverter
    from core.harness.document.converters._docx import DocxConverter
    from core.harness.document.converters._pptx import PptxConverter
    from core.harness.document.converters._xlsx import XlsxConverter
    from core.harness.document.converters._html import HtmlConverter
    from core.harness.document.converters._csv import CsvConverter
    from core.harness.document.converters._markdown import MarkdownConverter
    from core.harness.document.converters._json import JsonConverter
    from core.harness.document.converters._eml import EmlConverter
    from core.harness.document.converters._audio import AudioConverter
    from core.harness.document.converters._image import ImageConverter
    from core.harness.document.converters._video import VideoConverter
    from core.harness.document.converters._text import TextConverter

    # Generic catch-all (lowest priority = tried last)
    registry.register(TextConverter(), priority=PRIORITY_GENERIC_FORMAT)

    # Format-specific converters (default priority = tried in registration order)
    registry.register(PdfConverter())
    registry.register(DocxConverter())
    registry.register(PptxConverter())
    registry.register(XlsxConverter())
    registry.register(HtmlConverter())
    registry.register(CsvConverter())
    registry.register(MarkdownConverter())
    registry.register(JsonConverter())
    registry.register(EmlConverter())
    registry.register(AudioConverter())
    registry.register(ImageConverter())
    registry.register(VideoConverter())

    # Log availability diagnostics
    _log_availability(registry)

    # Load 3rd-party plugins
    _load_plugins(registry)
