"""eval_observability.py — 评测观测聚合器（诊断面板数据源）。

聚合三个评测观测产物为统一视图，供诊断面板/运维审计消费：

  - evidence_tree：最近一次证据树（AIPLAT_EVIDENCE_TREE_OUT，verify_claude_md_evidence --tree）
  - guard_trace：最近一次守卫路由决策（AIPLAT_GUARD_TRACE_OUT，architecture_guard.sh）
  - experiences：经验回写状态（AIPLAT_EXPERIENCE_FILE，experience_feedback）

用法:
    from governance.eval_observability import aggregate
    view = aggregate()   # 读环境变量配置的产物路径

    python3 aiPlat-platform/governance/eval_observability.py --summary
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _read_json_list(path: Optional[str]) -> List[Dict[str, Any]]:
    data = _read_json(path)
    return data if isinstance(data, list) else []


def aggregate(evidence_tree_path: Optional[str] = None,
              guard_trace_path: Optional[str] = None,
              experience_path: Optional[str] = None) -> Dict[str, Any]:
    """聚合三个评测观测产物为统一视图。路径缺省读环境变量。"""
    et_path = evidence_tree_path or os.environ.get("AIPLAT_EVIDENCE_TREE_OUT")
    gt_path = guard_trace_path or os.environ.get("AIPLAT_GUARD_TRACE_OUT")
    exp_path = experience_path or os.environ.get("AIPLAT_EXPERIENCE_FILE")

    evidence_tree = _read_json(et_path)
    guard_trace = _read_json(gt_path)
    experiences = _read_json_list(exp_path)

    # 经验状态汇总
    exp_counts = {"pending": 0, "promoted": 0, "rejected": 0, "promoted:review": 0}
    for e in experiences:
        st = e.get("status", "pending")
        exp_counts[st] = exp_counts.get(st, 0) + 1

    recent_exp = sorted(experiences, key=lambda x: x.get("updated_at", ""), reverse=True)[:5]

    sources = []
    if et_path:
        sources.append({"kind": "evidence_tree", "path": et_path, "present": evidence_tree is not None})
    if gt_path:
        sources.append({"kind": "guard_trace", "path": gt_path, "present": guard_trace is not None})
    if exp_path:
        sources.append({"kind": "experiences", "path": exp_path, "present": bool(experiences)})

    return {
        "generated_at": None,
        "sources": sources,
        "evidence_tree": {
            "present": evidence_tree is not None,
            "verdict": (evidence_tree or {}).get("verdict"),
            "known_gaps": (evidence_tree or {}).get("known_gaps", []),
            "cross_check_issues": (evidence_tree or {}).get("cross_check_issues", 0),
        } if evidence_tree is not None else None,
        "guard_trace": {
            "present": guard_trace is not None,
            "mode": (guard_trace or {}).get("mode"),
            "verdict": (guard_trace or {}).get("verdict"),
            "failed_guards": (guard_trace or {}).get("failed_guards", []),
            "skipped_checks": [
                {"check": t.get("check"), "reason_skipped": t.get("reason_skipped")}
                for t in (guard_trace or {}).get("route_trace", [])
                if not t.get("enabled")
            ],
        } if guard_trace is not None else None,
        "experiences": {
            "count": len(experiences),
            "by_status": exp_counts,
            "recent": recent_exp,
        },
    }


def _cli() -> int:
    view = aggregate()
    print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(_cli())
