"""
Production verification: SkillOpt three-piece end-to-end test.

Simulates real agent execution scenarios to validate:
  1. Dual-channel analysis: success + failure trajectories both produce valid drafts
  2. Rejected edit buffer: similar failed edits are remembered and flagged
  3. Edit learning rate: max_edits constraint is enforced in generated SOPs

Scenarios:
  A. CI Agent: assertion relaxation (should trigger failure analysis)
  B. Notes Agent: successful note organization (should trigger success analysis)
  C. Rejected pattern: repeat the same failure → buffer should flag it
"""
import pytest
from core.harness.learning import (
    get_auto_learner, AutoLearner, SkillDraft,
)
from core.harness.utils.prompt_loader import _sync_resolve


class TestProductionDualChannel:
    """Scenario A+B: Realistic production failure + success trajectories."""

    def setup_method(self):
        self.learner = get_auto_learner()

    def test_ci_agent_failure_assertion_relaxed(self):
        """CI Agent: relaxed test assertion from ==99.00 to >0.
        This is the exact scenario from the AgentOps article's Example 1."""
        error = (
            "AssertionError in test_order_discount: "
            "expected order.total == 99.00, but assertion was changed to > 0 "
            "by CI fix agent. Test passes but business logic is broken."
        )
        task = "修复 order-discount 模块的单测失败"
        agent_id = "ci_fix_agent"
        run_id = "run-ci-20260629-0017"

        draft = self.learner.analyze_failure(
            error=error, agent_id=agent_id, run_id=run_id, task=task,
        )

        # Assertions
        assert draft is not None, "CI failure should generate a draft"
        assert draft.source_type == "failure"
        assert draft.category == "self_learned"
        assert draft.name.startswith("fix-")
        assert "assertion" in draft.sop_body.lower()

        # Max edits constraint
        assert draft.max_edits == 4
        assert draft.edit_count > 0

        # SOP content checks
        assert "编辑限制" in draft.sop_body, "Max edits constraint must be in SOP"
        assert f"最多 {draft.max_edits} 条" in draft.sop_body

        # Confidence should be reasonable
        assert 0.0 < draft.confidence <= 1.0

    def test_notes_agent_success_trajectory(self):
        """Notes Agent: successfully organized daily technical notes.
        This simulates a real success pattern extraction."""
        trajectory = (
            "Step 1: 使用 search_tool 检索今日所有笔记文件 (3 files found). "
            "Step 2: 使用 classify_skill 按主题分类 (AI/工程/产品 3 categories). "
            "Step 3: 使用 summarize_skill 为每个类别生成摘要. "
            "Step 4: 使用 format_skill 输出结构化 Markdown 日报. "
            "总计 4 步, 耗时 23s, 用户满意度 95%."
        )
        task = "整理今日技术笔记，按主题分类并生成日报"
        agent_id = "notes_agent"
        run_id = "run-notes-20260630-0042"

        draft = self.learner.analyze_success(
            task=task, agent_id=agent_id, run_id=run_id,
            trajectory_summary=trajectory,
        )

        assert draft is not None, "Success trajectory should generate a draft"
        assert draft.source_type == "success"
        assert draft.category == "best_practice"
        assert draft.name.startswith("success-")
        assert "成功模式" in draft.display_name

        # SOP should contain structured rules
        assert "Rule 1" in draft.sop_body
        assert task[:60] in draft.sop_body

        # Success-derived rules should have high confidence
        assert draft.confidence >= 0.80

        # Max edits constraint present in success SOP too
        assert "编辑限制" in draft.sop_body

    def test_both_channels_produce_distinct_drafts(self):
        """Same task description, different channels → different drafts."""
        task = "修复 report 模块的测试失败"
        agent_id = "report_agent"
        run_id_fail = "run-fail-001"
        run_id_success = "run-success-001"

        fail_draft = self.learner.analyze_failure(
            error="Test failure in report module: KeyError on missing column",
            agent_id=agent_id, run_id=run_id_fail, task=task,
        )
        success_draft = self.learner.analyze_success(
            task=task, agent_id=agent_id, run_id=run_id_success,
            trajectory_summary="成功检索了 schema 定义, 补充了缺失的列映射, 测试全部通过.",
        )

        assert fail_draft is not None
        assert success_draft is not None
        assert fail_draft.source_type != success_draft.source_type
        assert fail_draft.name != success_draft.name
        assert fail_draft.category != success_draft.category


