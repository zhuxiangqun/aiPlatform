"""Markdown converter — splits by headings with frontmatter extraction."""
import logging
import re
from typing import Any, BinaryIO, Dict, List

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo, detect_structure_role,
)

ACCEPTED_MIME_PREFIXES = ["text/markdown", "text/x-markdown"]
ACCEPTED_EXTENSIONS = [".md", ".markdown"]


class MarkdownConverter(DocumentConverter):
    """Markdown → heading-split elements with frontmatter extraction."""

    REQUIRED_PACKAGES = {}  # yaml optional for frontmatter

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
        text = data.decode("utf-8", errors="ignore")
        if not text.strip():
            return []

        frontmatter: Dict[str, Any] = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml as _yaml
                    fm = _yaml.safe_load(parts[1]) or {}
                    if isinstance(fm, dict):
                        frontmatter = {k: fm[k] for k in fm}
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                body = parts[2]

        wikilinks = re.findall(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", body)
        link_texts = [l[0] for l in wikilinks]

        sections = re.split(r"\n(?=#{1,6}\s)", body)
        elements: List[DocumentElement] = []
        for si, section in enumerate(sections):
            if section.strip():
                meta = {"source": "markdown"}
                if frontmatter:
                    meta.update(frontmatter if si == 0 else {
                        "tags": frontmatter.get("tags", []) if isinstance(frontmatter.get("tags"), list) else [],
                        "aliases": frontmatter.get("aliases", []) if isinstance(frontmatter.get("aliases"), list) else [],
                    })
                if link_texts:
                    meta["wikilinks"] = link_texts
                elements.append(DocumentElement(
                    type="text", text=section.strip(),
                    page_idx=si, meta=meta,
                    source_format="markdown",
                    structure_role=detect_structure_role(section.strip()),
                ))
        return elements or [DocumentElement(
            type="text", text=text.strip(), page_idx=0,
            meta={"source": "markdown", **frontmatter},
            source_format="markdown",
        )]
