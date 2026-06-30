"""PDF converter — delegates to MarkItDown with optional Azure Document Intelligence.

Priority chain:
  1. Azure Document Intelligence (if AIPLAT_AZURE_DOCINTEL_ENDPOINT is set)
  2. MarkItDown (local conversion: pdf→markdown→headings)
  3. pdfplumber (local extraction)
  4. Raw text (ultimate fallback)

Azure DI provides cloud-powered OCR/layout analysis for scanned PDFs,
replacing the legacy PoC MinerU pipeline (poc/mineru_extract.py).
"""
import io
import os
import re
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
    MissingDependencyException, detect_structure_role,
)

ACCEPTED_MIME_PREFIXES = ["application/pdf", "application/x-pdf"]
ACCEPTED_EXTENSIONS = [".pdf"]


class PdfConverter(DocumentConverter):
    """PDF → Markdown via MarkItDown, split by headings."""

    REQUIRED_PACKAGES = {}  # markitdown + pdfplumber are soft deps; handled with ImportError

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()
        if extension in ACCEPTED_EXTENSIONS:
            return True
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
        if not file_path:
            raise MissingDependencyException("PdfConverter requires local_path in stream_info")

        # Tier 1: Azure Document Intelligence (cloud-powered OCR)
        azure_endpoint = os.getenv("AIPLAT_AZURE_DOCINTEL_ENDPOINT", "").strip()
        if azure_endpoint:
            try:
                return self._convert_via_azure_di(file_path, azure_endpoint)
            except Exception:
                import logging
                logging.debug("Azure DI conversion failed, falling back to local", exc_info=True)

        # Tier 2: MarkItDown (local)
        try:
            from markitdown import MarkItDown
        except ImportError:
            return self._fallback_pdfplumber(file_path)

        return self._convert_via_markitdown(file_path)

    def _convert_via_azure_di(self, file_path: str, endpoint: str) -> List[DocumentElement]:
        """Convert PDF via Azure Document Intelligence (markitdown v0.1.6+)."""
        from markitdown import MarkItDown
        kwargs = {"docintel_endpoint": endpoint}
        credential = os.getenv("AIPLAT_AZURE_DOCINTEL_KEY", "").strip()
        if credential:
            from azure.core.credentials import AzureKeyCredential
            kwargs["docintel_credential"] = AzureKeyCredential(credential)
        md = MarkItDown(**kwargs)
        result = md.convert(file_path)
        text = result.text_content or ""
        return self._split_headings(text, "azure_di")

    def _convert_via_markitdown(self, file_path: str) -> List[DocumentElement]:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content or ""
        return self._split_headings(text, "markitdown")

    def _split_headings(self, text: str, parser: str) -> List[DocumentElement]:
        """Split markdown text by headings into DocumentElements."""
        if not text.strip():
            return []

        sections = re.split(r"\n(?=#{1,6}\s)", text)
        elements: List[DocumentElement] = []
        for si, section in enumerate(sections):
            if section.strip():
                elements.append(DocumentElement(
                    type="text",
                    text=section.strip(),
                    page_idx=si,
                    meta={"source": "pdf", "parser": parser},
                    source_format="pdf",
                    structure_role=detect_structure_role(section.strip()),
                ))
        return elements or [DocumentElement(
            type="text", text=text.strip(), page_idx=0,
            meta={"source": "pdf", "parser": parser},
            source_format="pdf",
        )]

    def _fallback_pdfplumber(self, file_path: str) -> List[DocumentElement]:
        try:
            import pdfplumber
        except ImportError:
            return self._fallback_text(file_path)

        try:
            with pdfplumber.open(file_path) as pdf:
                chunks = []
                for pi, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        chunks.append(text.strip())
                full_text = "\n\n".join(chunks)
        except Exception:
            return self._fallback_text(file_path)

        if not full_text.strip():
            return []

        sections = re.split(r"\n(?=#{1,6}\s)", full_text)
        elements: List[DocumentElement] = []
        for si, section in enumerate(sections):
            if section.strip():
                elements.append(DocumentElement(
                    type="text",
                    text=section.strip(),
                    page_idx=si,
                    meta={"source": "pdf", "parser": "pdfplumber"},
                    source_format="pdf",
                    structure_role=detect_structure_role(section.strip()),
                ))
        return elements or [DocumentElement(
            type="text", text=full_text.strip(), page_idx=0,
            meta={"source": "pdf", "parser": "pdfplumber"},
            source_format="pdf",
        )]

    def _fallback_text(self, file_path: str) -> List[DocumentElement]:
        with open(file_path, "rb") as f:
            data = f.read()
        text = data.decode("utf-8", errors="ignore")
        if not text.strip():
            return []
        return [DocumentElement(
            type="text", text=text.strip(), page_idx=0,
            meta={"source": "pdf", "fallback": True},
            source_format="pdf",
        )]
