"""
Unit tests for DocumentConverter protocol, ConverterRegistry, and content detection.

Covers:
  - Converter registration and dispatch
  - Content-based file header detection
  - Structure role detection
  - Priority-based fallback chain
  - Diagnostics and availability reporting
  - Legacy format backward compatibility
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
    ConverterRegistry, get_document_registry,
    FileConversionException, UnsupportedFormatException,
    MissingDependencyException,
    detect_structure_role,
    _guess_extension_from_header, _guess_zip_subtype,
    PRIORITY_SPECIFIC_FORMAT, PRIORITY_GENERIC_FORMAT,
)


class TestStreamInfo:

    def test_default_values(self):
        info = StreamInfo()
        assert info.extension is None
        assert info.mimetype is None
        assert info.local_path is None

    def test_copy_and_update(self):
        info = StreamInfo(extension=".pdf", local_path="/tmp/test.pdf")
        updated = info.copy_and_update(mimetype="application/pdf")
        assert updated.extension == ".pdf"
        assert updated.mimetype == "application/pdf"
        assert updated.local_path == "/tmp/test.pdf"
        # Original unchanged
        assert info.mimetype is None

    def test_copy_and_update_overwrite(self):
        info = StreamInfo(extension=".pdf")
        updated = info.copy_and_update(extension=".docx")
        assert updated.extension == ".docx"
        assert info.extension == ".pdf"


class TestDocumentElement:

    def test_default_values(self):
        el = DocumentElement()
        assert el.type == "text"
        assert el.text == ""
        assert el.page_idx == 0
        assert el.cells is None
        assert el.source_format == ""
        assert el.structure_role == ""
        assert el.confidence == 1.0

    def test_full_construction(self):
        el = DocumentElement(
            type="table", text="a | b", page_idx=3,
            cells=[["a", "b"], ["1", "2"]],
            meta={"source": "csv"},
            source_format="csv",
            structure_role="table",
            confidence=0.95,
        )
        assert el.type == "table"
        assert el.page_idx == 3
        assert len(el.cells) == 2
        assert el.confidence == 0.95


class TestContentDetection:

    def test_pdf_header(self):
        assert _guess_extension_from_header(b"%PDF-1.4\n...") == ".pdf"
        assert _guess_extension_from_header(b"%PDF-2.0") == ".pdf"

    def test_png_header(self):
        assert _guess_extension_from_header(b"\x89PNG\r\n\x1a\n...") == ".png"

    def test_jpeg_header(self):
        assert _guess_extension_from_header(b"\xff\xd8\xff...") == ".jpg"

    def test_html_header(self):
        assert _guess_extension_from_header(b"<!DOCTYPE html>...") == ".html"
        assert _guess_extension_from_header(b"<html>...") == ".html"

    def test_eml_header(self):
        assert _guess_extension_from_header(b"From: test@x.com\n...") == ".eml"
        assert _guess_extension_from_header(b"Return-Path: <x>\n...") == ".eml"

    def test_unknown_header(self):
        assert _guess_extension_from_header(b"random garbage data") is None

    def test_zip_subtype_docx(self):
        assert _guess_zip_subtype("report.docx", b"PK\x03\x04...") == ".docx"

    def test_zip_subtype_pptx(self):
        assert _guess_zip_subtype("slides.pptx", b"PK\x03\x04...") == ".pptx"

    def test_zip_subtype_xlsx(self):
        assert _guess_zip_subtype("data.xlsx", b"PK\x03\x04...") == ".xlsx"

    def test_zip_subtype_unknown(self):
        assert _guess_zip_subtype("archive.zip", b"PK\x03\x04...") is None


class TestStructureRoleDetection:

    def test_h1(self):
        assert detect_structure_role("# Title") == "h1"

    def test_h2(self):
        assert detect_structure_role("## Subsection") == "h2"

    def test_h6(self):
        assert detect_structure_role("###### Deep") == "h6"

    def test_list_item_dash(self):
        assert detect_structure_role("- item one") == "list_item"

    def test_list_item_numbered(self):
        assert detect_structure_role("1. First") == "list_item"

    def test_table(self):
        text = "| A | B |\n|---|---|"
        assert detect_structure_role(text) == "table"

    def test_caption_figure(self):
        assert detect_structure_role("Figure 1: Architecture") == "caption"

    def test_caption_chinese(self):
        assert detect_structure_role("图 2: 流程图") == "caption"

    def test_paragraph(self):
        assert detect_structure_role("普通文本段落") == "paragraph"


class TestConverterRegistry:

    @pytest.fixture(autouse=True)
    def registry(self):
        return get_document_registry()

    def test_singleton(self, registry):
        r2 = get_document_registry()
        assert registry is r2

    def test_13_converters_registered(self, registry):
        cats = registry.get_supported_categories()
        assert len(cats) == 13
        assert "pdf" in cats
        assert "docx" in cats
        assert "xlsx" in cats
        assert "audio" in cats
        assert "video" in cats
        assert "txt" in cats

    def test_find_converter_pdf(self, registry):
        conv = registry.find_converter(StreamInfo(extension=".pdf"))
        assert conv is not None
        assert conv.name == "PdfConverter"

    def test_find_converter_docx(self, registry):
        conv = registry.find_converter(StreamInfo(extension=".docx"))
        assert conv.name == "DocxConverter"

    def test_find_converter_csv(self, registry):
        conv = registry.find_converter(StreamInfo(extension=".csv"))
        assert conv.name == "CsvConverter"

    def test_find_converter_unknown_fallback(self, registry):
        conv = registry.find_converter(StreamInfo(extension=".unknown"))
        assert conv is not None
        assert conv.name == "TextConverter"

    def test_find_converter_by_mimetype(self, registry):
        conv = registry.find_converter(StreamInfo(mimetype="application/pdf"))
        assert conv is not None
        assert conv.name == "PdfConverter"

    def test_find_all_converters(self, registry):
        # Multiple acceptors: .pdf also matches TextConverter
        convs = registry.find_all_converters(StreamInfo(extension=".pdf"))
        names = [c.name for c in convs]
        assert "PdfConverter" in names

    def test_available_categories(self, registry):
        avail = registry.get_available_categories()
        supported = registry.get_supported_categories()
        assert set(avail) == set(supported)

    def test_diagnostics(self, registry):
        diag = registry.diagnostics()
        assert "available" in diag
        assert "unavailable" in diag
        assert len(diag["available"]) == 13

    def test_content_detection_misnamed_pdf(self, registry):
        """A .xyz file that's actually a PDF should be detected correctly."""
        tmp = tempfile.NamedTemporaryFile(suffix=".xyz", delete=False)
        tmp.write(b"%PDF-1.4\nfake pdf content")
        tmp.close()
        try:
            info = StreamInfo(local_path=tmp.name, extension=".xyz")
            conv = registry.find_converter(info)
            assert conv is not None
            assert conv.name == "PdfConverter"
        finally:
            os.unlink(tmp.name)

    def test_custom_converter_registration(self):
        """A custom converter can be registered and found."""
        class MyConverter(DocumentConverter):
            def accepts(self, file_stream, stream_info, **kwargs):
                return (stream_info.extension or "") == ".myfmt"

            def convert(self, file_stream, stream_info, **kwargs):
                return [DocumentElement(type="text", text="custom_output", meta={"source": "myfmt"})]

        reg = ConverterRegistry()
        reg.register(MyConverter())
        conv = reg.find_converter(StreamInfo(extension=".myfmt"))
        assert conv is not None
        assert conv.name == "MyConverter"

    def test_priority_ordering(self):
        """Lower priority = tried first."""
        class HighPriority(DocumentConverter):
            def accepts(self, file_stream, stream_info, **kwargs):
                return True
            def convert(self, file_stream, stream_info, **kwargs):
                return [DocumentElement(text="high")]

        class LowPriority(DocumentConverter):
            def accepts(self, file_stream, stream_info, **kwargs):
                return True
            def convert(self, file_stream, stream_info, **kwargs):
                return [DocumentElement(text="low")]

        reg = ConverterRegistry()
        reg.register(LowPriority(), priority=PRIORITY_GENERIC_FORMAT)
        reg.register(HighPriority(), priority=PRIORITY_SPECIFIC_FORMAT)

        # find_converter should return HighPriority first
        info = StreamInfo(extension=".test")
        conv = reg.find_converter(info)
        assert conv.name == "HighPriority"


