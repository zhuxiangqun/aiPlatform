"""
SkillDraft — AI 草稿 + 人工确认 自学习系统

Agent 失败后自动分析根因 → 生成 SkillDraft.yaml → SkillSimulator 沙盒预检
→ 推送到管理端审核队列 → 管理员审批 → 注册到 SkillRegistry

安全底线:
  - 自学习 Skill 必须标记 source=self_learned + status=draft
  - 审批通过前不可被 Agent 调用
  - 同一 Agent 连续 3 次低质量 → 自动关闭 24h
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path


@dataclass
class SkillDraft:
    """Agent 自动生成的 Skill 草稿。"""

    name: str
    display_name: str = ""
    category: str = "general"
    description: str = ""
    trigger_conditions: List[Dict[str, Any]] = field(default_factory=list)
    sop_body: str = ""                # Markdown 操作手册
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    effects: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    source_run_id: str = ""           # 触发生成的 run_id
    source_agent_id: str = ""         # 触发生成的 agent_id
    source_error: str = ""            # 触发生成的错误信息
    source_type: str = "failure"      # "failure" | "success" — dual-channel analysis (SkillOpt-inspired)
    confidence: float = 0.0           # Agent 自评置信度 [0, 1]
    edit_count: int = 0               # SOP 中包含的实际改动数量 (SkillOpt "text learning rate")
    max_edits: int = 4                # 本轮允许的最大改动数 (SkillOpt default, env: AIPLAT_MAX_EDITS_PER_DRAFT)
    status: str = "draft"             # draft / simulated / pending_review / approved / rejected
    simulation_pass_rate: float = 0.0 # SkillSimulator 模拟通过率
    created_at: str = ""              # ISO timestamp
    created_by: str = "auto_learner"

    def to_yaml(self) -> str:
        """导出为 SKILL.md frontmatter + SOP body。"""
        import yaml
        fm = {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "version": "1.0.0",
            "status": "draft",
            "execution_type": "prompt",
            "effects": self.effects,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "metadata": {
                "source": "self_learned",
                "source_run_id": self.source_run_id,
                "source_agent_id": self.source_agent_id,
                "confidence": self.confidence,
                "simulation_pass_rate": self.simulation_pass_rate,
                "created_at": self.created_at,
            }
        }
        return f"---\n{yaml.dump(fm, allow_unicode=True, default_flow_style=False)}---\n\n{self.sop_body}\n"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "confidence": self.confidence,
            "status": self.status,
            "source_run_id": self.source_run_id,
            "source_error": self.source_error,
            "simulation_pass_rate": self.simulation_pass_rate,
            "created_at": self.created_at,
        }


class AutoLearner:
    """自学习编排器。

    核心流程:
        1. Agent 失败 → analyze_failure() → 生成 SkillDraft
        2. SkillSimulator.validate() → 沙盒预检
        3. submit_for_review() → 推送到管理端
        4. approve() / reject() → 注册或丢弃
    """

    def __init__(self, *, draft_dir: str = ""):
        home = os.path.expanduser("~")
        self._draft_dir = Path(draft_dir or os.path.join(home, ".aiplat", "skill_drafts"))
        self._draft_dir.mkdir(parents=True, exist_ok=True)
        self._storage: Dict[str, SkillDraft] = {}
        self._agent_failure_count: Dict[str, List[float]] = {}  # agent_id → [timestamps]
        self._agent_suspended: Dict[str, float] = {}  # agent_id → suspended_until_ts
        # SkillOpt-inspired: rejected edit buffer (prevents repeating bad edits)
        self._rejected_buffer: set = set()
        self._buffer_max_size = int(os.getenv("AIPLAT_REJECTED_BUFFER_SIZE", "500"))
        # SkillOpt-inspired: text learning rate (max edits per draft)
        self._max_edits = int(os.getenv("AIPLAT_MAX_EDITS_PER_DRAFT", "4"))

    # ── Public API ──────────────────────────────────────────────────────

    def analyze_failure(
        self,
        error: str,
        *,
        agent_id: str = "",
        run_id: str = "",
        task: str = "",
        suggested_fix: str = "",
    ) -> SkillDraft:
        """分析 Agent 失败并生成 SkillDraft。

        Args:
            error: 错误信息
            agent_id: 触发 Agent ID
            run_id: 触发 run_id
            task: 原始任务描述
            suggested_fix: Agent 建议的修复方案

        Returns:
            生成的 SkillDraft
        """
        # Generate a unique skill name
        error_id = hashlib.md5(error.encode()).hexdigest()[:8] if error else uuid.uuid4().hex[:8]
        draft_name = f"fix-{error_id}"

        draft = SkillDraft(
            name=draft_name,
            display_name=f"自动修复: {error[:50]}",
            category="self_learned",
            description=f"自动生成的 Skill，用于处理: {error[:100]}",
            sop_body=self._generate_sop(task, error, suggested_fix),
            effects=[{"type": "read", "resources": [], "idempotent": True, "rollback_available": False}],
            source_run_id=run_id,
            source_agent_id=agent_id,
            source_error=error,
            source_type="failure",
            confidence=0.8,
            max_edits=self._max_edits,
            edit_count=3,  # Default 3-step SOP
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # Check rejected buffer — if similar edit was previously rejected, flag it
        if self.is_rejected_before(draft):
            draft.confidence *= 0.5
            draft.description += " [WARNING: similar edit was previously rejected — confidence halved]"
        self._storage[draft_name] = draft
        # § v4.1: Enrich draft with historical rejection feedback from ExperienceVectorCache
        try:
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                _asyncio.ensure_future(self._enrich_with_history(draft, error))
        except Exception:
            logging.getLogger(__name__).debug('analyze_failure failed', exc_info=True)
        return draft

    def analyze_success(
        self,
        task: str,
        *,
        agent_id: str = "",
        run_id: str = "",
        trajectory_summary: str = "",
    ) -> Optional[SkillDraft]:
        """分析 Agent 成功轨迹并生成可复用规则 Draft（双通道分析的 success 通道）。

        与 analyze_failure 的差异:
          - 输入: 成功轨迹摘要（而非错误信息）
          - 方向: 记住"怎么做对的"（而非"避免怎么做错的"）
          - 标记: source_type="success"

        Args:
            task: 原始任务描述
            agent_id: 触发 Agent ID
            run_id: 触发 run_id
            trajectory_summary: 成功执行轨迹摘要（工具序列、关键步骤、最终输出）

        Returns:
            生成的 SkillDraft，如果成功模式无明显可提取规则则返回 None
        """
        if not trajectory_summary or len(trajectory_summary) < 30:
            return None

        success_id = hashlib.md5(f"{task}{agent_id}{run_id}".encode()).hexdigest()[:8]
        draft_name = f"success-{success_id}"

        sop = self._generate_sop_from_success(task, trajectory_summary)
        if not sop or len(sop) < 50:
            return None

        draft = SkillDraft(
            name=draft_name,
            display_name=f"成功模式: {task[:50]}",
            category="best_practice",
            description=f"从成功执行中提取的可复用规则: {task[:100]}",
            sop_body=sop,
            effects=[{"type": "read", "resources": [], "idempotent": True, "rollback_available": False}],
            source_run_id=run_id,
            source_agent_id=agent_id,
            source_error="",
            source_type="success",
            confidence=0.85,
            max_edits=self._max_edits,
            edit_count=sop.count("## Rule") if "## Rule" in sop else 1,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._storage[draft_name] = draft

        try:
            import asyncio as _asyncio2
            loop = _asyncio2.get_event_loop()
            if loop.is_running():
                _asyncio2.ensure_future(self._enrich_with_history(draft, trajectory_summary[:200]))
        except Exception:
            logging.getLogger(__name__).debug('analyze_success failed', exc_info=True)
        return draft

    # ── Rejected Edit Buffer (SkillOpt "refused-edit buffer") ──

    @staticmethod
    def _hash_edit_pattern(draft: SkillDraft) -> str:
        """MD5 hash of draft identity — used for rejection de-duplication."""
        return hashlib.md5(
            f"{draft.name}:{draft.sop_body[:200]}:{draft.source_type}".encode()
        ).hexdigest()[:16]

    def record_rejection(self, draft: SkillDraft) -> None:
        """Record a rejected draft pattern to prevent future similar edits."""
        h = self._hash_edit_pattern(draft)
        self._rejected_buffer.add(h)
        if len(self._rejected_buffer) > self._buffer_max_size:
            self._rejected_buffer = set(list(self._rejected_buffer)[-self._buffer_max_size:])
        logging.getLogger("aiplat.auto_learner").debug(
            "Rejected buffer: %d entries, added %s", len(self._rejected_buffer), h
        )

    def is_rejected_before(self, draft: SkillDraft) -> bool:
        """Check if a similar draft pattern was previously rejected."""
        return self._hash_edit_pattern(draft) in self._rejected_buffer

    async def _enrich_with_history(self, draft: SkillDraft, error: str) -> None:
        try:
            from core.harness.learning.experience_vector import get_experience_cache
            cache = get_experience_cache()
            context = await cache.enrich_skill_draft(error)
            if context.get("similar_failures") or context.get("similar_successes"):
                enrichment = "\n\n## 历史经验（错题本）\n"
                for f in context.get("similar_failures", [])[:3]:
                    enrichment += f"- [失败] {f.get('summary', '')[:200]}\n"
                for s in context.get("similar_successes", [])[:2]:
                    enrichment += f"- [成功] {s.get('summary', '')[:200]}\n"
                if context.get("best_practice"):
                    enrichment += f"\n**最佳实践**: {context['best_practice'][:300]}"
                draft.sop_body = (draft.sop_body or "") + enrichment
                draft.description = (draft.description or "") + " [历史经验已注入]"
        except Exception:
            logging.getLogger(__name__).debug('_enrich_with_history failed', exc_info=True)

    def is_suspended(self, agent_id: str) -> bool:
        """检查 Agent 是否因低质量而被暂停。"""
        if agent_id not in self._agent_suspended:
            return False
        return time.time() < self._agent_suspended[agent_id]

    def record_failure_quality(self, agent_id: str, quality: float):
        """记录 Agent 的 SkillDraft 质量评分。

        连续 3 次 < 0.5 → 暂停 24h
        """
        now = time.time()
        if agent_id not in self._agent_failure_count:
            self._agent_failure_count[agent_id] = []
        # Keep only last 10 entries
        self._agent_failure_count[agent_id] = self._agent_failure_count[agent_id][-9:] + [now]

        if quality < 0.5:
            recent = [t for t in self._agent_failure_count[agent_id] if now - t < 86400]
            if len(recent) >= 3:
                self._agent_suspended[agent_id] = now + 86400  # 24h
                import logging
                logging.getLogger("aiplat.auto_learner").warning(
                    f"Agent '{agent_id}' suspended for 24h (3 low-quality drafts)"
                )

    async def simulate(self, draft: SkillDraft) -> float:
        """在 Docker 沙盒中用历史 run 回放 Skill，返回模拟通过率。"""
        try:
            from .skill_simulator import SkillSimulator
            simulator = SkillSimulator()
            pass_rate = await simulator.validate(draft)
            draft.simulation_pass_rate = pass_rate
            if pass_rate >= 0.8:
                draft.status = "pending_review"
            else:
                draft.status = "rejected"
                draft.description += f" [AUTO-REJECTED: simulation_pass_rate={pass_rate:.0%}]"
            return pass_rate
        except Exception:
            # Simulator unavailable → manual review required
            draft.status = "pending_review"
            return -1.0

    def submit_for_review(self, draft: SkillDraft) -> str:
        """提交 SkillDraft 到审核队列。

        Returns:
            draft_id
        """
        draft_path = self._draft_dir / f"{draft.name}.yaml"
        draft_path.write_text(draft.to_yaml(), encoding="utf-8")
        return draft.name

    async def approve(self, draft_name: str) -> bool:
        """审批通过 → 注册到 SkillRegistry。"""
        draft = self._storage.get(draft_name)
        if not draft:
            return False
        draft.status = "approved"
        try:
            # Register in SkillRegistry
            # (Actual registration is done by management API)
            approved_path = Path(os.path.expanduser("~/.aiplat/skills")) / draft_name
            approved_path.mkdir(parents=True, exist_ok=True)
            (approved_path / "SKILL.md").write_text(draft.to_yaml(), encoding="utf-8")
            # ── Register in SkillRegistry so it's immediately available ──
            try:
                from core.api.core_facade import get_skill_registry
                from core.apps.skills.discovery import create_discovery
                discovery = create_discovery()
                skills = await discovery.scan_directory(str(approved_path))
                for skill in skills:
                    get_skill_registry().register(skill)
            except Exception as e:
                logging.debug("SkillRegistry registration skipped: %s", e)
            # Phase 4.3: Hook LoRA AutoTrigger
            try:
                from core.harness.training.auto_trigger import get_lora_auto_trigger
                await get_lora_auto_trigger().on_skill_approved(draft)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            return True
        except Exception:
            return False

    def reject(self, draft_name: str, reason: str = "") -> bool:
        """拒绝 SkillDraft。"""
        draft = self._storage.get(draft_name)
        if not draft:
            return False
        draft.status = "rejected"
        if reason:
            draft.description += f" [REJECTED: {reason}]"
        return True

    async def process_pending(self, *, min_confidence: float = 0.9) -> Dict[str, Any]:
        """处理待审核 Draft — 自动审批高置信度 (>threshold) 的 Draft。
        
        Phase 5.5: EvolutionEngine 夜间调用。
        """
        auto_approved = 0
        total_pending = 0
        for draft_name in list(self._storage.keys()):
            draft = self._storage.get(draft_name)
            if not draft or draft.status != "pending_review":
                continue
            total_pending += 1
            if draft.confidence >= min_confidence and draft.simulation_pass_rate >= 0.8:
                # Phase 6: 安全审计——高危漏洞阻断自动审批
                try:
                    from core.harness.security.code_auditor import CodeAuditor
                    auditor = CodeAuditor()
                    audit = auditor.audit(getattr(draft, "sop_body", ""), skill_name=draft_name)
                    if audit.high_count > 0:
                        logging.warning(f"AutoLearner: {draft_name} blocked by CodeAuditor ({audit.high_count} high issues)")
                        continue  # 跳过，不自动审批
                except Exception as e:
                    logging.debug(str(e), exc_info=True)
                await self.approve(draft_name)
                auto_approved += 1
        return {"pending": total_pending, "auto_approved": auto_approved}

    def list_drafts(self, status: str = "") -> List[Dict[str, Any]]:
        """列出所有草稿。"""
        drafts = list(self._storage.values())
        if status:
            drafts = [d for d in drafts if d.status == status]
        return [d.to_dict() for d in drafts]

    # ── Internal ────────────────────────────────────────────────────────

    def _generate_sop(self, task: str, error: str, suggested_fix: str) -> str:
        """生成 Skill SOP 操作手册（失败修复方向）。委托 prompt_loader 统一管理模板。"""
        from core.harness.utils.prompt_loader import _sync_resolve
        return _sync_resolve("skill-draft-failure",
            error=error[:50],
            error_full=error[:200],
            task=task[:300],
            suggested_fix=suggested_fix[:500] if suggested_fix else "请人工补充修复步骤",
            max_edits=str(self._max_edits),
        )

    def _generate_sop_from_success(self, task: str, trajectory_summary: str) -> str:
        """从成功轨迹中提取可复用的规则。委托 prompt_loader 统一管理模板。"""
        from core.harness.utils.prompt_loader import _sync_resolve
        return _sync_resolve("skill-draft-success",
            task=task[:60],
            task_full=task[:300],
            trajectory=trajectory_summary[:400],
            max_edits=str(self._max_edits),
        )


# ── Global singleton ─────────────────────────────────────────────────────

import hashlib  # noqa: E402

_auto_learner: Optional[AutoLearner] = None


def get_auto_learner() -> AutoLearner:
    global _auto_learner
    if _auto_learner is None:
        _auto_learner = AutoLearner()
    return _auto_learner
