"""MinerU PDF converter — structure-driven table extraction.

Integrates MinerU CLI as a DocumentConverter, producing DocumentElement
objects with type="table" cells as 2D arrays. Non-table content is
converted to type="text" elements.

Design:
  - CLI subprocess (no Python SDK yet) — backend="cli" parameter reserves
    future path for backend="sdk"
  - ENV: AIPLAT_PDF_MINERU_ENABLED controls activation; if "0"/"false", skip
  - ENV: AIPLAT_PDF_MINERU_TABLE_ONLY — when true, only return table elements
  - accepts() checks shutil.which("mineru") + env gate
  - convert() runs subprocess → JSON → DocumentElement[]
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional

from core.harness.document.protocol import (
    DocumentConverter, DocumentElement, StreamInfo,
)

logger = logging.getLogger(__name__)


class MineruConverter(DocumentConverter):
    """MinerU PDF → structured DocumentElements (table-first).

    Only handles PDF — accept() for other formats returns False.
    Activated when mineru CLI is on PATH and AIPLAT_PDF_MINERU_ENABLED is not "false".
    """

    SOURCE_FORMAT = "pdf"
    REQUIRED_PACKAGES = {}  # CLI-based; not a Python dependency
    ACCEPTED_EXTENSIONS = (".pdf",)
    ACCEPTED_MIME_PREFIXES = ("application/pdf", "application/x-pdf")

    def __init__(self, backend: str = "cli"):
        self._backend = backend

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        if not self._accepts_by_format(stream_info):
            return False
        enabled = os.getenv("AIPLAT_PDF_MINERU_ENABLED", "true").strip().lower()
        if enabled in ("0", "false", "no"):
            return False
        if self._backend == "cli":
            return shutil.which("mineru") is not None
        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> List[DocumentElement]:
        file_path = stream_info.local_path
        if not file_path:
            from core.harness.document.protocol import MissingDependencyException
            raise MissingDependencyException(
                "MineruConverter requires local_path in stream_info")

        content_list = self._invoke(file_path)
        if not content_list:
            return []

        table_only = os.getenv(
            "AIPLAT_PDF_MINERU_TABLE_ONLY", "false").strip().lower() in ("1", "true", "yes")
        return self._content_list_to_elements(content_list, table_only=table_only)

    # ── CLI invocation ─────────────────────────────────────────

    def _invoke(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Run MinerU CLI and return the parsed content list."""
        if self._backend == "cli":
            return self._invoke_cli(pdf_path)
        return []  # future: backend="sdk" → import magic_pdf

    def _invoke_cli(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Subprocess-based MinerU CLI call with timeout + heartbeat."""
        backend = os.getenv("AIPLAT_MINERU_BACKEND", "pipeline")
        lang = os.getenv("AIPLAT_MINERU_LANG", "ch")
        timeout_s = int(os.getenv("AIPLAT_MINERU_TIMEOUT_SECONDS", "240") or "240")
        poll_s = float(os.getenv("AIPLAT_MINERU_POLL_SECONDS", "2.0") or "2.0")

        with tempfile.TemporaryDirectory(prefix="mineru_") as out_dir:
            # Resolve executable
            if shutil.which("mineru"):
                base_exec = ["mineru"]
            else:
                base_exec = [sys.executable, "-m", "mineru"]

            cmd = base_exec + [
                "-p", pdf_path,
                "-o", out_dir,
                "-m", "auto",
                "-b", backend,
                "-l", lang,
            ]

            logger.info("[MinerU] Running: %s", " ".join(cmd))
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True,
            )

            start = time.time()
            last_err = ""
            while True:
                try:
                    proc.wait(timeout=poll_s)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = time.time() - start
                    if elapsed > timeout_s:
                        proc.terminate()
                        time.sleep(1)
                        if proc.poll() is None:
                            proc.kill()
                        last_err = f"mineru_timeout_{timeout_s}s"
                        logger.warning("[MinerU] Timeout after %.0fs", elapsed)
                        break

            if proc.returncode != 0:
                stderr = proc.stderr.read() if proc.stderr else ""
                last_err = f"exit_code_{proc.returncode}: {stderr[:200]}"
                logger.warning("[MinerU] Failed: %s", last_err)

            return _load_mineru_content_list(out_dir) if not last_err else []

    # ── JSON → DocumentElement ──────────────────────────────────

    def _content_list_to_elements(
        self,
        content_list: List[Dict[str, Any]],
        table_only: bool = False,
    ) -> List[DocumentElement]:
        """Convert MinerU content-list JSON to DocumentElement list."""
        elements: List[DocumentElement] = []
        for item in content_list:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type", "")
            page_idx = int(item.get("page_idx", 0))
            text = item.get("text", "") or item.get("md", "") or ""

            if item_type == "table":
                cells = _table_text_to_cells(item)
                if cells:
                    elements.append(DocumentElement(
                        type="table",
                        text=text or _cells_to_markdown(cells),
                        page_idx=page_idx,
                        cells=cells,
                        meta={"source": "pdf", "parser": "mineru"},
                        source_format="pdf",
                        structure_role="table",
                    ))
            elif not table_only:
                if text.strip():
                    elements.append(DocumentElement(
                        type="text",
                        text=text.strip(),
                        page_idx=page_idx,
                        meta={"source": "pdf", "parser": "mineru"},
                        source_format="pdf",
                    ))
        return elements


# ── Helper: table extraction from MinerU JSON ────────────────────

def _table_text_to_cells(obj: Dict[str, Any]) -> Optional[List[List[str]]]:
    """Normalize MinerU/Docling table payloads to 2D cell array."""
    for key in ("cells", "table_cells"):
        val = obj.get(key)
        if isinstance(val, list) and val and isinstance(val[0], list):
            return val  # Already 2D

    # Try Markdown table fields
    for key in ("table_body", "table_data", "md", "markdown"):
        val = obj.get(key)
        if isinstance(val, str) and "|" in val:
            cells = _parse_markdown_table(val)
            if cells:
                return cells
    return None


def _parse_markdown_table(md: str) -> Optional[List[List[str]]]:
    """Parse a markdown table string to 2D cell array."""
    lines = [l.strip() for l in md.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return None
    rows = []
    for line in lines:
        if re.match(r"^\|?[\s\-:|]+\|?$", line):
            continue  # separator row
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and any(c for c in cells):
            rows.append(cells)
    return rows if len(rows) >= 1 else None


def _cells_to_markdown(cells: List[List[str]]) -> str:
    """Convert 2D cells to markdown table string."""
    if not cells:
        return ""
    lines = []
    for i, row in enumerate(cells):
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * len(row)) + "|")
    return "\n".join(lines)


def _load_mineru_content_list(output_dir: str) -> List[Dict[str, Any]]:
    """Scan output_dir for MinerU content-list JSON files."""
    root = Path(output_dir)
    json_files = sorted(
        [p for p in root.rglob("*.json")
         if p.name not in ("manifest.json", "meta.json")],
        key=lambda p: -p.stat().st_size,
    )
    for path in json_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and "type" in first and "page_idx" in first:
                    return data
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
    return []
