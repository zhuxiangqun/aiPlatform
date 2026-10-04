"""Prompt Auditor — static and runtime AGENT.md quality checks.

Per CLAUDE.md §5.27 (AGENT.md撰写原则):
- Rule 1: AI 不能执行形容词（"写高质量代码" → "使用 ## FILE: 格式"）
- Rule 2: 三层分离（SOUL.md / AGENT.md / MEMORY.md）
- Rule 3: 交接协议 5 项字段
- Rule 4: 维护原则（两错法则，<100 行）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.audit.prompt")


@dataclass
class PromptAuditRecord:
    agent_id: str
    audit_timestamp: float
    sop_body_chars: int = 0
    sop_body_lines: int = 0
    prompt_extra_chars: int = 0
    total_estimated_tokens: int = 0
    compliance_issues: List[Dict[str, str]] = field(default_factory=list)
    injection_risk_score: float = 0.0
    instruction_count: int = 0
    handoff_complete: bool = False
    anti_patterns_found: List[str] = field(default_factory=list)
    delegation_style: str = "unknown"  # "instruction_dispatch" | "intent_delegation" | "mixed"

    @property
    def has_issues(self) -> bool:
        return bool(self.compliance_issues or self.anti_patterns_found)

    @property
    def score(self) -> float:
        """0-100 quality score."""
        base = 100.0
        base -= len(self.compliance_issues) * 8
        base -= len(self.anti_patterns_found) * 10
        if self.sop_body_lines > 100:
            base -= (self.sop_body_lines - 100) * 0.5
        if not self.handoff_complete:
            base -= 15
        return max(0.0, min(100.0, base))


# Adjectives that signal vague/unactionable instructions (CLAUDE.md §5.27 Rule 1)
# Patterns defined in prompt_audit_rules.py for extensibility.

# Required handoff fields (CLAUDE.md §5.27 Rule 2.1)
# Fields defined in prompt_audit_rules.py for extensibility.


def parse_agent_md(path: str) -> Dict[str, Any]:
    """Canonical AGENT.md parser. Replace all 4 duplicate implementations.

    Returns dict with all frontmatter fields + _sop_body (Markdown body after ---).
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    result: Dict[str, Any] = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            import yaml
            try:
                fm = yaml.safe_load(parts[1]) or {}
                result.update(fm)
            except Exception as e:
                logging.debug(str(e), exc_info=True)
            result["_sop_body"] = parts[2].strip()
    else:
        result["_sop_body"] = raw.strip()
    return result


def audit_agent_md(agent_id: str, sop_body: str, frontmatter: Dict = None) -> PromptAuditRecord:
    """Static audit of AGENT.md prompt quality at load time."""
    import re
    import time
    fm = frontmatter or {}
    body = sop_body or ""
    lines = body.split("\n")
    record = PromptAuditRecord(
        agent_id=agent_id,
        audit_timestamp=time.time(),
        sop_body_chars=len(body),
        sop_body_lines=len(lines),
        prompt_extra_chars=len(str(fm.get("prompt_extra", ""))),
    )

    # Check for vague adjectives
    from core.harness.audit.prompt_audit_rules import VAGUE_ADJECTIVES, HANDOFF_FIELDS, PIPELINE_FM_FIELDS

    for pattern, tag in VAGUE_ADJECTIVES:
        if re.search(pattern, body):
            record.anti_patterns_found.append(tag)

    # Check handoff completeness
    present = sum(1 for f in HANDOFF_FIELDS if f in body)
    record.handoff_complete = present >= 5
    if present < 5:
        missing = [f for f in HANDOFF_FIELDS if f not in body]
        record.compliance_issues.append({
            "rule": "handoff_completeness",
            "detail": f"Missing handoff fields: {missing}",
        })

    # Check frontmatter completeness for pipeline agents
    if fm.get("output_artifact"):
        for f in PIPELINE_FM_FIELDS:
            if not fm.get(f):
                record.compliance_issues.append({
                    "rule": "frontmatter_completeness",
                    "detail": f"Pipeline agent missing frontmatter field: {f}",
                })

    # Count imperative instructions
    record.instruction_count = len([l for l in lines if l.strip().startswith(("- ", "* ", "1.", "2.", "3."))])

    # Token estimate (rough: 1 token ≈ 4 chars)
    record.total_estimated_tokens = record.sop_body_chars // 4

    # Delegation style detection: intent_delegation vs instruction_dispatch
    record.delegation_style = _detect_delegation_style(body, lines)

    if record.has_issues:
        logger.warning("AGENT.md audit for %s: score=%.0f issues=%d anti=%d",
                       agent_id, record.score, len(record.compliance_issues), len(record.anti_patterns_found))
    if record.delegation_style == "instruction_dispatch":
        record.anti_patterns_found.append("instruction_dispatch_style")
        record.compliance_issues.append({
            "rule": "delegation_style",
            "detail": "SOP uses instruction-dispatch style (detailed step-by-step). Consider intent-delegation style: define acceptance criteria + boundary constraints, let agent plan its own execution.",
        })
    return record


_VAGUE_LABELS: Dict[str, str] = {
    "vague_quality_code": "「写高质量代码」不可执行——改为具体格式/命令/验收标准",
    "vague_best_practices": "「遵循最佳实践」不可执行——写出可检查的步骤或约束",
    "vague_security": "「注意安全」不可执行——列出具体检查项（注入/鉴权/脱敏等）",
    "vague_full_testing": "「充分测试」不可执行——写明测试命令与覆盖要求",
    "vague_maintainable": "「确保可维护」不可执行——写明模块边界/命名/禁止事项",
    "vague_elegant": "「编写优雅的…」不可执行——改为具体产出格式",
    "vague_performance": "「高性能」不可执行——写明延迟/吞吐等可度量目标",
}


