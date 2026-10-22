#!/usr/bin/env python3
"""
verify_capability_doc.py — CAPABILITIES 声明路径 ↔ 源码存在性审计

源码为真：本脚本只验证文档声明的 path / path:line 是否对应仓库中的真实文件与行号范围。
不能证明符号语义、生产调用方或行为可用。

用法:
  python3 scripts/verify_capability_doc.py            # 默认：报告到 stdout，exit 0，不写文件
  python3 scripts/verify_capability_doc.py --write    # 额外写入 docs/audit/latest.{json,md}
  python3 scripts/verify_capability_doc.py --ci       # file_missing>0 或 line_bad>0 时 exit 1
                                                      # （软警告 ambiguous 不单独导致非零）

逐条记录字段:
  source, raw_path, resolved_path, resolve_mode, line, status, name
  resolve_mode: exact | candidate_root | basename_unique | ambiguous | unresolved
  status: ok | file_missing | line_bad | ambiguous | unresolved

计数:
  file_missing 与 ambiguous 互斥；ambiguous 在 total 分母中、不计入 file_ok。
  line_valid_rate 仅对「带行号且文件已解析」子集；无此类引用时为 null。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = PROJECT_ROOT / "AIPLAT_CAPABILITIES.md"
AUDIT_DIR = PROJECT_ROOT / "docs" / "audit"
OUTPUT_JSON = AUDIT_DIR / "latest.json"
OUTPUT_MD = AUDIT_DIR / "latest.md"

CANDIDATE_ROOTS = [
    "aiPlat-core/core",
    "aiPlat-core",
    "aiPlat-platform",
    "aiPlat-infra/infra",
    "aiPlat-infra",
    "aiPlat-management",
    "aiPlat-app",
]

_SEGMENT_ROOTS = {
    "core": ["aiPlat-core/core", "aiPlat-core"],
    "platform": ["aiPlat-platform"],
    "infra": ["aiPlat-infra/infra", "aiPlat-infra"],
    "apps": ["aiPlat-core/core/apps", "aiPlat-platform/apps", "aiPlat-core"],
    "harness": ["aiPlat-core/core"],
    "api": ["aiPlat-core/core", "aiPlat-platform"],
    "management": ["aiPlat-infra/infra", "aiPlat-management", "aiPlat-core"],
    "builder": ["aiPlat-platform"],
    "evaluation": ["aiPlat-core/core"],
    "gates": ["aiPlat-core/core/harness/infrastructure", "aiPlat-core/core"],
    "coordination": ["aiPlat-core/core/harness"],
    "loop": ["aiPlat-core/core/harness/execution", "aiPlat-core/core/adapters/llm"],
    "ontology_engine": ["aiPlat-core/core/harness"],
    "frontend": ["aiPlat-management/frontend/src", "aiPlat-management/frontend"],
    "syscalls": ["aiPlat-core/core/harness"],
    "subagent": ["aiPlat-core/core/harness/coordination"],
    "kb": ["aiPlat-platform"],
}

_EXCLUDE_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".mypy_cache", ".ruff_cache", "tmp"}

_file_index_cache: Optional[Dict[str, List[Path]]] = None


def _build_file_index() -> Dict[str, List[Path]]:
    global _file_index_cache
    if _file_index_cache is not None:
        return _file_index_cache
    index: Dict[str, List[Path]] = {}
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in filenames:
            index.setdefault(fn, []).append(Path(dirpath) / fn)
    _file_index_cache = index
    return index


def _iter_path_blocks(text: str) -> List[Tuple[str, str, int]]:
    """frontmatter: - id: xxx + paths: - path::line → (cap_id, path, line)."""
    refs: List[Tuple[str, str, int]] = []
    ids = list(re.finditer(r"^\s*-\s*id:\s*(\S+)", text, re.M))
    for i, id_m in enumerate(ids):
        cap_id = id_m.group(1)
        seg_start = id_m.end()
        seg_end = ids[i + 1].start() if i + 1 < len(ids) else len(text)
        seg = text[seg_start:seg_end]
        for p in re.finditer(r"-\s*([\w\-\./]+\.(?:py|tsx?|yaml|yml|json|sh|sql|md))::(\d+)", seg):
            refs.append((cap_id, p.group(1), int(p.group(2))))
    return refs


def _parse_table_rows(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or s.startswith("|--") or s.startswith("|---") or s.startswith("|:"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 5:
            continue
        name, loc, status, impl = cols[0], cols[1], cols[2], cols[4]
        if name in ("能力", "名称", "模块", "能力/端点"):
            continue
        m = re.search(r"([\w\-\./]+\.(?:py|tsx?|yaml|yml|json|sh|sql|md))(?::(\d+))?", loc)
        if not m:
            continue
        rows.append({
            "name": name,
            "path": m.group(1),
            "line": int(m.group(2)) if m.group(2) else None,
            "status_mark": status,
            "impl": impl,
        })
    return rows


def _display_path(real: Optional[Path]) -> Optional[str]:
    """Prefer repo-relative path; fall back to absolute for ~/.aiplat etc."""
    if real is None:
        return None
    try:
        return str(real.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(real)


def resolve_path_detailed(rel: str) -> Tuple[Optional[Path], str]:
    """Return (path_or_None, resolve_mode)."""
    if rel.startswith("~"):
        p = Path(os.path.expanduser(rel))
        if p.is_file():
            return p, "exact"
    if rel.startswith(".aiplat") or rel.startswith("/.aiplat"):
        p = Path.home() / rel.lstrip("/")
        if p.is_file():
            return p, "exact"
    if rel.endswith(".yaml") and "/" not in rel:
        home_ont = Path.home() / ".aiplat" / "ontologies" / rel
        if home_ont.is_file():
            return home_ont, "exact"

    if rel.startswith("aiPlat-"):
        c = PROJECT_ROOT / rel
        if c.is_file():
            return c, "exact"

    seg = rel.split("/", 1)[0]
    for root in _SEGMENT_ROOTS.get(seg, []):
        c = PROJECT_ROOT / root / rel
        if c.is_file():
            return c, "candidate_root"

    if seg in ("platform", "core", "infra", "apps"):
        rest = rel.split("/", 1)[1] if "/" in rel else rel
        for repo in ("aiPlat-platform", "aiPlat-core", "aiPlat-infra"):
            for c in (PROJECT_ROOT / repo / rest, PROJECT_ROOT / repo / rel):
                if c.is_file():
                    return c, "candidate_root"

    for root in CANDIDATE_ROOTS:
        c = PROJECT_ROOT / root / rel
        if c.is_file():
            return c, "candidate_root"

    c = PROJECT_ROOT / rel
    if c.is_file():
        return c, "exact"

    basename = rel.split("/")[-1]
    if basename and "." in basename:
        hits = _build_file_index().get(basename, [])
        if len(hits) == 1:
            return hits[0], "basename_unique"
        if len(hits) > 1:
            return None, "ambiguous"
    return None, "unresolved"


def resolve_path(rel: str) -> Optional[Path]:
    p, _mode = resolve_path_detailed(rel)
    return p


def _line_count(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1


def _grep_field_in_engine(field: str) -> int:
    engine = PROJECT_ROOT / "aiPlat-core" / "core" / "harness" / "execution" / "pipeline_engine.py"
    if not engine.is_file():
        return 0
    try:
        text = engine.read_text(encoding="utf-8", errors="ignore")
        return len(re.findall(re.escape(field), text))
    except Exception:
        return 0


def audit(doc_path: Path) -> Dict[str, Any]:
    """Audit CAPABILITIES path declarations against the filesystem (source of truth)."""
    text = doc_path.read_text(encoding="utf-8")

    total_declared = None
    m = re.search(r"^total_capabilities:\s*(\d+)", text, re.M)
    if m:
        total_declared = int(m.group(1))

    markers = {
        "ok": len(re.findall(r"✅", text)),
        "warn": len(re.findall(r"⚠️", text)),
        "todo": len(re.findall(r"❌", text)),
    }

    # Per-record list — do NOT dedupe across sources (table vs frontmatter)
    records: List[Dict[str, Any]] = []

    for cap_id, path, line in _iter_path_blocks(text):
        real, mode = resolve_path_detailed(path)
        rec: Dict[str, Any] = {
            "source": "frontmatter",
            "name": cap_id,
            "raw_path": path,
            "resolved_path": _display_path(real),
            "resolve_mode": mode,
            "line": line,
            "status": "ok",
        }
        if mode == "ambiguous":
            rec["status"] = "ambiguous"
        elif real is None:
            rec["status"] = "file_missing" if mode == "unresolved" else "file_missing"
            if mode == "unresolved":
                rec["status"] = "unresolved"
        elif line and line > 0:
            total = _line_count(real)
            if total > 0 and line > total:
                rec["status"] = "line_bad"
                rec["file_lines"] = total
        if mode == "basename_unique" and rec["status"] == "ok":
            rec["soft_warning"] = "basename_unique"
        records.append(rec)

    for r in _parse_table_rows(text):
        path = r["path"]
        line = r["line"]
        real, mode = resolve_path_detailed(path)
        rec = {
            "source": "table",
            "name": r["name"],
            "raw_path": path,
            "resolved_path": _display_path(real),
            "resolve_mode": mode,
            "line": line,
            "status": "ok",
            "impl": r.get("impl"),
        }
        if mode == "ambiguous":
            rec["status"] = "ambiguous"
        elif real is None:
            rec["status"] = "unresolved" if mode == "unresolved" else "file_missing"
        elif line and line > 0:
            total = _line_count(real)
            if total > 0 and line > total:
                rec["status"] = "line_bad"
                rec["file_lines"] = total
        if mode == "basename_unique" and rec["status"] == "ok":
            rec["soft_warning"] = "basename_unique"
        records.append(rec)

    # Counts — ambiguous mutually exclusive with file_missing
    total_refs = len(records)
    file_ok = sum(1 for x in records if x["status"] == "ok" or x.get("soft_warning") == "basename_unique" and x["status"] == "ok")
    # basename_unique with ok still counts as file_ok
    file_ok = sum(1 for x in records if x["status"] == "ok")
    file_missing = sum(1 for x in records if x["status"] in ("file_missing", "unresolved"))
    ambiguous_count = sum(1 for x in records if x["status"] == "ambiguous")
    line_bad = sum(1 for x in records if x["status"] == "line_bad")

    # line_ok / line_valid only over records with line and resolved file
    lined = [
        x for x in records
        if x.get("line") and x["line"] > 0 and x["status"] in ("ok", "line_bad")
    ]
    line_ok = sum(1 for x in lined if x["status"] == "ok")
    if not lined:
        line_valid_rate: Optional[float] = None
    else:
        line_valid_rate = round(line_ok / len(lined), 4)

    file_exist_rate = round(file_ok / total_refs, 4) if total_refs else 0.0

    table_rows = [x for x in records if x["source"] == "table"]
    impl_counter = Counter(x.get("impl") or "" for x in table_rows)
    merged = sum(v for k, v in impl_counter.items() if k == "已合入")
    phase_tagged = sum(v for k, v in impl_counter.items() if re.match(r"^Phase\s+\d", k or ""))
    other_impl = len(table_rows) - merged - phase_tagged

    auto_gen = len(re.findall(r"Auto-generated by scan_inherited_capabilities", text))
    merge_note = len(re.findall(r"Merge into AIPLAT_CAPABILITIES\.md after review", text))

    orphan_fields = re.findall(
        r"Schema defines '(\w+)' but pipeline_engine never reads it", text)
    orphan_recheck = []
    for f in orphan_fields:
        hit = _grep_field_in_engine(f)
        orphan_recheck.append({"field": f, "still_orphan": not hit, "engine_hits": hit})

    missing_files = sorted({
        x["raw_path"] for x in records if x["status"] in ("file_missing", "unresolved")
    })
    out_of_range = [
        {
            "name": x["name"],
            "path": x["raw_path"],
            "line": x["line"],
            "file_lines": x.get("file_lines"),
            "source": x["source"],
        }
        for x in records if x["status"] == "line_bad"
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "doc": str(doc_path),
        "total_declared": total_declared,
        "markers": markers,
        "records": records,
        "refs": {
            "total_records": total_refs,
            "frontmatter": sum(1 for x in records if x["source"] == "frontmatter"),
            "table": sum(1 for x in records if x["source"] == "table"),
            "file_ok": file_ok,
            "file_missing": file_missing,
            "ambiguous_count": ambiguous_count,
            "line_ok": line_ok,
            "line_bad": line_bad,
            "lined_subset": len(lined),
            # backward-compat alias used by older callers
            "unique_total": total_refs,
        },
        "missing_files": missing_files,
        "out_of_range": out_of_range,
        "impl": {
            "merged": merged,
            "phase_tagged": phase_tagged,
            "other": other_impl,
        },
        "fragments": {"auto_generated": auto_gen, "merge_after_review": merge_note},
        "orphan_recheck": orphan_recheck,
        "rates": {
            "file_exist": file_exist_rate,
            "line_valid": line_valid_rate,  # null when no lined subset
            "impl": round(merged / max(1, total_refs), 4),
            # completion removed as CI gate; kept informational without merged/refs inflation
            "completion": file_exist_rate,
        },
    }


def render_markdown(r: Dict[str, Any]) -> str:
    L = []
    L.append("# aiPlat 能力审计报告")
    L.append("")
    L.append(f"**生成时间**: {r['generated_at']}")
    L.append(f"**文档**: `{r['doc']}`")
    L.append("")
    L.append("> 源码为真：本报告只核对声明路径/行号与仓库文件；不能证明接线或行为可用。")
    L.append("")
    L.append("## 一、概要")
    L.append("")
    L.append(f"- 头部声明 `total_capabilities`: **{r['total_declared']}**")
    L.append(f"- 标记分布：✅ {r['markers']['ok']} · ⚠️ {r['markers']['warn']} · ❌ {r['markers']['todo']}")
    L.append(
        f"- 逐条引用: **{r['refs']['total_records']}**"
        f"（frontmatter {r['refs']['frontmatter']} + 表格 {r['refs']['table']}；不去重）"
    )
    L.append("")
    L.append("## 二、文件存在率 / 行号有效率")
    L.append("")
    lv = r["rates"]["line_valid"]
    lv_s = "N/A" if lv is None else f"{lv * 100:.1f}%"
    L.append(f"- 文件存在率 file_ok/total: **{r['rates']['file_exist'] * 100:.1f}%** "
             f"（ok={r['refs']['file_ok']}, missing={r['refs']['file_missing']}, "
             f"ambiguous={r['refs']['ambiguous_count']}；ambiguous 在分母、不进 ok）")
    L.append(f"- 行号有效率（有行号且已解析子集）: **{lv_s}** "
             f"（subset={r['refs']['lined_subset']}, line_bad={r['refs']['line_bad']}）")
    L.append("")
    L.append("## 三、文件引用")
    L.append("")
    L.append(f"- 文件存在 (ok): **{r['refs']['file_ok']}**")
    L.append(f"- 文件缺失: **{r['refs']['file_missing']}**")
    L.append(f"- 歧义 basename: **{r['refs']['ambiguous_count']}**（软警告，不计 missing）")
    L.append(f"- 行号越界: **{r['refs']['line_bad']}**")
    L.append("")
    if r["missing_files"]:
        L.append("### 缺失文件清单")
        L.append("")
        for f in r["missing_files"][:40]:
            L.append(f"- `{f}`")
    else:
        L.append("### 缺失文件清单：无")
    L.append("")
    if r["out_of_range"]:
        L.append("### 行号越界清单")
        L.append("")
        for o in r["out_of_range"][:40]:
            L.append(f"- `{o['path']}:{o['line']}`（文件仅 {o.get('file_lines')} 行，source={o.get('source')}）")
    L.append("")
    L.append("## 四、实施状态分布（表格行）")
    L.append("")
    L.append(f"- 已合入: **{r['impl']['merged']}**")
    L.append(f"- Phase 标记: **{r['impl']['phase_tagged']}**")
    L.append(f"- 其它: **{r['impl']['other']}**")
    L.append("")
    L.append("---")
    L.append("*scripts/verify_capability_doc.py — 默认不写盘；`--write` 才落盘。*")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    ci = "--ci" in argv
    write = "--write" in argv

    print("aiPlat CAPABILITIES path audit (source of truth = repo files)")
    print(f"doc: {DOC_PATH}")
    print("-" * 50)

    if not DOC_PATH.exists():
        print(f"ERROR: missing {DOC_PATH}")
        return 1 if ci else 0

    r = audit(DOC_PATH)

    if write:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_JSON.write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        OUTPUT_MD.write_text(render_markdown(r), encoding="utf-8")
        print(f"wrote {OUTPUT_JSON}")
        print(f"wrote {OUTPUT_MD}")

    lv = r["rates"]["line_valid"]
    lv_s = "N/A" if lv is None else f"{lv * 100:.1f}%"
    print(
        f"records={r['refs']['total_records']} "
        f"file_ok={r['refs']['file_ok']} missing={r['refs']['file_missing']} "
        f"ambiguous={r['refs']['ambiguous_count']} line_bad={r['refs']['line_bad']} "
        f"file_exist={r['rates']['file_exist'] * 100:.1f}% line_valid={lv_s}"
    )

    hard_fail = r["refs"]["file_missing"] > 0 or r["refs"]["line_bad"] > 0
    if hard_fail:
        print(
            f"HARD findings: file_missing={r['refs']['file_missing']} "
            f"line_bad={r['refs']['line_bad']}"
        )
        if r["missing_files"]:
            for f in r["missing_files"][:20]:
                print(f"  missing: {f}")
        for o in r["out_of_range"][:20]:
            print(f"  line_bad: {o['path']}:{o['line']}")

    if r["refs"]["ambiguous_count"]:
        print(f"SOFT: ambiguous_count={r['refs']['ambiguous_count']} (not a --ci failure alone)")

    if ci and hard_fail:
        print("CI FAIL")
        return 1
    if ci:
        print("CI PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
