#!/usr/bin/env python3
"""
verify_capability_truth.py — 能力声明 ↔ 源码一致性统一入口

源码（及可重复行为验收）才是实现真相。本脚本只校验声明/视图与仓库文件的关系，
不得单独宣称「已实现」或「可运行」。

════════════════════════════════════════════════════════════════════════
静态校验能力边界（本轮 --ci 硬失败仅证明下表）
════════════════════════════════════════════════════════════════════════

| 检查 | 能证明 | 不能证明 |
|------|--------|----------|
| CAPABILITIES path / path:line | 文件存在；行号在文件行数内 | 该行仍是原符号；行为可用 |
| verify_capability_consistency | AUTO-STATS 块 ≡ 章节 ✅/⚠️ 实算（纯生成物全文） | 每行对应真实实现 |
| registry caps_count / 头体 | 登记表内部自洽（caps_count==len(provides)） | 符号在源码中存在 |
| 矩阵临时全文 diff | 工作树矩阵 ≡ 当前 registry 生成结果 | 消费者边在运行时真实 |
| check_code_doc_gap | harness 下 .py 模块 stem/parent 名在 CAPABILITIES 有登记 | 符号级存在、生产调用方、可运行 |
| verify_registry_provides_ast | provides.module 可解析且符号在模块 AST 顶层存在；相对 baseline 的**新增**债务 | 生产调用方；行为可用；baseline 内存量 |
| smoke_capability_critical_paths (static) | 关键路径清单中文件/AST/子串存在 | 服务可响应；端到端业务成功（见 `--live`） |

明确排除（本轮不硬失败）：
  - 「有生产调用方」——不由 manifest/registry 反推
  - 「行为可用 / 行为通过」——`smoke_capability_critical_paths --live`；与 CAPABILITIES ✅ 分列
  - registry provides 存量 AST 债务（baseline 内）——仅新增债务 --ci 硬失败

check_code_doc_gap 实际规则（以 scripts/check_code_doc_gap.py 为准）：
  - 扫描路径: aiPlat-core/core/harness/**/*.py（跳过 __init__.py、tests、__pycache__）
  - 匹配: 文件 stem 或 parent 目录名出现在 AIPLAT_CAPABILITIES.md 正文
  - 另有路径前缀跳过列表（kernel/、utils/、hooks/ 等）

用法:
  python3 scripts/verify_capability_truth.py           # 打印硬项+软警告，exit 0，不写盘
  python3 scripts/verify_capability_truth.py --ci      # 任一硬失败 → 非零；软警告永不单独非零
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load(name: str, filename: str):
    path = SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    # Py3.9 dataclasses need the module present in sys.modules during class body
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _check_registry_caps() -> Tuple[bool, List[str], Dict[str, Any]]:
    """caps_count MUST equal len(provides) per domain; header totals match bodies."""
    import yaml

    reg = ROOT / "aiPlat-core" / "core" / "capability_registry.yaml"
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))
    domains = data.get("domains") or {}
    errs: List[str] = []
    mismatches = []
    for did, d in domains.items():
        provides = d.get("provides") or []
        declared = int(d.get("caps_count") or 0)
        actual = len(provides)
        if declared != actual:
            mismatches.append({"domain": did, "caps_count": declared, "len_provides": actual})
            errs.append(f"{did}: caps_count={declared} != len(provides)={actual}")
    n_domains = len(domains)
    n_caps = sum(int(d.get("caps_count") or 0) for d in domains.values())
    hdr_domains = data.get("total_capability_domains")
    hdr_caps = data.get("total_capabilities")
    if hdr_domains is not None and int(hdr_domains) != n_domains:
        errs.append(f"header total_capability_domains={hdr_domains} != body {n_domains}")
    if hdr_caps is not None and int(hdr_caps) != n_caps:
        errs.append(f"header total_capabilities={hdr_caps} != sum(caps_count)={n_caps}")
    return (len(errs) == 0), errs, {
        "domains": n_domains,
        "caps": n_caps,
        "mismatches": mismatches[:20],
    }


def run_checks(*, ci: bool = False) -> Dict[str, Any]:
    """Run all hard checks + soft warnings. Never writes docs/audit."""
    hard: List[Dict[str, Any]] = []
    soft: List[Dict[str, Any]] = []

    # 1) CAPABILITIES path audit
    vdoc = _load("verify_capability_doc", "verify_capability_doc.py")
    doc_result = vdoc.audit(vdoc.DOC_PATH)
    refs = doc_result["refs"]
    if refs["file_missing"] > 0 or refs["line_bad"] > 0:
        hard.append({
            "check": "capability_doc_paths",
            "file_missing": refs["file_missing"],
            "line_bad": refs["line_bad"],
            "missing_sample": doc_result.get("missing_files", [])[:10],
            "oor_sample": doc_result.get("out_of_range", [])[:10],
        })
    if refs.get("ambiguous_count", 0):
        soft.append({
            "check": "capability_doc_ambiguous",
            "ambiguous_count": refs["ambiguous_count"],
            "note": "basename multi-hit; not a --ci failure alone",
        })
    if refs.get("runtime_home_count", 0):
        soft.append({
            "check": "capability_doc_runtime_home",
            "runtime_home_count": refs["runtime_home_count"],
            "sample": doc_result.get("runtime_home_files", [])[:10],
            "note": "~/.aiplat install path not in repo; prefer workspace_seeds; soft only",
        })
    basename_soft = sum(
        1 for r in doc_result.get("records", [])
        if r.get("soft_warning") == "basename_unique"
    )
    if basename_soft:
        soft.append({
            "check": "capability_doc_basename_unique",
            "count": basename_soft,
            "note": "resolved via unique basename; prefer explicit repo path",
        })

    # 2) CAPABILITIES stats table consistency
    vcons = _load("verify_capability_consistency", "verify_capability_consistency.py")
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            rc = int(vcons.main())
        except SystemExit as e:
            rc = int(e.code or 0)
    if rc != 0:
        hard.append({
            "check": "capability_consistency",
            "detail": buf.getvalue()[-800:],
        })

    # 3) registry caps_count == len(provides)
    ok_reg, reg_errs, reg_meta = _check_registry_caps()
    if not ok_reg:
        hard.append({"check": "registry_caps_count", "errors": reg_errs, **reg_meta})

    # 4) matrix full-body freshness (worktree vs render; does not rewrite)
    gmat = _load("generate_impact_matrix", "generate_impact_matrix.py")
    buf = io.StringIO()
    with redirect_stdout(buf):
        mrc = gmat.check_matrix_fresh(ROOT)
    if mrc != 0:
        hard.append({
            "check": "impact_matrix_fresh",
            "detail": buf.getvalue()[-600:],
        })

    # 5) code-doc gap (harness module name registration)
    cgap = _load("check_code_doc_gap", "check_code_doc_gap.py")
    buf = io.StringIO()
    with redirect_stdout(buf):
        grc = cgap.check_gaps()
    if grc != 0:
        hard.append({
            "check": "code_doc_gap",
            "detail": buf.getvalue()[-800:],
            "scope": "aiPlat-core/core/harness/**/*.py stem|parent ⊆ CAPABILITIES.md",
        })

    # 6) registry provides.module AST ratchet (new debt only)
    vast = _load("verify_registry_provides_ast", "verify_registry_provides_ast.py")
    ast_result = vast.audit_registry()
    baseline = vast.load_baseline()
    novel = vast.new_findings(ast_result, baseline)
    soft.append({
        "check": "registry_provides_ast",
        "findings": len(ast_result["finding_ids"]),
        "baseline": len(baseline.get("finding_ids") or []),
        "new": len(novel),
        "counts": ast_result["counts"],
        "note": "stock debt in baseline is soft; only NEW ids fail --ci",
    })
    if novel:
        hard.append({
            "check": "registry_provides_ast_new",
            "new_count": len(novel),
            "sample": novel[:15],
            "note": "fix registry or shrink baseline after cleanup",
        })

    # 7) Phase D critical-path static smoke (live HTTP stays opt-in / soft here)
    vsmoke = _load("smoke_capability_critical_paths", "smoke_capability_critical_paths.py")
    smoke = vsmoke.run_smoke(live=False)
    soft.append({
        "check": "critical_path_smoke_static",
        "static_fail": smoke["static_fail"],
        "live_skip": smoke["live_skip"],
        "note": "static wiring only; live HTTP via smoke_capability_critical_paths --live",
    })
    if smoke["static_fail"]:
        hard.append({
            "check": "critical_path_smoke_static",
            "static_fail": smoke["static_fail"],
            "sample": [r for r in smoke["results"] if r.get("ok") is False][:10],
        })

    return {
        "hard_failures": hard,
        "soft_warnings": soft,
        "doc_rates": {
            "file_exist": doc_result["rates"]["file_exist"],
            "line_valid": doc_result["rates"]["line_valid"],
            "total_records": refs["total_records"],
            "file_ok": refs["file_ok"],
            "file_missing": refs["file_missing"],
            "ambiguous_count": refs.get("ambiguous_count", 0),
            "line_bad": refs["line_bad"],
        },
        "registry": reg_meta,
        "provides_ast": {
            "findings": len(ast_result["finding_ids"]),
            "new": len(novel),
            "counts": ast_result["counts"],
        },
        "ci": ci,
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    ci = "--ci" in argv

    print("aiPlat capability truth gate (source of truth = repo source)")
    print("Static proof bounds: see module docstring. Soft warnings never alone fail --ci.")
    print("-" * 60)

    result = run_checks(ci=ci)
    rates = result["doc_rates"]
    lv = rates["line_valid"]
    lv_s = "N/A" if lv is None else f"{lv * 100:.1f}%"
    print(
        f"doc refs: total={rates['total_records']} ok={rates['file_ok']} "
        f"missing={rates['file_missing']} ambiguous={rates['ambiguous_count']} "
        f"line_bad={rates['line_bad']} file_exist={rates['file_exist']*100:.1f}% "
        f"line_valid={lv_s}"
    )
    print(
        f"registry: domains={result['registry'].get('domains')} "
        f"caps={result['registry'].get('caps')}"
    )
    past = result.get("provides_ast") or {}
    if past:
        print(
            f"provides_ast: findings={past.get('findings')} new={past.get('new')} "
            f"counts={past.get('counts')}"
        )

    for s in result["soft_warnings"]:
        print(f"SOFT: {s}")
    for h in result["hard_failures"]:
        print(f"HARD: {h.get('check')}")
        if h.get("errors"):
            for e in h["errors"][:10]:
                print(f"  - {e}")
        for key in ("missing_sample", "oor_sample", "sample"):
            for item in h.get(key) or []:
                print(f"  {key}: {item}")
        if h.get("detail"):
            for line in str(h["detail"]).strip().splitlines()[-8:]:
                print(f"  {line}")

    n_hard = len(result["hard_failures"])
    n_soft = len(result["soft_warnings"])
    print("-" * 60)
    print(f"hard={n_hard} soft={n_soft}")

    if ci and n_hard:
        print("CI FAIL")
        return 1
    if ci:
        print("CI PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
