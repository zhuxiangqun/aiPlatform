"""test_eval_observability.py — 评测观测聚合器测试。

覆盖：三源聚合、产物缺失降级、经验状态统计、skipped_checks 提取。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.eval_observability import aggregate  # noqa: E402


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_aggregate_full(tmp_path):
    et = _write(tmp_path, "et.json", {"verdict": {"score": 1.0}, "known_gaps": [], "cross_check_issues": 0})
    gt = _write(tmp_path, "gt.json", {
        "mode": "quick", "verdict": "pass", "failed_guards": [],
        "route_trace": [{"check": "capability_convergence", "enabled": False,
                         "reason_skipped": "quick 模式或 SKIP_CAP_CONV"}]})
    exp = _write(tmp_path, "exp.json", [
        {"rule_id": "r1", "status": "promoted", "updated_at": "2026-08-27T01:00:00Z"},
        {"rule_id": "r2", "status": "pending", "updated_at": "2026-08-27T02:00:00Z"}])

    v = aggregate(et, gt, exp)
    assert v["evidence_tree"]["verdict"]["score"] == 1.0
    assert v["guard_trace"]["mode"] == "quick"
    assert v["guard_trace"]["skipped_checks"] == [
        {"check": "capability_convergence", "reason_skipped": "quick 模式或 SKIP_CAP_CONV"}]
    assert v["experiences"]["by_status"] == {"pending": 1, "promoted": 1,
                                             "rejected": 0, "promoted:review": 0}
    assert v["experiences"]["count"] == 2
    assert all(s["present"] for s in v["sources"])


def test_aggregate_missing_products(tmp_path):
    """产物缺失时优雅降级（present=False / None），不抛异常。"""
    v = aggregate(str(tmp_path / "missing1.json"), str(tmp_path / "missing2.json"),
                  str(tmp_path / "missing3.json"))
    assert v["evidence_tree"] is None
    assert v["guard_trace"] is None
    assert v["experiences"]["count"] == 0
    assert all(not s["present"] for s in v["sources"])


def test_aggregate_no_env(tmp_path):
    """未配置任何产物路径时返回空视图。"""
    import governance.eval_observability as m
    old = {k: m.os.environ.get(k) for k in ("AIPLAT_EVIDENCE_TREE_OUT",
                                            "AIPLAT_GUARD_TRACE_OUT",
                                            "AIPLAT_EXPERIENCE_FILE")}
    for k in old:
        m.os.environ.pop(k, None)
    try:
        v = m.aggregate()
        assert v["sources"] == []
        assert v["experiences"]["count"] == 0
    finally:
        for k, val in old.items():
            if val is not None:
                m.os.environ[k] = val


def test_experience_status_distribution(tmp_path):
    exp = _write(tmp_path, "exp.json", [
        {"rule_id": "a", "status": "rejected", "updated_at": "t1"},
        {"rule_id": "b", "status": "promoted:review", "updated_at": "t2"}])
    v = aggregate(experience_path=exp)
    assert v["experiences"]["by_status"]["rejected"] == 1
    assert v["experiences"]["by_status"]["promoted:review"] == 1
