"""test_experience_feedback.py — L2 经验回写状态机测试。

覆盖：登记（含置信度门槛/合并）→ 两次独立验证 → 升级（低风险自动/高风险人工确认）
→ 失败重置/经验无效，以及 CLI 冒烟。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from governance.experience_feedback import (  # noqa: E402
    ExperienceStore,
    MIN_CONFIDENCE,
    PROMOTE_THRESHOLD,
    register_failure,
    record_verification,
)


@pytest.fixture()
def store(tmp_path):
    return ExperienceStore(str(tmp_path / "exp.json"))


# ── 登记 ──
def test_register_creates_pending(store):
    r = store.register_failure("rag-missing-source", "RAG 回答缺失检索来源",
                               source="evidence_tree", confidence=0.9)
    assert r["registered"] is True
    recs = store.status("rag-missing-source")
    assert len(recs) == 1
    assert recs[0]["status"] == "pending"
    assert recs[0]["verify_count"] == 0


def test_register_below_confidence_rejected(store):
    r = store.register_failure("rag-missing-source", "低置信度失败",
                               source="evidence_tree", confidence=0.5)
    assert r["registered"] is False
    assert r["reason"] == "confidence_below_threshold"
    assert store.status() == []  # 未落盘


def test_register_same_rule_merges(store):
    store.register_failure("arch-guard-fail", "守卫失败", source="architecture_guard", confidence=0.9)
    r2 = store.register_failure("arch-guard-fail", "守卫失败", source="evidence_tree", confidence=0.9)
    assert r2["merged"] is True
    assert r2["occurrences"] == 2
    recs = store.status("arch-guard-fail")
    assert len(recs) == 1
    assert "evidence_tree" in recs[0]["sources"]


# ── 两次独立验证 → 升级（低风险自动） ──
def test_two_independent_success_promotes_low_risk(store):
    store.register_failure("rule-a", "经验A", confidence=0.9, risk="low")
    r1 = store.record_verification("rule-a", "case-1", "success")
    assert r1["verified"] is True and r1["count"] == 1
    assert r1["promote_pending"] == 1
    r2 = store.record_verification("rule-a", "case-2", "success")
    assert r2["promoted"] is True
    assert r2["require_review"] is False
    rec = store.status("rule-a")[0]
    assert rec["status"] == "promoted"
    assert rec["verify_count"] == PROMOTE_THRESHOLD
    assert rec["promote_draft"] and "rule-a" in rec["promote_draft"]


def test_same_case_duplicate_not_counted(store):
    store.register_failure("rule-a", "经验A", confidence=0.9, risk="low")
    store.record_verification("rule-a", "case-1", "success")
    r = store.record_verification("rule-a", "case-1", "success")
    assert r["duplicate_case"] is True
    assert store.status("rule-a")[0]["verify_count"] == 1


# ── 失败重置 / 经验无效 ──
def test_failure_resets_progress(store):
    store.register_failure("rule-a", "经验A", confidence=0.9, risk="low")
    store.record_verification("rule-a", "case-1", "success")
    r = store.record_verification("rule-a", "case-2", "fail")
    assert r["verified"] is False and r["count"] == 0
    rec = store.status("rule-a")[0]
    assert rec["verify_count"] == 0
    assert rec["status"] == "pending"  # 未失效（仅 1 次失败）


def test_two_failures_rejects(store):
    store.register_failure("rule-a", "经验A", confidence=0.9, risk="low")
    store.record_verification("rule-a", "case-1", "fail")
    r = store.record_verification("rule-a", "case-2", "fail")
    assert r["status"] == "rejected"
    assert store.status("rule-a")[0]["status"] == "rejected"


# ── 高风险升级需人工确认 ──
def test_high_risk_requires_review(store):
    store.register_failure("rule-h", "高风险经验", confidence=0.9, risk="high")
    store.record_verification("rule-h", "case-1", "success")
    r = store.record_verification("rule-h", "case-2", "success")
    assert r["require_review"] is True
    rec = store.status("rule-h")[0]
    assert rec["status"] == "promoted:review"
    # 未确认前不算最终 promoted
    r2 = store.confirm_promotion("rule-h", accept=True)
    assert r2["status"] == "promoted"
    # 拒绝路径
    store.register_failure("rule-h2", "高风险经验2", confidence=0.9, risk="high")
    store.record_verification("rule-h2", "c1", "success")
    store.record_verification("rule-h2", "c2", "success")
    r3 = store.confirm_promotion("rule-h2", accept=False)
    assert r3["status"] == "rejected"


# ── CLI 冒烟 ──
def test_cli_register_status(tmp_path):
    exp_file = str(tmp_path / "exp.json")
    env = {**os.environ, "AIPLAT_EXPERIENCE_FILE": exp_file}
    script = Path(__file__).resolve().parents[1] / "governance/experience_feedback/experience_feedback.py"
    r = subprocess.run([sys.executable, str(script), "--register",
                        "--rule", "cli-rule", "--content", "CLI 经验",
                        "--confidence", "0.9"], capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert json.loads(r.stdout)["registered"] is True
    s = subprocess.run([sys.executable, str(script), "--status"],
                       capture_output=True, text=True, env=env)
    assert json.loads(s.stdout)[0]["rule_id"] == "cli-rule"


def test_register_helper_signature():
    # 顶层便捷函数可用（供 architecture_guard 接线）
    assert callable(register_failure)
    assert callable(record_verification)
