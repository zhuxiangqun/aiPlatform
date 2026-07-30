"""PDF converter — multi-tier fallback chain.

Priority chain:
  1. Azure Document Intelligence (if AIPLAT_AZURE_DOCINTEL_ENDPOINT is set)
  2. MarkItDown (local conversion: pdf→markdown→headings)
  3. MinerU (structure-driven table extraction, CLI subprocess)
  3.5 Smart Merge (blend MarkItDown text + MinerU tables per page)
  4. pdfplumber (local extraction)
  5. Raw text (ultimate fallback)

Azure DI provides cloud-powered OCR/layout analysis for scanned PDFs.
MinerU provides cell-level table extraction + cross-page merge.
"""
import io
import os
import re
from typing import Any, BinaryIO, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
    MissingDependencyException, detect_structure_role,
)


class PdfConverter(DocumentConverter):
    """PDF → Markdown via MarkItDown, split by headings."""

    SOURCE_FORMAT = "pdf"
    REQUIRED_PACKAGES = {}  # markitdown + pdfplumber are soft deps; handled with ImportError
    ACCEPTED_EXTENSIONS = (".pdf",)
    ACCEPTED_MIME_PREFIXES = ("application/pdf", "application/x-pdf")

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
        if not file_path:
            raise MissingDependencyException("PdfConverter requires local_path in stream_info")

        # Tier 1: Azure Document Intelligence (cloud-powered OCR)
        azure_endpoint = os.getenv("AIPLAT_AZURE_DOCINTEL_ENDPOINT", "").strip()
        if azure_endpoint:
            try:
                return self._convert_via_azure_di(file_path, azure_endpoint)
            except Exception:
                import logging
                logging.debug("Azure DI conversion failed, falling back", exc_info=True)

        # Tier 2: MarkItDown (local text extraction)
        md_elements: List[DocumentElement] = []
        try:
            from markitdown import MarkItDown
        except ImportError:
            pass  # noqa: optional-dependency
        else:
            md_elements = self._convert_via_markitdown(file_path)

        # Tier 3: MinerU (structure-driven table extraction)
        mineru_elements: List[DocumentElement] = []
        try:
            from core.harness.document.converters._mineru import MineruConverter
            mineru = MineruConverter()
            if mineru.accepts(file_stream, stream_info):
                mineru_elements = mineru.convert(file_stream, stream_info)
        except Exception:
            import logging
            logging.debug("MinerU conversion failed, falling back", exc_info=True)

        # Tier 3.5: Smart Merge — blend MarkItDown text + MinerU tables
        if md_elements and mineru_elements:
            return _merge_tiers(md_elements, mineru_elements)

        if mineru_elements:
            return mineru_elements

        if md_elements:
            return md_elements

        # Tier 4: pdfplumber (local)
        return self._fallback_pdfplumber(file_path)

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

    def _fallback_pdfplumber(self, file_path: str) -> List[DocumentElement]:
        try:
            import pdfplumber
        except ImportError:
            return self._fallback_text_from_file(file_path)

        try:
            with pdfplumber.open(file_path) as pdf:
                chunks = []
                for pi, page in enumerate(pdf.pages):
                    text = page.extract_text()
                    if text and text.strip():
                        chunks.append(text.strip())
                full_text = "\n\n".join(chunks)
        except Exception:
            return self._fallback_text_from_file(file_path)

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

    @staticmethod
    def _reorder_columns(text: str) -> str:
        """Detect and reorder multi-column text to single-column reading order."""
        if not text:
            return text
        lines = text.split("\n")
        if len(lines) < 10:
            return text

        max_width = max(len(l) for l in lines) if lines else 80
        cols = [[], [], []]
        single_col = True

        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                continue
            indent = len(line) - len(stripped)
            # Full-width blocks stay in place (titles, wide tables)
            if len(line) > max_width * 0.6:
                cols[0].append(line)
                continue
            if indent < 4:
                cols[0].append(line)
            elif indent < max_width * 0.35:
                cols[1].append(line)
                single_col = False
            else:
                cols[2].append(line)
                single_col = False

        return text if single_col else "\n\n".join(
            "\n".join(c) for c in cols if c
        )


# ── Smart Merge: blend MarkItDown text + MinerU tables ──────────

def _merge_tiers(
    md_elements: List[DocumentElement],
    mineru_elements: List[DocumentElement],
) -> List[DocumentElement]:
    """Blend MarkItDown text elements with MinerU table elements per page.

    Strategy:
      1. Group elements by page_idx.
      2. Within each page: keep MinerU type="table" (irreplaceable cells).
      3. Keep MarkItDown type="text"/"heading" (better text coherence).
      4. Deduplicate overlapping text between the two sources.
      5. Cross-page MinerU tables preserved as single elements.
    """
    md_by_page: Dict[int, List[DocumentElement]] = {}
    mu_by_page: Dict[int, List[DocumentElement]] = {}

    for e in md_elements:
        md_by_page.setdefault(e.page_idx, []).append(e)
    for e in mineru_elements:
        mu_by_page.setdefault(e.page_idx, []).append(e)

    all_pages = sorted(set(list(md_by_page.keys()) + list(mu_by_page.keys())))
    merged: List[DocumentElement] = []

    for page in all_pages:
        md_items = md_by_page.get(page, [])
        mu_items = mu_by_page.get(page, [])

        if not mu_items:
            merged.extend(md_items)
            continue
        if not md_items:
            merged.extend(mu_items)
            continue

        # MinerU tables on this page
        mu_tables = [e for e in mu_items if e.type == "table"]

        # MarkItDown text on this page
        md_text = [e for e in md_items if e.type != "table"]

        # Collect all MarkItDown text content for deduplication
        md_text_content = " ".join(e.text.lower() for e in md_text)

        # Keep MinerU tables + non-overlapping text
        for mu in mu_items:
            if mu.type == "table":
                merged.append(mu)  # always keep MinerU tables
            else:
                # Keep MinerU text only if not substantially present in MarkItDown
                mu_text_lower = mu.text.lower()
                if _text_overlap_ratio(mu_text_lower, md_text_content) < 0.6:
                    merged.append(mu)

        # Add MarkItDown text (already deduped by overlap check above)
        for md in md_text:
            merged.append(md)

    return merged


def _text_overlap_ratio(a: str, b: str) -> float:
    """Jaccard-like overlap ratio between two text strings."""
    if not a or not b:
        return 0.0
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))

