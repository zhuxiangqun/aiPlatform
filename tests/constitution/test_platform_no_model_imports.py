"""
Architecture Constitution Tests: Platform No Direct AI Model Imports

Enforces boundary-standard.md §铁律1: Model inference belongs in Core.
Platform must NOT directly import AI model libraries (Whisper, Tesseract,
PaddleOCR, sentence-transformers). These must be accessed via CoreFacade
or provider callbacks.

Authoritative reference: docs/architecture/boundary-standard.md
"""

import ast
from pathlib import Path
from typing import List, Set, Tuple

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLATFORM_DIR = WORKSPACE_ROOT / "aiPlat-platform"

FORBIDDEN_MODEL_IMPORTS: List[str] = [
    "faster_whisper",
    "whisper",
    "pytesseract",
    "paddleocr",
    "sentence_transformers",
]

KNOWN_DEBT_FILES: Set[str] = {
    "kb/poc/ocr.py",       # legacy PoC — to be replaced by core/harness/document/ocr.py
    "kb/video.py",         # transcriber+OCR to be extracted to core/harness/document/
}


def _is_import_of(import_name: str, lib: str) -> bool:
    return import_name == lib or import_name.startswith(lib + ".")


def _gather_py_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*.py"):
        if p.is_file() and "__pycache__" not in str(p):
            files.append(p)
    return files


def _relative_path(fp: Path) -> str:
    try:
        return str(fp.relative_to(PLATFORM_DIR))
    except ValueError:
        return str(fp)


def test_platform_no_direct_model_imports():
    """Platform must not directly import AI model libraries at module level."""
    violations: List[str] = []

    for fp in _gather_py_files(PLATFORM_DIR):
        rel = _relative_path(fp)
        if rel in KNOWN_DEBT_FILES:
            continue
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for lib in FORBIDDEN_MODEL_IMPORTS:
                        if _is_import_of(alias.name, lib):
                            violations.append(f"{rel}: import {alias.name} (line ~{node.lineno})")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for lib in FORBIDDEN_MODEL_IMPORTS:
                        if _is_import_of(node.module, lib):
                            violations.append(f"{rel}: from {node.module} import ... (line ~{node.lineno})")

    assert not violations, (
        f"Platform has {len(violations)} direct AI model import(s):\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nModel inference belongs in Core. Platform must go through CoreFacade or provider callbacks."
        "\nReference: docs/architecture/boundary-standard.md §铁律1"
    )
