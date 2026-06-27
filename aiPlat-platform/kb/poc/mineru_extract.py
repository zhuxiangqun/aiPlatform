"""MinerU document parsing (PoC).

⚠ BOUNDARY BLUR (cross-layer audit): document parsing with MinerU CLI belongs
in core's document layer (core/harness/document/), not in platform's KB service.
Migration plan: delegate to core.harness.document.parsers once core provides
a MinerU-based parser. This file is in poc/ and marked experimental.
"""
from __future__ import annotations
import logging

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _iter_json_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    out: List[Path] = []
    for p in root.rglob("*.json"):
        # skip obviously irrelevant meta files
        if p.name.lower() in {"manifest.json", "meta.json"}:
            continue
        out.append(p)
    return out


def _load_json_safely(p: Path) -> Optional[Any]:
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _pick_content_list_json(root: Path) -> Optional[Path]:
    """
    MinerU / wrappers may produce multiple JSONs. Pick the one that looks like a
    MinerU-style content list: a list of dict with keys like 'type' and 'page_idx'.
    """
    best: Tuple[int, Path] | None = None
    for p in _iter_json_files(root):
        data = _load_json_safely(p)
        if not isinstance(data, list) or not data:
            continue
        # Heuristic: count items with expected keys
        score = 0
        for it in data[:50]:
            if isinstance(it, dict) and ("type" in it) and ("page_idx" in it):
                score += 1
        if score <= 0:
            continue
        # Prefer larger lists and higher score
        total_score = score * 1000 + len(data)
        if best is None or total_score > best[0]:
            best = (total_score, p)
    return best[1] if best else None


def _parse_markdown_table(md: str) -> List[List[str]]:
    """
    Very small markdown-table parser that supports:
    | a | b |
    |---|---|
    | 1 | 2 |
    """
    lines = [ln.strip() for ln in (md or "").splitlines() if ln.strip()]
    if not lines:
        return []
    # keep only lines that look like table rows
    rows = [ln for ln in lines if ln.count("|") >= 2]
    if len(rows) < 2:
        return []
    # remove separator line(s)
    cleaned: List[str] = []
    for ln in rows:
        if re.fullmatch(r"\|?[\s:\-|\+]+\|?", ln):
            continue
        cleaned.append(ln)

    out: List[List[str]] = []
    for ln in cleaned:
        parts = [p.strip() for p in ln.strip("|").split("|")]
        if parts and any(p for p in parts):
            out.append(parts)
    return out


def _table_text_to_cells(obj: Dict[str, Any]) -> List[List[str]]:
    """
    Try to normalize different possible MinerU/Docling table payloads to a 2D cell array.
    """
    # Common keys seen in multimodal pipelines
    for k in ("cells", "table_cells"):
        v = obj.get(k)
        if isinstance(v, list) and v and all(isinstance(r, list) for r in v):
            return [[str(c) for c in r] for r in v]

    # Markdown/CSV-ish
    for k in ("table_body", "table_data", "md", "markdown"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            cells = _parse_markdown_table(v)
            if cells:
                return cells

    return []


def run_mineru_parse(
    *,
    pdf_path: str,
    out_dir: str,
    max_pages: Optional[int] = None,
    parse_method: str = "auto",
    heartbeat_cb: Optional[callable] = None,
) -> Path:
    """
    Run MinerU CLI to parse a PDF into a content list.
    This is best-effort: different MinerU versions have different CLI flags.
    We try a small set of common variants.
    Returns the output directory used.
    """
    # Do NOT rely on PATH. Prefer invoking via the current Python interpreter:
    #   python -m mineru ...
    # Fall back to the console script if available.
    base_exec: List[str]
    if shutil.which("mineru"):
        base_exec = ["mineru"]
    else:
        base_exec = [sys.executable, "-m", "mineru"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # try common CLI styles
    candidates: List[List[str]] = []
    # MinerU official CLI (2.x): mineru -p/--path <input> -o/--output <dir> -m/--method auto|txt|ocr
    # Use CPU-friendly backend for stability unless user overrides.
    backend = os.getenv("AIPLAT_MINERU_BACKEND", "pipeline").strip() or "pipeline"
    lang = os.getenv("AIPLAT_MINERU_LANG", "ch").strip() or "ch"
    cmd_main = [*base_exec, "-p", str(pdf_path), "-o", str(out), "-m", str(parse_method), "-b", backend, "-l", lang]
    api_url = os.getenv("AIPLAT_MINERU_API_URL", "").strip()
    if api_url:
        cmd_main += ["--api-url", api_url]
    # MinerU uses -s/-e as page window (0-based). Use -e as an approximate max_pages bound.
    if max_pages:
        cmd_main += ["-s", "0", "-e", str(int(max_pages) - 1)]
    candidates.append(cmd_main)

    # Older/alternate wrappers (kept for compatibility; harmless if unsupported)
    cmd_alt = [*base_exec, "--path", str(pdf_path), "--output", str(out), "--method", str(parse_method)]
    if max_pages:
        cmd_alt += ["--start", "0", "--end", str(int(max_pages) - 1)]
    candidates.append(cmd_alt)

    # First run may download models and take time. Keep a bounded timeout and fall back to OCR.
    timeout_s = int(os.getenv("AIPLAT_MINERU_TIMEOUT_SECONDS", "240"))
    poll_s = float(os.getenv("AIPLAT_MINERU_POLL_SECONDS", "2.0"))

    last_err = None
    for cmd in candidates:
        proc = None
        try:
            start_ts = time.time()
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # Heartbeat loop so job UI doesn't look frozen.
            while True:
                rc = proc.poll()
                if rc is not None:
                    out_s, err_s = proc.communicate(timeout=5)
                    if rc == 0:
                        return out
                    last_err = (err_s or out_s or "").strip()
                    break
                elapsed = time.time() - start_ts
                if heartbeat_cb:
                    try:
                        heartbeat_cb(elapsed, timeout_s, {"backend": backend, "lang": lang})
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
                if elapsed >= timeout_s:
                    try:
                        proc.terminate()
                        time.sleep(1)
                        if proc.poll() is None:
                            proc.kill()
                    except Exception as e:
                        logging.debug(str(e), exc_info=True)
                    last_err = f"mineru_timeout_{timeout_s}s"
                    break
                time.sleep(poll_s)
        except FileNotFoundError as e:
            last_err = str(e)
        except Exception as e:
            last_err = str(e)
        finally:
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception as e:
                logging.debug(str(e), exc_info=True)
    raise RuntimeError(f"mineru_failed: {last_err}")


def load_mineru_content_list(output_dir: str) -> List[Dict[str, Any]]:
    root = Path(output_dir)
    p = _pick_content_list_json(root)
    if not p:
        return []
    data = _load_json_safely(p)
    return data if isinstance(data, list) else []


def extract_tables_from_content_list(content_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return normalized tables:
      {page_idx:int, caption:list[str], cells:list[list[str]], raw:dict}
    """
    out: List[Dict[str, Any]] = []
    for it in content_list:
        if not isinstance(it, dict):
            continue
        if str(it.get("type", "")).lower() != "table":
            continue
        page_idx = int(it.get("page_idx") or 0)
        caption = it.get("table_caption") or it.get("caption") or []
        if isinstance(caption, str):
            caption = [caption]
        if not isinstance(caption, list):
            caption = []
        cells = _table_text_to_cells(it)
        out.append({"page_idx": page_idx, "caption": caption, "cells": cells, "raw": it})
    return out