class TestLegacyParserBackwardCompatibility:
    """Verify old parser functions still work."""

    def test_parse_markdown(self):
        from core.harness.document.parsers import parse_markdown
        tmp = tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8")
        tmp.write("# Test\nContent")
        tmp.close()
        try:
            elements = parse_markdown(tmp.name)
            assert len(elements) >= 1
            assert any("Test" in e["text"] for e in elements)
        finally:
            os.unlink(tmp.name)

    def test_parse_csv(self):
        from core.harness.document.parsers import parse_csv
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False, encoding="utf-8")
        tmp.write("a,b,c\n1,2,3")
        tmp.close()
        try:
            elements = parse_csv(tmp.name)
            assert len(elements) >= 1
        finally:
            os.unlink(tmp.name)

    def test_parse_json(self):
        from core.harness.document.parsers import parse_json_document
        tmp = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8")
        tmp.write('{"k": "v"}')
        tmp.close()
        try:
            elements = parse_json_document(tmp.name)
            assert len(elements) >= 1
        finally:
            os.unlink(tmp.name)

    def test_parse_eml(self):
        from core.harness.document.parsers import parse_eml
        tmp = tempfile.NamedTemporaryFile(suffix=".eml", mode="w", delete=False, encoding="utf-8")
        tmp.write("From: a@b.com\nSubject: Hi\n\nBody")
        tmp.close()
        try:
            elements = parse_eml(tmp.name)
            assert len(elements) >= 1
        finally:
            os.unlink(tmp.name)


