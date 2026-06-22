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
    confidence: float = 0.0           # Agent 自评置信度 [0, 1]
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
            confidence=0.8,  # Agent's self-assessed confidence
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._storage[draft_name] = draft
        return draft

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
            # Phase 4.3: Hook LoRA AutoTrigger
            try:
                from core.harness.training.auto_trigger import get_lora_auto_trigger
                await get_lora_auto_trigger().on_skill_approved(draft)
            except Exception:
                pass
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

    def list_drafts(self, status: str = "") -> List[Dict[str, Any]]:
        """列出所有草稿。"""
        drafts = list(self._storage.values())
        if status:
            drafts = [d for d in drafts if d.status == status]
        return [d.to_dict() for d in drafts]

    # ── Internal ────────────────────────────────────────────────────────

    def _generate_sop(self, task: str, error: str, suggested_fix: str) -> str:
        """生成 Skill SOP 操作手册。"""
        return f"""# {error[:50]}

## 做了什么
自动生成的修复 Skill，用于处理以下类型的错误。

## 触发场景
当 Agent 执行任务时遇到以下错误模式时触发：
```
{error[:200]}
```

## 操作步骤
1. 识别错误类型和根因
2. 应用修复策略
3. 验证修复结果

## 原始任务
{task[:300]}

## 建议修复
{suggested_fix[:500] if suggested_fix else "请人工补充修复步骤"}

## 如何验证
重新执行原始任务，确认错误不再出现。

## 已知问题
此 Skill 由 AI 自动生成，可能不完整。请人工审核后使用。
"""


# ── Global singleton ─────────────────────────────────────────────────────

import hashlib  # noqa: E402

_auto_learner: Optional[AutoLearner] = None


def get_auto_learner() -> AutoLearner:
    global _auto_learner
    if _auto_learner is None:
        _auto_learner = AutoLearner()
    return _auto_learner
