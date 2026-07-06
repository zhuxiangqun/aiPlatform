#!/usr/bin/env python3
"""
compute_assessment.py — 评估框架"验证 + 聚合 + 漂移检测"引擎 (P0.1)

诚实性底线 (见 docs/framework/assessment-spec.yaml 头部):
  - L 级 / 分数是人工判定 (declared_*), 本程序**不推导、不计算** L 级。
  - 本程序只做三件事:
    1. 验证: 跑 source=script/file_check 项的 evidence.command, 判 declared 值是否仍有证据。
    2. 聚合: 按 spec.weighting 的确定性公式算综合分 (全库唯一, 消除 4.15/4.35/5.00 三头矛盾)。
    3. 漂移: declared 有声明但证据命令 FAIL → 记入 drift; 文档声明层分 vs 计算层分不符 → 记入 drift。

用法:
  python3 scripts/compute_assessment.py                 # 全量, 写 assessment-scores.json + 打印摘要
  python3 scripts/compute_assessment.py --drift-only    # 只打印漂移报告
  python3 scripts/compute_assessment.py --quiet         # 只写文件, 不打印

退出码: 0=无漂移, 1=有漂移
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要 pyyaml: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "docs" / "framework" / "assessment-spec.yaml"
OUT = REPO / "docs" / "framework" / "assessment-scores.json"


def _run_evidence(ev: dict) -> tuple:
    """Run one evidence command; return (status, actual). status: pass/fail/error."""
    cmd = ev.get("command", "")
    op = ev.get("op", "-ge")
    expected = ev.get("expected", 1)
    try:
        out = subprocess.run(
            cmd, shell=True, cwd=str(REPO), capture_output=True,
            text=True, timeout=30,
        ).stdout.strip()
        # take last non-empty token as the number
        tok = (out.split() or ["0"])[-1]
        actual = int("".join(c for c in tok if c.isdigit() or c == "-") or "0")
    except Exception as e:
        return "error", str(e)[:80]
    ok = (
        actual >= expected if op == "-ge"
        else actual == expected if op == "-eq"
        else actual <= expected if op == "-le"
        else actual > expected if op == "-gt"
        else actual >= expected
    )
    return ("pass" if ok else "fail"), actual


def _verify_items(items: list, drift: list, ctx: str) -> None:
    """Attach verification_status to each item; record drift on FAIL."""
    for it in items:
        src = it.get("source")
        if src in ("script", "file_check") and it.get("evidence"):
            status, actual = _run_evidence(it["evidence"])
            it["verification_status"] = status
            it["actual"] = actual
            if status != "pass":
                drift.append({
                    "where": ctx, "id": it.get("id"),
                    "declared": it.get("declared_level") or it.get("result"),
                    "evidence_status": status.upper(), "actual": actual,
                    "expected": it["evidence"].get("expected"),
                    "command": it["evidence"].get("command"),
                    "note": "证据命令不再通过 — declared 值可能已过时",
                })
        else:
            it["verification_status"] = "no-data"  # manual / gap


def compute(spec: dict) -> dict:
    lm = spec["weighting"]["framework_one"]["level_map"]
    drift: list = []
    result: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "spec_version": spec.get("spec_version"),
        "frameworks": {}, "drift": [],
    }

    # ── Framework 1: normalized weighted avg of AXIS declared levels ──
    f1 = spec["frameworks"]["framework_one"]
    num = den = 0.0
    axes_out = []
    for ax in f1["axes"]:
        _verify_items(ax["items"], drift, f"framework_one/{ax['id']}")
        lvl = ax.get("declared_level")
        w = ax.get("weight", 0)
        val = lm.get(lvl) if lvl else None
        if val is not None:
            num += val * w
            den += w
        axes_out.append({
            "id": ax["id"], "name": ax["name"], "declared_level": lvl,
            "weight": w, "level_value": val,
            "conflict_note": ax.get("conflict_note"),
            "items": ax["items"],
        })
    f1_score = round(num / den, 2) if den else 0
    result["frameworks"]["framework_one"] = {
        "name": f1["name"],
        "composite_level_value": f1_score,
        "composite_grade": f"L{int(round(f1_score))}",
        "weight_sum": round(den, 3),
        "formula": "sum(axis_level*weight)/sum(weight) — normalized",
        "axes": axes_out,
    }

    # ── Framework 2: percentage (yes + 0.5*partial)/total ──
    f2 = spec["frameworks"]["framework_two"]
    rm = spec["weighting"]["framework_two"]["result_map"]
    dims_out = []
    all_num = all_tot = 0
    for d in f2["dimensions"]:
        _verify_items(d["items"], drift, f"framework_two/{d['id']}")
        s = sum(rm.get(it.get("result", "no"), 0) for it in d["items"])
        t = len(d["items"])
        all_num += s
        all_tot += t
        dims_out.append({
            "id": d["id"], "name": d["name"],
            "pct": round(s / t * 100, 1) if t else 0, "items": d["items"],
        })
    result["frameworks"]["framework_two"] = {
        "name": f2["name"],
        "overall_pct": round(all_num / all_tot * 100, 1) if all_tot else 0,
        "formula": "(yes*1 + partial*0.5)/total * 100",
        "dimensions": dims_out,
    }

    # ── Framework 3: per-tier mean of manual scores + declared-vs-computed drift ──
    f3 = spec["frameworks"]["framework_three"]
    tiers_out = []
    for t in f3["tiers"]:
        _verify_items(t["items"], drift, f"framework_three/{t['id']}")
        scores = [it["score"] for it in t["items"] if "score" in it]
        mean = round(sum(scores) / len(scores), 2) if scores else 0
        declared = t.get("declared_tier_score")
        if declared is not None and abs(mean - declared) >= 0.3:
            drift.append({
                "where": f"framework_three/{t['id']}", "id": t["id"],
                "declared": declared, "evidence_status": "MISMATCH",
                "actual": mean,
                "note": f"文档声明层分 {declared} 与项均值 {mean} 不符(差≥0.3) — 文档综合分可疑",
            })
        tiers_out.append({
            "id": t["id"], "name": t["name"],
            "declared_tier_score": declared, "computed_mean": mean,
            "items": t["items"],
        })
    result["frameworks"]["framework_three"] = {
        "name": f3["name"], "note": f3.get("note"),
        "formula": "per-tier mean of manual scores (all source=manual)",
        "tiers": tiers_out,
    }

    result["drift"] = drift
    return result


def print_summary(r: dict) -> None:
    f1 = r["frameworks"]["framework_one"]
    f2 = r["frameworks"]["framework_two"]
    f3 = r["frameworks"]["framework_three"]
    print("\n===== 评估综合分 (确定性计算, 全库唯一) =====")
    print(f"  框架一 8轴自主性: {f1['composite_level_value']} → {f1['composite_grade']} "
          f"(权重和={f1['weight_sum']})")
    print(f"  框架二 工程落地:   {f2['overall_pct']}%")
    for t in f3["tiers"]:
        print(f"  框架三 {t['name']}: 文档声明={t['declared_tier_score']} vs 项均值={t['computed_mean']}")
    print(f"\n===== 漂移/矛盾 ({len(r['drift'])}) =====")
    if not r["drift"]:
        print("  ✓ 无漂移 — 所有 declared 值证据均通过, 层分自洽")
    for d in r["drift"]:
        print(f"  ⚠ [{d['where']}] {d['id']} {d['evidence_status']}: "
              f"declared={d['declared']} actual={d.get('actual')} — {d['note']}")


# ── P0.2: idempotent marker-block render into framework docs ──

_MARK_BEGIN = "<!-- AUTO-SCORE:BEGIN (由 scripts/compute_assessment.py 生成, 勿手改) -->"
_MARK_END = "<!-- AUTO-SCORE:END -->"
_RENDER_TARGETS = [
    "docs/framework/aiplat-complete-assessment.md",
    "docs/framework/scoring-detail.md",
    "docs/framework/aiplat-autonomy-framework.md",
]


def build_score_block(r: dict) -> str:
    import re as _re
    f1 = r["frameworks"]["framework_one"]
    f2 = r["frameworks"]["framework_two"]
    f3 = r["frameworks"]["framework_three"]
    verifiable = 0
    passed = 0
    for fw in ("framework_one", "framework_two"):
        node = r["frameworks"][fw]
        groups = node.get("axes") or node.get("dimensions") or []
        for g in groups:
            for it in g["items"]:
                if it.get("verification_status") in ("pass", "fail", "error"):
                    verifiable += 1
                    if it["verification_status"] == "pass":
                        passed += 1
    tiers = " / ".join(f"{t['name'][:2]} {t['computed_mean']}" for t in f3["tiers"])
    lines = [
        _MARK_BEGIN,
        f"> **📊 权威评分**（唯一源 `assessment-spec.yaml` → `compute_assessment.py`，生成于 {r['generated_at']}）",
        ">",
        "> | 框架 | 计算综合 | 公式 |",
        "> |------|------|------|",
        f"> | 框架一 8轴自主性 | **{f1['composite_grade']} ({f1['composite_level_value']})** | 归一化加权(权重和 {f1['weight_sum']}) |",
        f"> | 框架二 工程落地 | **{f2['overall_pct']}%** | (yes+0.5·partial)/total |",
        f"> | 框架三 三层企业 | {tiers} | 项均值(人工分) |",
        ">",
        f"> 可验证项 {passed}/{verifiable} pass · 漂移 {len(r['drift'])} · 手写分数已废弃，本块自动回填。",
        _MARK_END,
    ]
    return "\n".join(lines)


def render_docs(r: dict) -> None:
    import re as _re
    block = build_score_block(r)
    pat = _re.compile(_re.escape(_MARK_BEGIN) + r".*?" + _re.escape(_MARK_END), _re.DOTALL)
    for rel in _RENDER_TARGETS:
        p = REPO / rel
        if not p.exists():
            print(f"  ⚠ render skip (缺文件): {rel}")
            continue
        txt = p.read_text(encoding="utf-8")
        if _MARK_BEGIN in txt:
            txt = pat.sub(block, txt)
        else:
            # insert after first H1 line
            lines = txt.splitlines(keepends=True)
            idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), 0)
            lines.insert(idx + 1, "\n" + block + "\n")
            txt = "".join(lines)
        p.write_text(txt, encoding="utf-8")
        print(f"  ✓ rendered AUTO-SCORE → {rel}")


def main() -> int:
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    r = compute(spec)
    if "--drift-only" not in sys.argv:
        OUT.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    if "--render" in sys.argv:
        render_docs(r)
    if "--quiet" not in sys.argv:
        print_summary(r)
        if "--drift-only" not in sys.argv:
            print(f"\n→ {OUT.relative_to(REPO)}")
    return 1 if r["drift"] else 0


if __name__ == "__main__":
    sys.exit(main())