class TestFallbackChain:
    """Verify convert_with_fallback handles failures gracefully."""

    def test_fallback_chain_multiple_attempts(self):
        """All failing converters should be collected in FileConversionException."""
        class FailingConverter(DocumentConverter):
            def accepts(self, file_stream, stream_info, **kwargs):
                return True
            def convert(self, file_stream, stream_info, **kwargs):
                raise RuntimeError("always fails")

        reg = ConverterRegistry()
        reg.register(FailingConverter())

        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"test content")
        tmp.close()
        try:
            with pytest.raises(FileConversionException) as exc:
                with open(tmp.name, "rb") as f:
                    reg.convert_with_fallback(f, StreamInfo(extension=".txt", local_path=tmp.name))
            assert len(exc.value.attempts) >= 1
            assert "FailingConverter" in str(exc.value)
        finally:
            os.unlink(tmp.name)

    def test_fallback_chain_empty_registry(self):
        """Empty registry should raise UnsupportedFormatException."""
        reg = ConverterRegistry()
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        tmp.write(b"content")
        tmp.close()
        try:
            with pytest.raises(UnsupportedFormatException):
                with open(tmp.name, "rb") as f:
                    reg.convert_with_fallback(f, StreamInfo(extension=".txt", local_path=tmp.name))
        finally:
            os.unlink(tmp.name)


class TestKbFacadeIntegration:

    def test_kb_parse_document_markdown(self):
        from core.api.facades.kb_facade import kb_parse_document
        tmp = tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False, encoding="utf-8")
        tmp.write("## Section\nContent")
        tmp.close()
        try:
            elements = kb_parse_document(tmp.name, "markdown")
            assert len(elements) >= 1
        finally:
            os.unlink(tmp.name)

    def test_kb_parse_document_fallback_text(self):
        from core.api.facades.kb_facade import kb_parse_document
        tmp = tempfile.NamedTemporaryFile(suffix=".xyz", mode="w", delete=False, encoding="utf-8")
        tmp.write("some text")
        tmp.close()
        try:
            elements = kb_parse_document(tmp.name, "unknown")
            assert len(elements) >= 1
        finally:
            os.unlink(tmp.name)

    def test_normalize_kind(self):
        from core.api.facades.kb_facade import normalize_kind
        assert normalize_kind("word") == "docx"
        assert normalize_kind("doc") == "docx"
        assert normalize_kind("ppt") == "pptx"
        assert normalize_kind("xls") == "xlsx"
        assert normalize_kind("md") == "markdown"
