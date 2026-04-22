from __future__ import annotations

from pathlib import Path


def test_auto_eval_docs_guard_has_required_terms():
    """
    文档护栏（contracts-guard）：
    防止 auto-eval / 证据 / 回归 / 策略 的实现迭代后，设计真值文档不更新而脱节。
    """

    # 1) 关键 artifacts kind 必须存在于代码中（防重命名漏改）
    from core.learning.types import LearningArtifactKind

    assert LearningArtifactKind.EVALUATION_REPORT.value == "evaluation_report"
    assert LearningArtifactKind.EVIDENCE_PACK.value == "evidence_pack"
    assert LearningArtifactKind.EVIDENCE_DIFF.value == "evidence_diff"
    assert LearningArtifactKind.EVALUATION_POLICY.value == "evaluation_policy"
    assert LearningArtifactKind.RUN_STATE.value == "run_state"

    # 2) 文档必须提及关键对象/API/字段（防文档脱节）
    doc_path = Path(__file__).resolve().parents[4] / "docs" / "design" / "evaluation" / "auto-eval-and-regression.md"
    assert doc_path.exists(), f"missing doc: {doc_path}"
    text = doc_path.read_text(encoding="utf-8", errors="ignore")

    required_terms = [
        # artifact kinds
        "evaluation_report",
        "evidence_pack",
        "evidence_diff",
        "evaluation_policy",
        "run_state",
        # core APIs
        "POST /runs/{run_id}/evaluate/auto",
        "GET /evaluation/policy/latest",
        "POST /evaluation/policy",
        "GET /projects/{project_id}/evaluation/policy/latest",
        "POST /projects/{project_id}/evaluation/policy",
        "GET /runs/{run_id}/evidence_pack/latest",
        "POST /runs/{run_id}/evidence/diff",
        # request fields
        "project_id",
        "expected_tags",
        "tag_expectations",
        "tag_template",
        # gates
        "tag_assertions",
        "regression_gate",
    ]

    missing = [t for t in required_terms if t not in text]
    assert not missing, f"auto-eval doc missing terms: {missing}"

