#!/usr/bin/env python3
"""audit_doc_semantics.py — full automated factual spot-scan of active docs."""
from __future__ import annotations
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOTS = [REPO / "docs", REPO / "reports"]
for n in ("aiPlat-core", "aiPlat-infra", "aiPlat-platform", "aiPlat-management", "aiPlat-app"):
    p = REPO / n / "docs"
    if p.is_dir(): ROOTS.append(p)
ROOTS += [p for p in (REPO / "packages").glob("*/docs") if p.is_dir()]
STALE = ["docs/manuals/", "docs/whitepaper/", "docs/API/", "docs/matrix/", "docs/framework/",
         "docs/security/", "docs/policy/", "docs/compliance/", "docs/articles/",
         "docs/agents/", "docs/harness/", "docs/mcp/", "docs/skills/", "docs/tools/"]
STALE_NUM = {"954": "旧文档总数", "225": "旧 archive 断链数"}
PATH_RE = re.compile(r"`([^`\s]+\.(?:md|py|yaml|yml|json|sh|toml|ts|tsx|html|pdf|svg))`")

def active(p: Path) -> bool:
    """active。

    Args:
        p: p 参数。
    """
    return not any(x in p.parts for x in ("archive", "_archive", ".git", "node_modules", "__pycache__"))

files = [p for r in ROOTS for p in r.rglob("*.md") if active(p)]
missing, stale_paths, stale_numbers = [], [], []
for p in files:
    text = p.read_text(errors="ignore")
    rel = str(p.relative_to(REPO))
    skip_stale = ("docs/audit/" in rel or "DOCUMENT_SYSTEM.md" in rel)
    if "docs/audit/" in rel or "DOCUMENT_SYSTEM.md" in rel:
        continue
    for m in PATH_RE.finditer(text):
        raw = m.group(1).strip().split("#")[0].split("?")[0]
        if not raw.startswith(("docs/", "reports/", "scripts/", "packages/", "aiPlat-")):
            continue
        if not raw or any(x in raw for x in ("{", "}", "<", ">", "*", "...", "…", "客户", "示例")):
            continue
        if not (REPO / raw).exists() and not (p.parent / raw).exists():
            missing.append((rel, raw))
    if not skip_stale:
        for tok in STALE:
            if tok in text:
                stale_paths.append((rel, tok))
    for num, why in STALE_NUM.items():
        if re.search(rf"(?<!\d){num}(?!\d)", text):
            stale_numbers.append((rel, num, why))

print(f"active_docs={len(files)}")
print(f"missing_paths={len(missing)} stale_tokens={len(stale_paths)} stale_numbers={len(stale_numbers)}")
for rel, raw in missing[:25]: print(f"MISS {rel} :: {raw}")
for rel, tok in stale_paths[:15]: print(f"STALE {rel} :: {tok}")
for rel, num, why in stale_numbers[:15]: print(f"NUM {rel} :: {num} {why}")
