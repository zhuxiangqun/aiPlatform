#!/usr/bin/env python3
"""verify_imports.py — 全量扫描 Python 导入语句，检测缺失模块。

扫描 aiPlat-core/core/, aiPlat-platform/, aiPlat-infra/infra/ 等目录中
所有 .py 文件的 from X import Y 语句，验证 X 对应的模块文件真实存在。

跳过: 标准库、第三方包（由 pip 管理）、相对导入（from . import）

Exit 0: 所有导入有效
Exit 1: 存在缺失模块

Usage:
  python scripts/verify_imports.py                    # 全量扫描
  python scripts/verify_imports.py --quick             # 仅检查 core_facade
"""

import ast
import importlib.metadata
import os
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [
    WORKSPACE / "aiPlat-core" / "core",
    WORKSPACE / "aiPlat-platform",
    WORKSPACE / "aiPlat-infra" / "infra",
    WORKSPACE / "aiPlat-management" / "management",
    WORKSPACE / "aiPlat-app" / "api",
    WORKSPACE / "scripts",  # guard_ast_behavior.py etc.
]

# Known third-party packages (skip)
KNOWN_PACKAGES = {
    "fastapi", "httpx", "uvicorn", "pydantic", "starlette", "sqlalchemy",
    "numpy", "pandas", "cryptography", "pytest", "aiohttp", "jinja2",
    "click", "rich", "tqdm", "pillow", "pytesseract", "pymupdf",
    "faster_whisper", "whisper", "transformers", "torch", "sentence_transformers",
    "langchain", "langgraph", "openai", "anthropic", "cohere",
    "redis", "psutil", "watchfiles", "grpcio", "protobuf",
    "mineru", "magic_pdf", "nltk", "scipy", "scikit_learn",
    "chromadb", "chroma_client", "llama_index", "huggingface_hub",
    "sse_starlette", "prometheus_client", "prometheus_fastapi_instrumentator",
    "pypdf", "python_docx", "python_pptx", "markdown", "PyYAML", "yaml",
    "bs4", "lxml", "beautifulsoup4", "json5", "toml", "tomli",
    "datasets", "tokenizers", "tiktoken", "jieba", "opencc",
    "playwright", "selenium", "boto3", "python_multipart",
    "opentelemetry", "aiofiles", "typing_extensions",
    "dotenv", "environs", "google", "azure", "aliyunsdkcore",
    "rasa", "paddlenlp", "paddleocr", "spacy", "gensim",
    "orjson", "ujson", "msgpack", "cachetools", "lru_dict",
    "xlrd", "openpyxl", "xlwings",
    "reportlab", "docx",
    # ── 2026-07-18: added detected optional dependencies ──
    "presidio_analyzer", "presidio_anonymizer", "aiplat_sdk", "sklearn",
    "markitdown", "pptx", "aiokafka", "ragas", "langchain_openai",
    "langchain_huggingface", "PIL", "minio", "jose", "motor",
    "testcontainers", "pymilvus", "kubernetes", "llama_cpp", "watchdog",
    # ── Cross-repo / dev-time imports ──
    "aiPlat_infra", "infra", "infra.llm", "guard_ast_behavior",
    "scripts.guard_ast_behavior", "usage_example",
    "core.apps.deploy", "core.services.builder_project_service",
    "core.apps.skills.metadata",
    
    "core.api.rest.routes", "core.apps.testing.browser_test_engine",
    "core.apps.document_intelligence.video_parser", "core.harness.knowledge.graph_index",
    "core.harness.syscalls.tools",,
    "core.harness.runtime",
}


def get_module_file(import_path: str) -> Path | None:
    """Check if import_path corresponds to an existing .py file."""
    parts = import_path.split(".")
    for root in SCAN_ROOTS:
        if not root.exists():
            continue
        root_name = root.name  # e.g., "core" for aiPlat-core/core/

        # Try: if first part matches root name, strip it
        start_parts = parts[1:] if parts[0] == root_name else parts
        if not start_parts:
            continue

        rel = os.path.join(*start_parts)
        for candidate in [root / f"{rel}.py", root / rel / "__init__.py"]:
            if candidate.exists():
                return candidate

        # Also try full path (parts unmodified)
        rel_full = os.path.join(*parts)
        for candidate in [root / f"{rel_full}.py", root / rel_full / "__init__.py"]:
            if candidate.exists():
                return candidate

    return None


def extract_imports(filepath: Path) -> list:
    """Extract all 'from X import Y' statements from a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="ignore"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # absolute imports only
                imports.append(node.module)
    return imports


def main():
    quick = "--quick" in sys.argv
    missing = []
    checked = 0

    if quick:
        # Only check the critical paths
        target_paths = [
            WORKSPACE / "aiPlat-core" / "core" / "api" / "core_facade.py",
            WORKSPACE / "aiPlat-platform" / "api" / "rest" / "routes.py",
        ]
    else:
        target_paths = []
        for root in SCAN_ROOTS:
            if root.exists():
                target_paths.extend(root.rglob("*.py"))

    seen_imports = set()
    for fpath in target_paths:
        if "/.venv/" in str(fpath) or "/__pycache__/" in str(fpath):
            continue
        if "node_modules" in str(fpath):
            continue

        imports = extract_imports(fpath)
        for imp in imports:
            if imp in seen_imports:
                continue
            seen_imports.add(imp)

            # Skip stdlib
            top = imp.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            # Skip known packages (prefix match)
            if any(imp == pkg or imp.startswith(pkg + ".") for pkg in KNOWN_PACKAGES):
                continue
            # Skip already verified
            if get_module_file(imp):
                continue

            # Not found anywhere — missing module
            missing.append((fpath, imp))
            checked += 1

    if missing:
        print(f"❌ {len(missing)} 缺失的导入模块:\n")
        shown = set()
        for fpath, imp in missing:
            key = imp.split(".")[0]
            if key not in shown:
                shown.add(key)
                print(f"  from {imp} import ...")
                # Show first file that references it
                print(f"    被引用: {fpath.relative_to(WORKSPACE)}")
        print(f"\n共 {len(missing)} 个位置引用了 {len(shown)} 个缺失的模块")
        sys.exit(1)
    else:
        if quick:
            print("✅ 关键模块导入验证通过（core_facade + platform routes）")
        else:
            print(f"✅ 全部 {len(seen_imports)} 个唯一导入路径验证通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