def prompt_audit_to_issues(
    record: PromptAuditRecord,
    *,
    frontmatter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Map PromptAuditRecord → AssetAudit issue dicts for Edit Agent「AI 审核」.

    Severity policy (avoid flooding standalone trial agents):
    - vague adjectives → warning
    - pipeline frontmatter gaps → warning
    - handoff fields → warning only when ``output_artifact`` set (pipeline);
      otherwise skipped (trial/chat agents rarely need 5-way handoff)
    - instruction_dispatch → info (many code agents intentionally use numbered SOP)
    - body >100 lines → info
    """
    from core.management.asset_audit import issue

    fm = frontmatter if isinstance(frontmatter, dict) else {}
    is_pipeline = bool(str(fm.get("output_artifact") or "").strip())
    out: List[Dict[str, Any]] = []
    seen: set = set()

    for tag in record.anti_patterns_found or []:
        tag_s = str(tag or "").strip()
        if not tag_s or tag_s == "instruction_dispatch_style":
            continue
        cat = f"prompt_{tag_s}"
        if cat in seen:
            continue
        seen.add(cat)
        out.append(
            issue(
                severity="warning",
                category=cat,
                field="sop_body",
                message=_VAGUE_LABELS.get(tag_s, f"AGENT.md 反模式：{tag_s}"),
                suggestion="把形容词改成可执行约束（格式、命令、字段、禁止项）",
                current=tag_s,
            )
        )

    for ci in record.compliance_issues or []:
        if not isinstance(ci, dict):
            continue
        rule = str(ci.get("rule") or "").strip()
        detail = str(ci.get("detail") or "").strip()
        if rule == "handoff_completeness":
            if not is_pipeline:
                continue
            cat = "prompt_handoff_incomplete"
            if cat in seen:
                continue
            seen.add(cat)
            from core.management.asset_audit import fix_append_sop_handoff

            out.append(
                issue(
                    severity="warning",
                    category=cat,
                    field="sop_body",
                    message=(
                        "流水线 Agent 的 AGENT.md 缺少交接协议字段"
                        "（做了什么/产出物在哪/如何验证/已知问题/下一步）"
                    ),
                    suggestion=(
                        "在正文补齐 CLAUDE.md §5.27 交接 5 项，便于下游阶段接手。"
                        "一键修复可追加交接骨架，请再按本阶段真实产物改写。"
                    ),
                    current=detail,
                    fix=fix_append_sop_handoff(),
                )
            )
        elif rule == "frontmatter_completeness":
            cat = "prompt_frontmatter_incomplete"
            key = f"{cat}:{detail}"
            if key in seen:
                continue
            seen.add(key)
            out.append(
                issue(
                    severity="warning",
                    category=cat,
                    field="frontmatter",
                    message=f"流水线 Agent frontmatter 不完整：{detail}",
                    suggestion="补齐 agent_type / output_artifact / phase 等流水线字段",
                    current=detail,
                )
            )
        elif rule == "delegation_style":
            cat = "prompt_instruction_dispatch"
            if cat in seen:
                continue
            seen.add(cat)
            out.append(
                issue(
                    severity="info",
                    category=cat,
                    field="sop_body",
                    message="AGENT.md 偏「指令派发」风格（细步骤堆叠）",
                    suggestion=(
                        "可改为：验收标准 + 边界约束，由 Agent 自行规划步骤（intent-delegation）"
                    ),
                    current=record.delegation_style,
                )
            )

    if record.sop_body_lines > 100:
        out.append(
            issue(
                severity="info",
                category="prompt_body_long",
                field="sop_body",
                message=f"AGENT.md 正文偏长（{record.sop_body_lines} 行）——维护成本高",
                suggestion="按两错法则拆到 docs/，AGENT.md 只保留核心铁律与路由（建议 <100 行）",
                current=record.sop_body_lines,
            )
        )

    actionable = [i for i in out if str(i.get("severity")) in ("error", "warning")]
    if not actionable and (record.sop_body_chars or 0) > 0:
        out.append(
            issue(
                severity="info",
                category="prompt_md_ok",
                field="sop_body",
                message=(
                    f"AGENT.md 正文质量门禁通过（score≈{record.score:.0f}，"
                    f"{record.sop_body_chars} 字 / {record.sop_body_lines} 行）"
                ),
                suggestion="已检查模糊形容词与（流水线）交接/frontmatter；产物质量仍由执行后复核。",
            )
        )
    return out


def _detect_delegation_style(body: str, lines: List[str]) -> str:
    import re
    intent_signals = 0
    dispatch_signals = 0
    if re.search(r'验收标准|acceptance.criteria|边界约束|boundary.constraint|边界.*不能|禁止', body or ""):
        intent_signals += 1
    if re.search(r'自行规划|自己决定|自行选择|自主|you decide', body or ""):
        intent_signals += 1
    if len([l for l in lines if l.strip().startswith("步骤")]) >= 3:
        dispatch_signals += 1
    if len([l for l in lines if re.match(r'^\d+[\.\)、] ', l.strip())]) >= 4:
        dispatch_signals += 1
    if re.search(r'(你必须|你必须按|必须使用|按照以下格式|使用标准模板)', body or ""):
        dispatch_signals += 1
    if re.search(r'(完成后把.*发给我|我审核通过后|等我确认)', body or ""):
        dispatch_signals += 2
    if intent_signals > 0 and dispatch_signals == 0:
        return "intent_delegation"
    if dispatch_signals > 0 and intent_signals == 0:
        return "instruction_dispatch"
    if dispatch_signals > 0:
        return "mixed"
    return "unknown"
