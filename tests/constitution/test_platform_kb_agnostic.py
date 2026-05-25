"""
Architecture Constitution Tests: Platform KB Agnostic

Enforces boundary-standard.md §铁律2: Reusable capabilities belong in Core.
Platform's kb/intelligence/ must not implement:
- Document parsing (docx/pptx/md)
- Document classification
- Embedding cache layer
These are general capabilities that belong in core/harness/document/ or
core/harness/knowledge/.

Authoritative reference: docs/architecture/boundary-standard.md §3.1
"""

import ast
from pathlib import Path
from typing import Dict, List, Set

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
INTELLIGENCE_DIR = WORKSPACE_ROOT / "aiPlat-platform" / "kb" / "intelligence"

KNOWN_DEBT: Dict[str, str] = {
    "summarize.py": "summarize_document to be moved to core/apps/document_intelligence/summarizer.py",
}


def _module_functions(fp: Path) -> List[str]:
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    funcs: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node.name)
    return funcs


def _module_classes(fp: Path) -> List[str]:
    try:
        tree = ast.parse(fp.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    classes: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
    return classes


def _relative_path(fp: Path) -> str:
    try:
        return str(fp.relative_to(INTELLIGENCE_DIR))
    except ValueError:
        return str(fp)


def test_platform_kb_no_own_parsers():
    """Platform kb/intelligence/ must have no parser/classifier implementations."""
    violations: List[str] = []

    for fp in INTELLIGENCE_DIR.rglob("*.py"):
        if not fp.is_file() or "__pycache__" in str(fp):
            continue
        rel = _relative_path(fp)
        if rel in KNOWN_DEBT:
            continue
        funcs = _module_functions(fp)
        cls = _module_classes(fp)
        for fname in funcs:
            if fname.startswith("parse_") or fname.startswith("classify_") or fname.startswith("summarize_"):
                violations.append(f"{rel}::{fname}()")

    assert not violations, (
        f"Platform kb/intelligence/ has {len(violations)} parser/classifier function(s):\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nDocument parsing and classification are general capabilities. They belong in Core."
        "\nReference: docs/architecture/boundary-standard.md §铁律2"
    )


def test_platform_kb_no_own_embed_cache():
    """Platform kb/intelligence/ must not maintain its own embed cache layer."""
    violations: List[str] = []

    for fp in INTELLIGENCE_DIR.rglob("*.py"):
        if not fp.is_file() or "__pycache__" in str(fp):
            continue
        rel = _relative_path(fp)
        if rel in KNOWN_DEBT:
            continue
        funcs = _module_functions(fp)
        classes = _module_classes(fp)
        for cname in classes:
            if "cache" in cname.lower() or "embed" in cname.lower():
                violations.append(f"{rel}::class {cname}")

    assert not violations, (
        f"Platform kb/intelligence/ has {len(violations)} embed/cache class(es):\n" +
        "\n".join(f"  - {v}" for v in violations) +
        "\n\nEmbedding cache belongs in core/harness/knowledge/embedder.py."
        "\nReference: docs/architecture/boundary-standard.md §3.1"
    )
