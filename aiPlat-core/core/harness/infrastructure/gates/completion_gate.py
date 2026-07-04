"""CompletionChecklistGate — post-generation task completion validation.

Phase 15: verifies that the Agent output actually answers the question, not just
that it's semantically valid (which is SemanticGate's job).

Two-layer verification:
  Layer 1: Fixed template checks (zero LLM, <1ms) — structure, confidence, targets
  Layer 2: LLM deep verification (conditional) — triggered when Layer 1 fails

Orthogonal to SemanticGate:
  SemanticGate: "is this conclusion ontologically valid?" (compliance)
  CompletionChecklistGate: "did this output actually answer the question?" (completeness)

Enabled by: AIPLAT_COMPLETION_GATE_ENABLED=true (default)
LLM threshold: AIPLAT_COMPLETION_GATE_LLM_THRESHOLD=1 (violation_count trigger)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.completion_gate")


# ═══════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChecklistItem:
    item: str       # what is being checked
    verified: bool  # whether it passed
    detail: str = "" # explanation


@dataclass
class CompletionGateResult:
    valid: bool
    status: str = "pass"  # "pass" | "needs_review"
    checklist: List[ChecklistItem] = field(default_factory=list)
    llm_verification_triggered: bool = False


# ═══════════════════════════════════════════════════════════════
# CompletionChecklistGate
# ═══════════════════════════════════════════════════════════════

class CompletionChecklistGate:
    """Post-generation task completion validator.

    Checks whether the output actually answers the original question —
    not whether it's ontologically valid (that's SemanticGate's job).
    """

    def __init__(self, llm_threshold: int = None):
        self._llm_threshold = llm_threshold or int(
            os.getenv("AIPLAT_COMPLETION_GATE_LLM_THRESHOLD", "1")
        )

    def verify(
        self,
        output: dict,
        question: str = "",
        *,
        semantic_violation_count: int = 0,
    ) -> CompletionGateResult:
        """Run completion validation against the original question.

        Args:
            output: Agent decision/output dict.
            question: Original user question (used for LLM deep check).
            semantic_violation_count: Violation count from SemanticGate
                                      (used as trigger for LLM deep verification).

        Returns:
            CompletionGateResult with pass/needs_review status.
        """
        checklist: List[ChecklistItem] = []

        # ═══════════════════════════════════════════════════════
        # Layer 1: Fixed template checks (zero LLM)
        # ═══════════════════════════════════════════════════════

        # Check 1: Output has meaningful content
        answer = (
            output.get("answer", "") or
            output.get("output", "") or
            str(output)
        )
        has_content = bool(answer) and len(str(answer)) >= 10
        checklist.append(ChecklistItem(
            item="输出包含有意义的内容（≥10 字符）",
            verified=has_content,
            detail=f"长度={len(str(answer))}" if has_content else "输出为空或过短",
        ))

        # Check 2: Confidence is in valid range [0, 1]
        confidence = output.get("confidence", None)
        if confidence is not None:
            try:
                conf_val = float(confidence)
                conf_valid = 0.0 <= conf_val <= 1.0
            except (ValueError, TypeError):
                conf_valid = False
        else:
            conf_valid = True  # no confidence field = not applicable
            conf_val = None
        checklist.append(ChecklistItem(
            item="置信度在有效范围内 [0, 1]",
            verified=conf_valid,
            detail=f"confidence={conf_val}" if conf_val is not None else "无 confidence 字段",
        ))

        # Check 3: If recommended_actions exist, each action has a target
        actions = output.get("recommended_actions", [])
        if isinstance(actions, list) and actions:
            all_have_target = all(
                isinstance(a, dict) and a.get("target", "").strip()
                for a in actions
            )
            checklist.append(ChecklistItem(
                item="所有 recommended_actions 都指定了 target",
                verified=all_have_target,
                detail=f"actions={len(actions)}, all_have_target={all_have_target}",
            ))
        else:
            checklist.append(ChecklistItem(
                item="recommended_actions 检查",
                verified=True,
                detail="无 recommended_actions（不适用）",
            ))

        # Check 4: Severity field is present and in valid values
        severity = output.get("severity", "")
        valid_severities = {"critical", "elevated", "normal", ""}
        sev_valid = severity in valid_severities
        checklist.append(ChecklistItem(
            item="severity 字段值有效",
            verified=sev_valid,
            detail=f"severity={severity}" if sev_valid else f"无效值: {severity}",
        ))

        # ═══════════════════════════════════════════════════════
        # Layer 2: LLM deep verification (conditional)
        # ═══════════════════════════════════════════════════════
        llm_triggered = False
        template_failures = [c for c in checklist if not c.verified]
        should_llm_check = (
            len(template_failures) >= self._llm_threshold or
            semantic_violation_count > 0
        )

        if should_llm_check and question:
            llm_triggered = True
            try:
                llm_items = self._llm_deep_verify(output, question)
                checklist.extend(llm_items)
            except Exception as e:
                logger.debug("LLM deep verification failed: %s", e)

        # ═══════════════════════════════════════════════════════
        # Determine status
        # ═══════════════════════════════════════════════════════
        failures = [c for c in checklist if not c.verified]
        valid = len(failures) == 0
        status = "pass" if valid else "needs_review"

        return CompletionGateResult(
            valid=valid,
            status=status,
            checklist=checklist,
            llm_verification_triggered=llm_triggered,
        )

    # ═══════════════════════════════════════════════════════════
    # LLM deep verification
    # ═══════════════════════════════════════════════════════════

    def _llm_deep_verify(self, output: dict, question: str) -> List[ChecklistItem]:
        """Generate checklist from question, verify each item against output."""
        import asyncio

        async def _run():
            from core.harness.syscalls.llm import sys_llm_generate
            from core.harness.utils.model_injection import best_model_for_purpose

            answer = output.get("answer", output.get("output", str(output)))
            prompt = (
                f"原始问题：{question}\n\n"
                f"AI 的输出：{answer[:2000]}\n\n"
                f"请检查 AI 输出是否完整回答了原始问题。请按以下格式返回 JSON:\n"
                f'{{"checks": ['
                f'  {{"item": "检查项描述", "pass": true/false, "detail": "简要说明"}}'
                f']}}'
            )
            resp = await sys_llm_generate(
                None,
                [{"role": "user", "content": prompt}],
                model_name=best_model_for_purpose("doc_llm"),
                temperature=0,
                max_tokens=300,
            )
            text = getattr(resp, "content", "") or str(resp)

            # Parse JSON
            import json
            import re
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                m = re.search(r'\{[\s\S]*"checks"[\s\S]*\}', text)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except (json.JSONDecodeError, TypeError):
                        return []
                else:
                    return []

            checks = data.get("checks", [])
            return [
                ChecklistItem(
                    item=c.get("item", "unknown"),
                    verified=c.get("pass", False),
                    detail=c.get("detail", ""),
                )
                for c in checks[:5]
            ]

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return []  # can't nest async calls
            return loop.run_until_complete(_run())
        except Exception:
            return []
