"""Skill 质量离线评估 — 对标 SkillsBench。

对比三种条件：无Skill(基线) / 手写Skill / AutoLearner生成Skill。
必须验证自生成Skill的净收益 > 0。
环境变量: AIPLAT_EVAL_DRY_RUN=true 在CI中开启
"""

import json, os, sys
from pathlib import Path
import pytest

GOLD_FILE = str(Path(__file__).resolve().parent.parent / "data" / "gold_skill_quality.json")

if os.getenv("AIPLAT_EVAL_DRY_RUN", "").lower() != "true":
    pytest.skip("AIPLAT_EVAL_DRY_RUN not set — use --eval to run manually",
                allow_module_level=True)


def _load_gold():
    with open(GOLD_FILE) as f:
        return json.load(f)


def _verify(case: dict, output: str) -> bool:
    """Run deterministic verifier against agent output."""
    verifier = case["verifier"]
    vtype = verifier["type"]
    if vtype == "contains":
        return any(v.lower() in output.lower() for v in verifier["values"])
    elif vtype == "contains_all":
        return all(v.lower() in output.lower() for v in verifier["values"])
    elif vtype == "code_exec":
        try:
            exec(verifier["test"].replace("output", repr(output)), {"output": output})
            return True
        except Exception:
            return False
    return False


async def _evaluate_condition(cases: list, skill_mode: str) -> dict:
    """在指定条件下跑所有case，返回汇总指标。"""
    from core.harness.evaluation.eval_runner import EvalRunner

    runner = EvalRunner()
    passed, total = 0, 0
    results = []

    for case in cases:
        task = {
            "user_input": case["user_input"],
            "skill_mode": skill_mode,
            "curated_skill": case.get("curated_skill") if skill_mode == "curated" else None,
        }
        try:
            result = await runner.run_task(task)
            output = str(getattr(result, "output", result) if hasattr(result, "output") else result)
        except Exception:
            output = ""

        ok = _verify(case, output)
        if ok:
            passed += 1
        total += 1
        results.append({
            "case_id": case["id"], "passed": ok,
            "domain": case["domain"], "difficulty": case["difficulty"],
        })

    return {"pass_rate": passed / max(total, 1), "passed": passed, "total": total, "results": results}


# ── 1. 净收益：自生成 Skill 必须有正向净收益 ──

@pytest.mark.eval
async def test_skill_net_gain():
    """自生成 Skill 的净收益必须 > 0（相对于无Skill基线）。"""
    cases = _load_gold()
    baseline = await _evaluate_condition(cases, "none")
    auto_gen = await _evaluate_condition(cases, "auto_gen")

    net_gain = auto_gen["pass_rate"] - baseline["pass_rate"]
    print(f"\n  Baseline (no skill):     {baseline['pass_rate']:.1%}")
    print(f"  Auto-Generated skill:  {auto_gen['pass_rate']:.1%}")
    print(f"  Net gain:               {net_gain:+.1%}")

    assert net_gain > 0, (
        f"自生成 Skill 无正向净收益（{net_gain:+.1%}）。"
        f"SkillsBench 基准：自生成 Skill 平均 -1.3pp。"
    )


# ── 2. 与手写差距：不能差超过 10% ──

@pytest.mark.eval
async def test_skill_curated_gap():
    """自生成 Skill 不能比手写 Skill 差超过 10%。"""
    cases = _load_gold()
    curated = await _evaluate_condition(cases, "curated")
    auto_gen = await _evaluate_condition(cases, "auto_gen")

    gap = curated["pass_rate"] - auto_gen["pass_rate"]
    print(f"\n  Curated skill:          {curated['pass_rate']:.1%}")
    print(f"  Auto-Generated skill:   {auto_gen['pass_rate']:.1%}")
    print(f"  Gap:                    {gap:+.1%}")

    assert gap < 0.10, (
        f"自生成 Skill 比手写 Skill 差 {gap:.1%}。"
        f"SkillsBench 基准：手写 Skill 平均 +16.2pp。"
    )


# ── 3. 领域分层 ──

@pytest.mark.eval
async def test_skill_domain_breakdown():
    """按领域和难度输出分层 pass_rate，发现薄弱环节。"""
    cases = _load_gold()
    for mode in ["none", "curated", "auto_gen"]:
        result = await _evaluate_condition(cases, mode)
        by_domain = {}
        for r in result["results"]:
            d = r["domain"]
            by_domain.setdefault(d, {"passed": 0, "total": 0})
            by_domain[d]["passed"] += r["passed"]
            by_domain[d]["total"] += 1
        print(f"\n  [{mode}] Domain breakdown:")
        for dom, stats in sorted(by_domain.items()):
            pr = stats["passed"] / max(stats["total"], 1)
            print(f"    {dom}: {stats['passed']}/{stats['total']} ({pr:.0%})")
