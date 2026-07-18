"""
Documentation API — 为前端文档系统提供目录树和 Markdown 内容。

支持类型: .md / .yaml / .json + 图片 (png/jpg/gif/svg/webp)

Routes:
  GET /api/docs/tree       → 返回完整目录树 JSON
  GET /api/docs/content    → 返回文档内容或图片 (?path=xxx)
  GET /api/docs/download   → 下载文档 (?path=xxx)
"""

import base64
import time
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pathlib import Path
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/docs", tags=["docs"])

_TEXT_EXT = {".md", ".yaml", ".yml", ".json", ".txt", ".py", ".toml"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
_DISPLAYABLE = _TEXT_EXT | _IMAGE_EXT

# ── Simple in-memory cache for the tree ──
_tree_cache: Dict[str, Any] = {}
_tree_cache_ts: float = 0.0
_TREE_CACHE_TTL = 60  # seconds


def _workspace_root() -> Path:
    mgmt_dir = Path(__file__).resolve().parents[1]
    return (mgmt_dir / ".." / "..").resolve()


def _docs_root() -> Path:
    return _workspace_root() / "docs"


# ── Sub-repo docs roots (auto-discovered) ──
def _discover_doc_roots() -> List[Dict[str, Any]]:
    roots = []
    ws = _workspace_root()
    for repo in ws.iterdir():
        if repo.is_dir() and not repo.name.startswith(".") and not repo.name.startswith("_"):
            docs_dir = repo / "docs"
            if docs_dir.exists() and docs_dir != _docs_root():
                roots.append({"name": repo.name, "root": docs_dir})
    return roots


def _is_safe(path: str) -> bool:
    return ".." not in path and not path.startswith("/")


# ── Document category classification — intent-first ──
# Rules: (set_of_path_segments, category_key). First segment match wins.
# Files inherit parent directory category via upward path search.
_CATEGORY = {
    "gov": "📜 核心规约",
    "arch": "🏗️ 架构设计",
    "layers": "📋 层设计",
    "manuals": "📖 用户手册",
    "design": "🎨 设计方案",
    "knowledge": "🧠 知识引擎（本体·RAG·记忆 — AI 工程专项参考）",
    "compliance": "🔒 合规与安全",
    "tools": "🛠️ 工具与框架",
    "reports": "📄 报告与审计",
}

_CATEGORY_RULES: List[tuple] = [
    # ── Core governance ──
    (("ws", "by-role"), "gov"),
    # ── Architecture design ──
    (("architecture", "contracts", "harness", "agents", "skills",
      "kernel_orchestrator", "runtime", "services", "framework",
      "errors", "apps", "adapters", "evaluation", "interfaces",
      "learning_loop", "decisions", "plans", "core", "assets", "diagrams", "ops"), "arch"),
    # ── Layer designs ──
    (("api", "auth", "gateway", "database", "cache", "compute",
      "llm", "http", "deployment", "storage", "network", "vector",
      "di", "config", "messaging", "billing", "observability",
      "monitoring", "logging", "tenants", "registry", "user", "utils",
      "infra", "platform", "management"), "layers"),
    # ── User manuals ──
    (("manuals", "guides", "getting-started",
      "examples", "bid-review", "onboarding"), "manuals"),
    # ── Design proposals ──
    (("design",), "design"),
    # ── Knowledge engine ──
    (("knowledge", "memory", "ontology_engine", "graph_index"), "knowledge"),
    # ── Compliance & security ──
    (("compliance", "security", "policy", "governance"), "compliance"),
    # ── Tools & frameworks ──
    (("tools", "testing", "mcp", "standards", "API",
      "document_intelligence"), "tools"),
    # ── Reports & audit ──
    (("reports", "audit", "project", "archive", "strategy",
      "articles", "whitepaper"), "reports"),
]


def _classify(path: str, is_dir: bool) -> str:
    """Classify by upward path segment match. Files inherit parent dir category.
    Top-level governance files get 'gov' category."""
    segments = path.split("/")
    for i in range(len(segments), 0, -1):
        prefix = segments[i - 1]
        for prefixes, cat in _CATEGORY_RULES:
            if prefix in prefixes:
                return cat
    # Top-level governance files
    if len(segments) == 1 and not is_dir:
        name = segments[0]
        if name in ("CLAUDE.md", "DOCUMENT_SYSTEM.md", "README.md"):
            return "gov"
        if any(name.startswith(p) for p in ("AIPLAT_CAPABILITIES", "AIPLAT_ROADMAP")):
            return "gov"
    return ""


# ── Extra roots: workspace-level key docs ──

_EXTRA_ROOTS: List[Dict[str, Any]] = [
    {"name": "CLAUDE.md", "path": "./CLAUDE.md", "root": _workspace_root(), "label": "工作区规约"},
    {"name": "CAPABILITIES.md", "path": "./AIPLAT_CAPABILITIES.md", "root": _workspace_root(), "label": "能力清单"},
    {"name": "ROADMAP.md", "path": "./AIPLAT_ROADMAP.md", "root": _workspace_root(), "label": "路线图"},
    {"name": "Core CLAUDE.md", "path": "./aiPlat-core/CLAUDE.md", "root": _workspace_root(), "label": "Core 规约"},
    {"name": "Platform CLAUDE.md", "path": "./aiPlat-platform/CLAUDE.md", "root": _workspace_root(), "label": "Platform 规约"},
    {"name": "Infra CLAUDE.md", "path": "./aiPlat-infra/CLAUDE.md", "root": _workspace_root(), "label": "Infra 规约"},
    {"name": "Management CLAUDE.md", "path": "./aiPlat-management/CLAUDE.md", "root": _workspace_root(), "label": "Management 规约"},
]


def _build_tree(dir_path: Path, prefix: str = "") -> List[Dict[str, Any]]:
    items = []
    try:
        entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return items

    for entry in entries:
        name = entry.name
        if name.startswith(".") or name == "__pycache__" or name == "node_modules":
            continue

        rel_path = f"{prefix}/{name}" if prefix else name

        if entry.is_dir():
            children = _build_tree(entry, rel_path)
            cat = _classify(rel_path, True)
            if children:
                items.append({
                    "name": name, "path": rel_path, "type": "directory", "children": children,
                    "category": cat,
                })
            elif cat:
                items.append({
                    "name": name, "path": rel_path, "type": "directory", "children": [],
                    "category": cat,
                })
        elif entry.suffix in _DISPLAYABLE:
            label = name if entry.suffix in _TEXT_EXT else f"{name} 🖼"
            cat = _classify(rel_path, False)
            items.append({
                "name": label, "path": rel_path, "type": "file",
                "category": cat,
            })

    return items


def _merge_tree(main: list, sub: list) -> None:
    """Merge sub-tree items into main tree in-place. Directories merge their children, files dedupe by name."""
    if not sub or not main:
        return
    main_names = {(m["name"], m["type"]) for m in main}
    for sub_item in sub:
        key = (sub_item["name"], sub_item["type"])
        if key not in main_names:
            main.append(sub_item)
            main_names.add(key)
        elif sub_item["type"] == "directory":
            existing = next(m for m in main if m["name"] == sub_item["name"] and m["type"] == "directory")
            _merge_tree(existing.get("children", []), sub_item.get("children", []))


@router.get("/tree")
async def get_docs_tree(exclude_archive: bool = Query(True)) -> Dict[str, Any]:
    """Return the docs/ directory tree, plus extra workspace-level key docs."""
    global _tree_cache, _tree_cache_ts
    _now = time.time()

    # Cache for quick reload
    cache_key = f"tree_{exclude_archive}"
    if cache_key in _tree_cache and (_now - _tree_cache_ts) < _TREE_CACHE_TTL:
        return _tree_cache[cache_key]

    root = _docs_root()
    tree = _build_tree(root)

    # Exclude archive by default
    if exclude_archive:
        tree = [t for t in tree if t.get("name") != "archive"]

    # ── Inject extra roots directly (no virtual directory nesting) ──
    gov_items = []
    for er in _EXTRA_ROOTS:
        full = er["root"] / er["path"]
        if full.exists():
            gov_items.append({"name": er["name"], "path": er["path"], "type": "file", "category": "gov"})
    tree[0:0] = gov_items

    # ── Merge sub-repo docs into main tree ──
    for extra in _discover_doc_roots():
        extra_root = extra["root"]
        if extra_root.exists():
            subtree = _build_tree(extra_root)
            if subtree:
                _merge_tree(tree, subtree)

    result = {"tree": tree, "root": str(root), "categories": _CATEGORY}
    _tree_cache[cache_key] = result
    _tree_cache_ts = _now
    return result


@router.get("/content", response_model=None)
async def get_doc_content(
    path: str = Query("README.md"),
    base64_encode: bool = Query(False),
) -> Response | Dict[str, Any]:
    """Return a document's content. Returns JSON for text, raw binary for images.

    For workspace-level docs (like CLAUDE.md, AIPLAT_CAPABILITIES.md),
    path resolves from the workspace root.
    For standard docs, path resolves from docs/.
    """
    if not _is_safe(path):
        raise HTTPException(status_code=400, detail="Invalid path")

    # Try extra roots first (workspace-level files)
    full_path = None
    for er in _EXTRA_ROOTS:
        if path == er["path"]:
            full_path = er["root"] / er["path"]
            break

    # Fall back to docs/
    if full_path is None:
        full_path = _docs_root() / path

    # Try sub-repo docs roots as fallback (merged tree — same path, different root)
    if not full_path.exists():
        for extra in _discover_doc_roots():
            candidate = extra["root"] / path
            if candidate.exists():
                full_path = candidate
                break

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")

    suffix = full_path.suffix.lower()

    # ── Images: return binary ──
    if suffix in _IMAGE_EXT:
        media_map = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".svg": "image/svg+xml", ".webp": "image/webp",
        }
        content_type = media_map.get(suffix, "application/octet-stream")
        return Response(content=full_path.read_bytes(), media_type=content_type)

    # ── Text files ──
    if suffix not in _TEXT_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    try:
        content = full_path.read_text(encoding="utf-8", errors="replace")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read: {e}")

    return {
        "path": path,
        "name": full_path.stem,
        "suffix": suffix,
        "content": content,
        "size": len(content),
    }


@router.get("/download")
async def download_doc(path: str = Query("README.md")):
    """Return a document as a file download with Content-Disposition attachment.

    Resolves path identically to /content: workspace-level files from
    workspace root, standard docs from docs/ directory.
    """
    if not _is_safe(path):
        raise HTTPException(status_code=400, detail="Invalid path")

    full_path = None
    # Try extra roots (workspace-level files)
    if full_path is None:
        for er in _EXTRA_ROOTS:
            if path == er["path"]:
                full_path = er["root"] / er["path"]
                break

    if full_path is None:
        full_path = _docs_root() / path

    # Try sub-repo docs roots as fallback (merged tree — same path, different root)
    if not full_path.exists():
        for extra in _discover_doc_roots():
            candidate = extra["root"] / path
            if candidate.exists():
                full_path = candidate
                break

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"Document not found: {path}")

    suffix = full_path.suffix.lower()

    media_map = {
        ".md": "text/markdown",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".json": "application/json",
        ".txt": "text/plain",
        ".py": "text/x-python",
        ".toml": "text/plain",
    }

    try:
        content = full_path.read_bytes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read: {e}")

    content_type = media_map.get(suffix, "application/octet-stream")
    filename = full_path.name

    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
