"""Unit tests for SkillOpt-inspired dual-channel analysis + rejected buffer + max edits."""
import pytest
from core.harness.learning import (
    AutoLearner, SkillDraft, get_auto_learner,
)


class TestDualChannelAnalysis:
    """P0: Success + Failure dual-channel analysis."""

    def test_analyze_success_generates_draft(self):
        learner = get_auto_learner()
        draft = learner.analyze_success(
            task="整理每日技术笔记",
            agent_id="notes_agent",
            run_id="run_001",
            trajectory_summary="成功使用 search_tool 检索文档，再用 summarize_skill 生成摘要，最后用 format_skill 格式化为 Markdown。总计 3 步，耗时 12s。",
        )
        assert draft is not None
        assert draft.source_type == "success"
        assert draft.category == "best_practice"
        assert draft.name.startswith("success-")
        assert "成功模式" in draft.display_name

    def test_analyze_success_requires_min_content(self):
        learner = get_auto_learner()
        draft = learner.analyze_success(
            task="short", agent_id="a", run_id="r",
            trajectory_summary=""  # empty — should return None
        )
        assert draft is None

    def test_analyze_failure_marks_source_type(self):
        learner = get_auto_learner()
        draft = learner.analyze_failure(
            error="assertion was relaxed from ==99.00 to >0",
            agent_id="ci_agent", run_id="run_002", task="fix CI test",
        )
        assert draft is not None
        assert draft.source_type == "failure"
        assert draft.max_edits == 4
        assert draft.edit_count > 0


class TestRejectedEditBuffer:
    """P1-1: Rejected edit buffer — prevents repeating bad edits."""

    def test_record_and_check_rejection(self):
        learner = get_auto_learner()
        draft = SkillDraft(
            name="test-draft", sop_body="# Rule: always use X tool",
            category="test", source_type="failure",
        )
        assert not learner.is_rejected_before(draft)
        learner.record_rejection(draft)
        assert learner.is_rejected_before(draft)

    def test_rejection_affects_confidence(self):
        learner = get_auto_learner()
        # Record a rejection of the exact draft that analyze_failure would produce
        draft = learner.analyze_failure(
            error="Rule: skip validation check",
            agent_id="test", run_id="r", task="test",
        )
        assert draft is not None
        # Record rejection of THIS specific draft
        learner.record_rejection(draft)
        # Re-check: this exact draft should now be rejected
        assert learner.is_rejected_before(draft)
        # Same error pattern should trigger rejection flag on next analyze
        draft2 = learner.analyze_failure(
            error="Rule: skip validation check",  # same error → same hash
            agent_id="test", run_id="r2", task="test",
        )
        # The new draft should have lowered confidence due to rejected buffer
        assert draft2 is not None
        assert learner.is_rejected_before(draft2) or draft2.confidence < 0.8

    def test_buffer_size_limit(self):
        learner = get_auto_learner()
        learner._buffer_max_size = 10
        for i in range(15):
            learner.record_rejection(SkillDraft(
                name=f"draft-{i}", sop_body=f"content-{i}",
                category="test", source_type="failure",
            ))
        assert len(learner._rejected_buffer) <= learner._buffer_max_size


class TestMaxEdits:
    """P1-2: Edit learning rate — max edits per draft."""

    def test_default_max_edits(self):
        learner = get_auto_learner()
        assert learner._max_edits == 4

    def test_max_edits_in_draft(self):
        learner = get_auto_learner()
        draft = learner.analyze_failure(
            error="test error", agent_id="test", run_id="r", task="test",
        )
        assert draft.max_edits == 4
        assert draft.edit_count > 0

    def test_custom_max_edits(self):
        import os
        os.environ["AIPLAT_MAX_EDITS_PER_DRAFT"] = "3"
        learner = AutoLearner()
        assert learner._max_edits == 3
        os.environ["AIPLAT_MAX_EDITS_PER_DRAFT"] = "4"  # restore

    def test_sop_contains_max_edits_limit(self):
        learner = get_auto_learner()
        draft = learner.analyze_failure(
            error="test", agent_id="t", run_id="r", task="test",
        )
        assert "编辑限制" in draft.sop_body
        assert f"最多 {learner._max_edits} 条" in draft.sop_body

    def test_success_sop_contains_max_edits_limit(self):
        learner = get_auto_learner()
        draft = learner.analyze_success(
            task="create report", agent_id="a", run_id="r",
            trajectory_summary="成功执行了搜索、分析、报告生成三个步骤。每个步骤都调用了对应的工具。最终输出格式化的 Markdown 文件。",
        )
        assert draft is not None
        assert "编辑限制" in draft.sop_body


class TestSkillDraftFields:
    """Verify new SkillDraft fields."""

    def test_source_type_field(self):
        d = SkillDraft(name="test")
        assert hasattr(d, "source_type")
        assert d.source_type == "failure"  # default

    def test_edit_count_field(self):
        d = SkillDraft(name="test")
        assert hasattr(d, "edit_count")
        assert d.edit_count == 0  # default

    def test_max_edits_field(self):
        d = SkillDraft(name="test")
        assert hasattr(d, "max_edits")
        assert d.max_edits == 4  # default
