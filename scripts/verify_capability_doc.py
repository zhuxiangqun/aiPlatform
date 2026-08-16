#!/usr/bin/env python3
"""
verify_capability_doc.py — aiPlat 元治理审计脚本（阶段 0）

功能：只读扫描 AIPLAT_CAPABILITIES.md，审计能力登记与代码文件的一致性。
     产出 docs/audit/latest.json + docs/audit/latest.md。

用法：
  python scripts/verify_capability_doc.py           # 生成报表
  python scripts/verify_capability_doc.py --ci      # 落地完成度 < 80% 时 exit 1

审计项：
  1. header total_capabilities vs 实际 ✅/⚠️/❌ 计数
  2. 文件引用是否存在（相对路径回推 6 个候选根）
  3. 行号是否越界（行号 <= 文件总行数，轻量模式）
  4. "已合入" vs "Phase XX" 分布
  5. 未合并的 auto-generated 碎片
  6. 过期自审计（ORPHAN 12 字段）复验
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 配置 ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = PROJECT_ROOT / "AIPLAT_CAPABILITIES.md"
AUDIT_DIR = PROJECT_ROOT / "docs" / "audit"
OUTPUT_JSON = AUDIT_DIR / "latest.json"
OUTPUT_MD = AUDIT_DIR / "latest.md"

CI_THRESHOLD = 0.80  # --ci 门禁：落地完成度低于此值 exit 1

FILE_EXT = r"(?:py|tsx?|yaml|yml|json|sh|sql|md)"

# 相对路径回推候选根（表格里的路径丢了 aiPlat-core/core/ 前缀）
CANDIDATE_ROOTS = [
    "aiPlat-core/core",
    "aiPlat-core",
    "aiPlat-platform",
    "aiPlat-infra/infra",
    "aiPlat-infra",
    "aiPlat-management",
    "aiPlat-app",
]

# 首段映射（文档混用 core/...、platform/...、infra/...、frontend/... 等短约定）
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

_EXCLUDE_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", "build", ".mypy_cache", ".ruff_cache"}

_file_index_cache: Optional[Dict[str, List[Path]]] = None


def _build_file_index() -> Dict[str, List[Path]]:
    """一次性扫描仓库，建立 basename → 全路径列表 索引（排除重目录）。"""
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


# ── 解析器 ──────────────────────────────────────────────
def _iter_path_blocks(text: str) -> List[Tuple[str, str]]:
    """frontmatter 格式：- id: xxx + paths: - path::line。

    返回 [(capability_id, path, line), ...]
    """
    refs: List[Tuple[str, str]] = []
    ids = list(re.finditer(r"^\s*-\s*id:\s*(\S+)", text, re.M))
    for i, id_m in enumerate(ids):
        cap_id = id_m.group(1)
        seg_start = id_m.end()
        seg_end = ids[i + 1].start() if i + 1 < len(ids) else len(text)
        seg = text[seg_start:seg_end]
        for p in re.finditer(r"-\s*([\w\-\./]+\.(?:py|tsx?|yaml|yml|json|sh|sql|md))::(\d+)", seg):
            refs.append((cap_id, p.group(1), int(p.group(2))))
    return refs


def _parse_table_rows(text: str) -> List[Dict]:
    """表格格式：| 能力 | 位置 | 状态 | 说明 | 实施状态 |。

    返回 [{name, path, line, status, impl}]
    """
    rows: List[Dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|") or s.startswith("|--") or s.startswith("|---") or s.startswith("|:"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 5:
            continue
        name, loc, status, impl = cols[0], cols[1], cols[2], cols[4]
        if name in ("能力", "名称", "模块", "能力/端点"):
            continue  # 表头
        # 位置列可能含反引号 / `+` 拼接 / 范围 :a-b，只取第一个文件片段
        m = re.search(r"([\w\-\./]+\.(?:py|tsx?|yaml|yml|json|sh|sql|md))(?::(\d+))?", loc)
        if not m:
            continue
        rows.append({
            "name": name,
            "path": m.group(1),
            "line": int(m.group(2)) if m.group(2) else 0,
            "status": status,
            "impl": impl,
        })
    return rows


def resolve_path(rel: str) -> Optional[Path]:
    """把文档里的路径解析成真实文件（None = 不存在）。"""
    # 处理 home 目录引用（~/.aiplat/... 或 /.aiplat/... 或 .aiplat/...）
    if rel.startswith("~"):
        p = Path(os.path.expanduser(rel))
        if p.is_file():
            return p
    if rel.startswith(".aiplat") or rel.startswith("/.aiplat"):
        p = Path.home() / rel.lstrip("/")
        if p.is_file():
            return p
    # 本体 YAML（~/.aiplat/ontologies/ 下，文档可能只写 basename）
    if rel.endswith(".yaml") and "/" not in rel:
        home_ont = Path.home() / ".aiplat" / "ontologies" / rel
        if home_ont.is_file():
            return home_ont
    # 已是完整路径（含 aiPlat- 前缀）
    if rel.startswith("aiPlat-"):
        c = PROJECT_ROOT / rel
        if c.is_file():
            return c
    # 首段映射（文档混用 core/...、platform/...、infra/...、frontend/... 等短约定）
    seg = rel.split("/", 1)[0]
    for root in _SEGMENT_ROOTS.get(seg, []):
        c = PROJECT_ROOT / root / rel
        if c.is_file():
            return c
    # repo 短名回推：platform/... → aiPlat-platform/...（strip 首段）
    if seg in ("platform", "core", "infra", "apps"):
        rest = rel.split("/", 1)[1] if "/" in rel else rel
        for repo in ("aiPlat-platform", "aiPlat-core", "aiPlat-infra"):
            c = PROJECT_ROOT / repo / rest
            if c.is_file():
                return c
            c = PROJECT_ROOT / repo / rel
            if c.is_file():
                return c
    # 候选根回推
    for root in CANDIDATE_ROOTS:
        c = PROJECT_ROOT / root / rel
        if c.is_file():
            return c
    # 直接
    c = PROJECT_ROOT / rel
    if c.is_file():
        return c
    # 兜底：按 basename 在仓库索引里唯一匹配（处理纯文件名/短路径引用）
    basename = rel.split("/")[-1]
    if basename and "." in basename:
        hits = _build_file_index().get(basename, [])
        if len(hits) == 1:
            return hits[0]
    return None


def _line_count(path: Path) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1


# ── 主审计 ──────────────────────────────────────────────
def audit(doc_path: Path) -> Dict:
    text = doc_path.read_text(encoding="utf-8")

    # 1. marker 计数
    total_declared = None
    m = re.search(r"^total_capabilities:\s*(\d+)", text, re.M)
    if m:
        total_declared = int(m.group(1))

    markers = {
        "ok": len(re.findall(r"✅", text)),
        "warn": len(re.findall(r"⚠️", text)),
        "todo": len(re.findall(r"❌", text)),
    }

    # 2. 解析引用（frontmatter + 表格），按 (path, line) 去重
    fm_refs = _iter_path_blocks(text)
    table_rows = _parse_table_rows(text)

    unique_refs: Dict[Tuple[str, int], str] = {}
    for cap_id, path, line in fm_refs:
        unique_refs.setdefault((path, line), cap_id)
    for r in table_rows:
        unique_refs.setdefault((r["path"], r["line"]), r["name"])

    # 3. 逐条校验
    file_ok = 0
    file_missing = 0
    line_ok = 0
    line_bad = 0
    missing_files: List[str] = []
    out_of_range: List[Dict] = []

    for (path, line), name in unique_refs.items():
        real = resolve_path(path)
        if real is None:
            file_missing += 1
            missing_files.append(path)
            continue
        file_ok += 1
        if line == 0:
            line_ok += 1  # 无行号，只校验文件存在
            continue
        total = _line_count(real)
        if total > 0 and line <= total:
            line_ok += 1
        else:
            line_bad += 1
            out_of_range.append({"name": name, "path": path, "line": line, "file_lines": total})

    # 4. 实施状态分布
    impl_counter = Counter(r["impl"] for r in table_rows)
    merged = sum(v for k, v in impl_counter.items() if k == "已合入")
    phase_tagged = sum(v for k, v in impl_counter.items() if re.match(r"^Phase\s+\d", k))
    other_impl = len(table_rows) - merged - phase_tagged

    # 5. 未合并碎片
    auto_gen = len(re.findall(r"Auto-generated by scan_inherited_capabilities", text))
    merge_note = len(re.findall(r"Merge into AIPLAT_CAPABILITIES\.md after review", text))

    # 6. ORPHAN 自审计复验
    orphan_fields = re.findall(
        r"Schema defines '(\w+)' but pipeline_engine never reads it", text)
    orphan_recheck = []
    if orphan_fields:
        for f in orphan_fields:
            # 只读 grep pipeline_engine.py 里该字段的引用
            hit = _grep_field_in_engine(f)
            orphan_recheck.append({"field": f, "still_orphan": not hit, "engine_hits": hit})

    # 7. 落地完成度
    total_refs = len(unique_refs)
    if total_refs == 0:
        completion = 0.0
        file_exist_rate = line_valid_rate = 0.0
    else:
        file_exist_rate = file_ok / total_refs
        line_valid_rate = line_ok / max(1, file_ok)
    impl_rate = merged / max(1, total_refs)
    conflict_penalty = min(1.0, (auto_gen + merge_note) / max(1, total_refs))
    completion = (
        file_exist_rate * 0.5
        + line_valid_rate * 0.2
        + impl_rate * 0.2
        + (1 - conflict_penalty) * 0.1
    )
    completion = max(0.0, min(1.0, completion))

    return {
        "generated_at": datetime.now().isoformat(),
        "doc": str(doc_path),
        "total_declared": total_declared,
        "markers": markers,
        "refs": {
            "unique_total": total_refs,
            "frontmatter": len(fm_refs),
            "table": len(table_rows),
            "file_ok": file_ok,
            "file_missing": file_missing,
            "line_ok": line_ok,
            "line_bad": line_bad,
        },
        "missing_files": sorted(set(missing_files)),
        "out_of_range": out_of_range,
        "impl": {
            "merged": merged,
            "phase_tagged": phase_tagged,
            "other": other_impl,
        },
        "fragments": {"auto_generated": auto_gen, "merge_after_review": merge_note},
        "orphan_recheck": orphan_recheck,
        "rates": {
            "file_exist": round(file_exist_rate, 4),
            "line_valid": round(line_valid_rate, 4),
            "impl": round(impl_rate, 4),
            "completion": round(completion, 4),
        },
    }


def _grep_field_in_engine(field: str) -> int:
    """只读统计 pipeline_engine.py 里字段的引用次数（用于 ORPHAN 复验）。"""
    engine = PROJECT_ROOT / "aiPlat-core" / "core" / "harness" / "execution" / "pipeline_engine.py"
    if not engine.is_file():
        return 0
    try:
        text = engine.read_text(encoding="utf-8", errors="ignore")
        return len(re.findall(re.escape(field), text))
    except Exception:
        return 0


# ── 输出 ────────────────────────────────────────────────
def render_markdown(r: Dict) -> str:
    L = []
    L.append("# aiPlat 能力审计报告")
    L.append("")
    L.append(f"**生成时间**: {r['generated_at']}")
    L.append(f"**文档**: `{r['doc']}`")
    L.append("")
    L.append("## 一、概要")
    L.append("")
    L.append(f"- 头部声明 `total_capabilities`: **{r['total_declared']}**")
    L.append(f"- 标记分布：✅ {r['markers']['ok']} · ⚠️ {r['markers']['warn']} · ❌ {r['markers']['todo']}")
    L.append(f"- 去重后文件引用总数: **{r['refs']['unique_total']}**（frontmatter {r['refs']['frontmatter']} + 表格 {r['refs']['table']}）")
    L.append("")
    L.append("## 二、落地完成度")
    L.append("")
    L.append(f"**{r['rates']['completion'] * 100:.1f}%**")
    L.append("")
    L.append("| 指标 | 值 | 权重 |")
    L.append("|------|-----|------|")
    L.append(f"| 文件存在率 | {r['rates']['file_exist'] * 100:.1f}% | 50% |")
    L.append(f"| 行号有效率 | {r['rates']['line_valid'] * 100:.1f}% | 20% |")
    L.append(f"| 已合入占比 | {r['rates']['impl'] * 100:.1f}% | 20% |")
    L.append(f"| 无碎片惩罚 | {(1 - min(1.0, (r['fragments']['auto_generated'] + r['fragments']['merge_after_review']) / max(1, r['refs']['unique_total']))) * 100:.1f}% | 10% |")
    L.append("")
    L.append("## 三、文件引用")
    L.append("")
    L.append(f"- 文件存在: **{r['refs']['file_ok']}**")
    L.append(f"- 文件缺失: **{r['refs']['file_missing']}**")
    L.append(f"- 行号有效: **{r['refs']['line_ok']}**")
    L.append(f"- 行号越界: **{r['refs']['line_bad']}**")
    L.append("")
    if r["missing_files"]:
        L.append("### 缺失文件清单")
        L.append("")
        for f in r["missing_files"][:30]:
            L.append(f"- `{f}`")
        if len(r["missing_files"]) > 30:
            L.append(f"- … 共 {len(r['missing_files'])} 个")
    else:
        L.append("### 缺失文件清单：无")
    L.append("")
    if r["out_of_range"]:
        L.append("### 行号越界清单")
        L.append("")
        for o in r["out_of_range"][:30]:
            L.append(f"- `{o['path']}:{o['line']}`（文件仅 {o['file_lines']} 行）")
    L.append("")
    L.append("## 四、实施状态分布")
    L.append("")
    L.append(f"- 已合入: **{r['impl']['merged']}**")
    L.append(f"- Phase 标记: **{r['impl']['phase_tagged']}**")
    L.append(f"- 其它/日期: **{r['impl']['other']}**")
    L.append("")
    L.append("## 五、未合并碎片")
    L.append("")
    L.append(f"- auto-generated 片段: **{r['fragments']['auto_generated']}**")
    L.append(f"- 'Merge after review' 标记: **{r['fragments']['merge_after_review']}**")
    L.append("")
    L.append("## 六、ORPHAN 自审计复验")
    L.append("")
    if r["orphan_recheck"]:
        for o in r["orphan_recheck"]:
            tag = "❌ 仍孤儿" if o["still_orphan"] else "✅ 已接线"
            L.append(f"- `{o['field']}` → {tag}（引擎命中 {o['engine_hits']} 处）")
    else:
        L.append("未发现 ORPHAN 自审计标记。")
    L.append("")
    L.append("---")
    L.append("*本报告由 scripts/verify_capability_doc.py 自动生成，只读审计。*")
    return "\n".join(L)


def main():
    print("🚀 aiPlat 元治理审计启动（阶段 0）")
    print(f"📄 文档: {DOC_PATH}")
    print("-" * 50)

    if not DOC_PATH.exists():
        print(f"❌ 未找到文档: {DOC_PATH}")
        sys.exit(1)

    r = audit(DOC_PATH)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    with open(OUTPUT_MD, "w", encoding="utf-8") as f:
        f.write(render_markdown(r))

    print(f"✅ JSON 报告: {OUTPUT_JSON}")
    print(f"✅ Markdown 报告: {OUTPUT_MD}")
    print("-" * 50)
    print(f"🏁 落地完成度: {r['rates']['completion'] * 100:.1f}%")
    print(f"   文件缺失 {r['refs']['file_missing']} · 行号越界 {r['refs']['line_bad']} · 已合入 {r['impl']['merged']} · Phase {r['impl']['phase_tagged']} · 碎片 {r['fragments']['auto_generated'] + r['fragments']['merge_after_review']}")

    if "--ci" in sys.argv:
        if r["rates"]["completion"] < CI_THRESHOLD:
            print(f"❌ CI 失败: 完成度 {r['rates']['completion'] * 100:.1f}% < {CI_THRESHOLD * 100:.0f}%")
            sys.exit(1)
        print("✅ CI 通过")
        sys.exit(0)

    print("✅ 审计完成。详见 docs/audit/latest.md")


if __name__ == "__main__":
    main()
