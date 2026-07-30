"""MinerU document parsing (PoC — DEPRECATED).

⚠ MIGRATED: MinerU is now integrated into the core PdfConverter chain.
   → core/harness/document/converters/_mineru.py (MineruConverter class)
   → core/harness/document/converters/_pdf.py   (Tier 3 fallback + Smart Merge)

This file is retained for backward compatibility with external callers.
All functions delegate to the core MineruConverter or its helpers.
The old subprocess-based implementation has been removed.

ENV migration:
  AIPLAT_KB_PARSER → AIPLAT_PDF_MINERU_ENABLED (controls PdfConverter Tier 3)
  AIPLAT_PDF_MINERU_TABLE_ONLY               (MinerU only extracts tables)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Re-export helpers from core for backward compatibility
from core.harness.document.converters._mineru import (
    _table_text_to_cells,
    _parse_markdown_table,
    _cells_to_markdown,
    _load_mineru_content_list,
)


def run_mineru_parse(
    *, pdf_path: str, out_dir: str, max_pages: Optional[int] = None,
    parse_method: str = "auto", heartbeat_cb: Any = None,
) -> Any:
    """DEPRECATED: Use CoreFacade.kb_parse_document() instead.
    
    CoreFacade routes through PdfConverter which includes MinerU as Tier 3.
    """
    import warnings
    warnings.warn(
        "run_mineru_parse is deprecated. Use CoreFacade.kb_parse_document(). "
        "MinerU is now integrated in core PdfConverter chain.",
        DeprecationWarning, stacklevel=2,
    )
    from core.harness.document.converters._mineru import MineruConverter
    converter = MineruConverter()
    from core.harness.document.protocol import StreamInfo
    info = StreamInfo(local_path=pdf_path, extension=".pdf")
    elements = converter.convert(None, info)
    # Legacy return: path to output directory
    from pathlib import Path
    return Path(out_dir)


def extract_tables_from_content_list(
    content_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """DEPRECATED: Use CoreFacade output directly (DocumentElement.cells)."""
    import warnings
    warnings.warn(
        "extract_tables_from_content_list is deprecated. "
        "DocumentElement.cells provides structured table data.",
        DeprecationWarning, stacklevel=2,
    )
    return [
        {"page_idx": int(item.get("page_idx", 0)),
         "caption": item.get("caption") or [],
         "cells": _table_text_to_cells(item) or [],
         "raw": item}
        for item in (content_list or [])
        if isinstance(item, dict) and item.get("type") == "table"
    ]


load_mineru_content_list = _load_mineru_content_list  # deprecated alias