class TestProductionRejectedBuffer:
    """Scenario C: Rejected edit buffer prevents repeated bad edits."""

    def setup_method(self):
        self.learner = get_auto_learner()

    def test_repeated_failure_gets_buffered(self):
        """Same error pattern repeated 3 times → buffer should reduce confidence."""
        error = "SQL injection vulnerability in user_query parameter"
        task = "修复 user_query 的 SQL 注入问题"
        agent_id = "security_agent"

        # First attempt: generate and record rejection
        draft1 = self.learner.analyze_failure(
            error=error, agent_id=agent_id, run_id="run-sec-001", task=task,
        )
        assert draft1 is not None
        orig_conf = draft1.confidence

        self.learner.record_rejection(draft1)
        assert self.learner.is_rejected_before(draft1), "Rejected draft should be remembered"

        # Second attempt: same error → should be flagged
        draft2 = self.learner.analyze_failure(
            error=error, agent_id=agent_id, run_id="run-sec-002", task=task,
        )
        assert draft2 is not None
        # The buffer should have flagged this as a repeated pattern
        assert self.learner.is_rejected_before(draft2), (
            "Same error pattern should match rejected buffer"
        )
        # Confidence should be halved from original
        assert draft2.confidence < orig_conf, (
            f"Repeated pattern confidence ({draft2.confidence}) should be less than original ({orig_conf})"
        )

    def test_different_error_not_matched(self):
        """Buffer should not flag genuinely different errors."""
        error_a = "NullPointerException in payment module"
        error_b = "Timeout connecting to database in reporting module"
        task = "修复生产环境错误"
        agent_id = "ops_agent"

        draft_a = self.learner.analyze_failure(
            error=error_a, agent_id=agent_id, run_id="run-a", task=task,
        )
        self.learner.record_rejection(draft_a)

        draft_b = self.learner.analyze_failure(
            error=error_b, agent_id=agent_id, run_id="run-b", task=task,
        )
        # Different error → different hash → should NOT match
        assert not self.learner.is_rejected_before(draft_b), (
            "Different error should not match rejected buffer"
        )

    def test_buffer_capacity(self):
        """500-entry LRU buffer should evict oldest entries."""
        self.learner._buffer_max_size = 100
        for i in range(150):
            draft = SkillDraft(
                name=f"draft-{i}", sop_body=f"content variant {i}",
                category="test", source_type="failure",
            )
            self.learner.record_rejection(draft)
        assert len(self.learner._rejected_buffer) <= 100, "Buffer should not exceed capacity"


class TestProductionMaxEdits:
    """Edit learning rate constraint in real production scenarios."""

    def setup_method(self):
        self.learner = get_auto_learner()

    def test_max_edits_default_is_4(self):
        assert self.learner._max_edits == 4

    def test_failure_sop_contains_limit(self):
        draft = self.learner.analyze_failure(
            error="Memory leak in image processing pipeline",
            agent_id="perf_agent", run_id="run-perf-001", task="修复内存泄漏",
        )
        assert "编辑限制" in draft.sop_body
        assert f"最多 {self.learner._max_edits} 条" in draft.sop_body
        assert draft.max_edits == self.learner._max_edits

    def test_success_sop_contains_limit(self):
        draft = self.learner.analyze_success(
            task="优化数据库查询性能", agent_id="db_agent", run_id="run-db-001",
            trajectory_summary="使用 EXPLAIN ANALYZE 分析慢查询, 添加复合索引, 查询时间从 2.3s 降至 0.05s.",
        )
        assert draft is not None
        assert "编辑限制" in draft.sop_body
        assert f"最多 {self.learner._max_edits} 条" in draft.sop_body

    def test_env_var_override(self):
        import os
        os.environ["AIPLAT_MAX_EDITS_PER_DRAFT"] = "6"
        learner2 = AutoLearner()
        assert learner2._max_edits == 6
        os.environ["AIPLAT_MAX_EDITS_PER_DRAFT"] = "4"  # restore


class TestPromptLoaderIntegration:
    """Verify templates are correctly registered and resolvable."""

    def test_failure_template_resolves(self):
        result = _sync_resolve("skill-draft-failure",
            error="test_error", error_full="full_error_context",
            task="test_task", suggested_fix="apply fix X",
            max_edits="4",
        )
        assert "test_error" in result
        assert "编辑限制" in result
        assert "最多 4 条" in result

    def test_success_template_resolves(self):
        result = _sync_resolve("skill-draft-success",
            task="organize notes", task_full="organize daily technical notes",
            trajectory="searched, classified, summarized, formatted.",
            max_edits="3",
        )
        assert "organize notes" in result
        assert "编辑限制" in result
        assert "最多 3 条" in result

    def test_template_variables_not_leaked(self):
        """Unset variables should not appear as literal ${...} in output."""
        result = _sync_resolve("skill-draft-failure",
            error="E", error_full="F", task="T", suggested_fix="S", max_edits="4",
        )
        assert "${" not in result, "Template variables should be fully resolved"
