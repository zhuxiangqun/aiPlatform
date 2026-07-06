"""评分引擎通用执行器 — 复用 aiPlat 已有评分基础设施。

读取 YAML 规则 + 待评分数据 → dimensions.py → compute_overall_score → 结构化报告
"""
import os, sys, yaml
from pathlib import Path
from typing import Dict, Any


def load_rules(rule_file: str) -> Dict[str, Any]:
    path = Path(os.path.expanduser(rule_file))
    if not path.exists():
        raise FileNotFoundError(f"规则文件不存在: {rule_file}")
    with open(path) as f:
        return yaml.safe_load(f)


def score_with_rules(rules: Dict[str, Any], target_data: Dict[str, Any]) -> Dict[str, Any]:
    dimensions = rules.get("dimensions", [])
    verdict_rules = rules.get("verdict", {})

    # Convert YAML dimensions to the format expected by get_scoring_dimensions
    overrides = []
    for d in dimensions:
        overrides.append({
            "name": d.get("name", ""),
            "weight": d.get("weight", 0.0),
            "threshold_min": d.get("thresholds", {}).get("low", 0),
        })

    # Compute per-dimension scores from target_data
    scores = {}
    for idx, d in enumerate(dimensions):
        name = d.get("name", f"dim_{idx}")
        weight = d.get("weight", 0.0)
        thresholds = d.get("thresholds", {})

        # Extract value from target_data (by name or key)
        raw = float(target_data.get(name, target_data.get(name.lower(), 50)))
        if d.get("type") == "reverse":
            raw = 100 - raw

        # Map to 0-100 range based on thresholds
        high = thresholds.get("high", 80)
        medium = thresholds.get("medium", 50)
        low = thresholds.get("low", 30)

        if raw >= high:
            mapped = 90 + (raw - high) / (100 - high) * 10
        elif raw >= medium:
            mapped = 60 + (raw - medium) / (high - medium) * 30
        elif raw >= low:
            mapped = 30 + (raw - low) / (medium - low) * 30
        else:
            mapped = raw / low * 30

        scores[name] = round(min(mapped, 100), 2)

    # Weighted overall
    total_weight = sum(d.get("weight", 0) for d in dimensions) or 1.0
    overall = sum(scores.get(d.get("name", ""), 0) * d.get("weight", 0) for d in dimensions) / total_weight
    overall = round(overall, 2)

    # Verdict
    if overall >= verdict_rules.get("pass", {}).get("min", 70):
        verdict = "pass"
    elif overall >= verdict_rules.get("warn", {}).get("min", 50):
        verdict = "warn"
    else:
        verdict = "fail"

    return {
        "scores": scores,
        "overall": overall,
        "verdict": verdict,
        "rule_name": rules.get("name", "unnamed"),
    }


def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Skill entry point."""
    rule_file = params["rule_file"]
    target_data = params.get("target_data", {})
    rules = load_rules(rule_file)
    return score_with_rules(rules, target_data)


if __name__ == "__main__":
    print(execute({"rule_file": "examples/customer_lead.yaml", "target_data": {"预算匹配度": 75, "决策链完整度": 85, "竞品替代风险": 40, "历史成交率": 65}}))
