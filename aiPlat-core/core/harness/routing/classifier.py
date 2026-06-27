"""
Routing classifier — 规则 + LLM 双重意图分类引擎。

Architecture:
  1. Rule-based keyword matching (~0.5ms)
  2. If confidence < threshold → LLM fallback (opt-in, ~3s)
  3. Returns unified RoutingResult
"""

from __future__ import annotations
import logging

import json as _json
import re as _re
from typing import Any, Dict, List, Optional, Tuple

from core.schemas_routing import (
    ConfidenceLevel,
    IntentCategory,
    RouteKind,
    RoutingContext,
    RoutingResult,
    SuggestedRoute,
)


# ── Intent patterns loaded from configuration ─────────────────────────────
# All business-specific labels extracted to intent_patterns.yaml per §5.29 v4.1

def _load_patterns() -> dict:
    """Load intent patterns from YAML config. Falls back to built-in defaults."""
    import os, yaml
    from pathlib import Path
    config_path = Path(__file__).resolve().parent / "intent_patterns.yaml"
    try:
        raw = yaml.safe_load(open(config_path)) or {}
    except Exception:
        raw = {}
    return raw.get("intent_patterns", {})


_patterns = _load_patterns()

# Build rule table from YAML
_RULE_TABLE: List[Tuple[str, IntentCategory, float, Dict[int, str]]] = []
for entry in _patterns.get("rule_table", []):
    if len(entry) >= 3:
        try:
            category = getattr(IntentCategory, entry[1], None)
            if category is not None:
                _RULE_TABLE.append((str(entry[0]), category, float(entry[2]), {}))
        except (AttributeError, ValueError):
            continue

# Suggested agent display labels per intent
_SUGGESTED_AGENT_LABELS: Dict[IntentCategory, str] = {}
raw_labels = _patterns.get("suggested_agent_labels", {})
for key, label in raw_labels.items():
    try:
        category = getattr(IntentCategory, key, None)
        if category is not None:
            _SUGGESTED_AGENT_LABELS[category] = str(label)
    except (AttributeError, ValueError):
        continue

# Category to agent tags mapping
_CATEGORY_TO_TAGS: Dict[IntentCategory, List[str]] = {}
raw_tags = _patterns.get("category_to_tags", {})
for key, tags in raw_tags.items():
    try:
        category = getattr(IntentCategory, key, None)
        if category is not None and isinstance(tags, list):
            _CATEGORY_TO_TAGS[category] = [str(t) for t in tags]
    except (AttributeError, ValueError):
        continue

# Agent alternatives for fallback suggestions
_AGENT_ALTERNATIVES: Dict[IntentCategory, List[str]] = {}
raw_alts = _patterns.get("agent_alternatives", {})
for key, alternatives in raw_alts.items():
    try:
        category = getattr(IntentCategory, key, None)
        if category is not None and isinstance(alternatives, list):
            _AGENT_ALTERNATIVES[category] = [str(a) for a in alternatives]
    except (AttributeError, ValueError):
        continue

# Threshold below which we recommend clarification or LLM fallback
_RULE_CONFIDENCE_HIGH = 0.80
_RULE_CONFIDENCE_MEDIUM = 0.50

# Entity extraction patterns
_ENTITY_PATTERNS: List[Tuple[str, str, int]] = [
    (r"(?:订单|order)[号#]?\s*([A-Za-z0-9\-_]+)", "order_id", 1),
    (r"(?:用户|会员)[ID号]?\s*[：:]\s*([A-Za-z0-9\-_]+)", "user_id", 1),
    (r"(?:语言|框架)[：:]\s*(\w+)", "language", 1),
    (r"(?:目录|路径|path)[：:]\s*(/[^\s,]+)", "directory", 1),
    (r"(?:商品|产品|product)[：:]?\s*([^\s,，。]+)", "product_name", 1),
    (r"(?:金额|价格|钱)[：:]?\s*(\d+(?:\.\d+)?)", "amount", 1),
    (r"(?:时间|日期|time)[：:]?\s*([^\s,，。]+)", "time_constraint", 1),
    (r"(?:VIP|vip|钻石|白金|黄金|白银|银卡|金卡|铂金)", "user_tier", 0),
    (r"我是\s*(VIP|钻石会员|白金会员|金卡会员|银卡会员|黄金会员)", "user_tier", 1),
]


def classify(ctx: RoutingContext) -> RoutingResult:
    """Classify user intent and produce routing suggestions.

    Uses rule-based keyword matching as the primary path (fast, 0 LLM cost).
    For ambiguous cases (confidence < 0.5), returns should_clarify=True.
    """
    message = ctx.user_message or ""
    message_lower = message.lower()

    # Stage 1: Rule-based keyword matching
    best_intent = IntentCategory.UNKNOWN
    best_confidence = 0.0
    matched_rule = ""
    matched_signals: Dict[str, Any] = {}

    for pattern, intent, conf, groups in _RULE_TABLE:
        m = _re.search(pattern, message_lower)
        if m:
            if conf > best_confidence:
                best_intent = intent
                best_confidence = conf
                matched_rule = pattern
                matched_signals = {"matched_pattern": pattern, "confidence": conf}
                for gid, key in groups.items():
                    try:
                        matched_signals[f"entity:{key}"] = m.group(gid)
                    except IndexError:
                        pass

    # Stage 2: Entity extraction
    entities: Dict[str, Any] = {}
    for pattern, key, group_idx in _ENTITY_PATTERNS:
        em = _re.search(pattern, message, _re.IGNORECASE)
        if em:
            try:
                entities[key] = em.group(group_idx)
            except IndexError:
                pass

    # Stage 3: Confidence level
    if best_confidence >= _RULE_CONFIDENCE_HIGH:
        level = ConfidenceLevel.HIGH
        should_clarify = False
    elif best_confidence >= _RULE_CONFIDENCE_MEDIUM:
        level = ConfidenceLevel.MEDIUM
        should_clarify = False
    else:
        level = ConfidenceLevel.LOW
        should_clarify = True

    # Stage 4: Build primary route
    primary = _build_primary_route(best_intent, best_confidence, ctx)
    suggested = _build_suggested_routes(best_intent, ctx)

    # Stage 5: Clarification prompt
    clarify_prompt = ""
    if should_clarify:
        clarify_prompt = _build_clarification_prompt(message, ctx)

    return RoutingResult(
        intent=best_intent,
        confidence=best_confidence,
        confidence_level=level,
        primary_route=primary,
        suggested_routes=suggested,
        entities=entities,
        reason=f"Rule matched: {matched_rule}" if matched_rule else "No rule matched, using default",
        signals=matched_signals,
        should_clarify=should_clarify,
        clarification_prompt=clarify_prompt,
        suggested_skill_ids=_map_intent_to_skills(best_intent, ctx),
        suggested_tool_ids=_map_intent_to_tools(best_intent, ctx),
    )


def _build_primary_route(intent: IntentCategory, confidence: float, ctx: RoutingContext) -> SuggestedRoute:
    """Map intent to the best Agent/Skill/Tool route."""
    # If confidence is low, recommend clarification
    if confidence < _RULE_CONFIDENCE_MEDIUM and confidence > 0:
        return SuggestedRoute(kind=RouteKind.CLARIFY, target="", score=confidence, reason="置信度过低，建议追问")

    # Intent → Agent mapping (from YAML config)
    target = _SUGGESTED_AGENT_LABELS.get(intent, "")
    if target:
        return SuggestedRoute(kind=RouteKind.AGENT, target=target, score=confidence,
                              reason=f"意图 {intent.value} → Agent {target}")

    # Intent → Skill mapping
    intent_to_skill = {
        IntentCategory.SUMMARY: "summarize",
        IntentCategory.COMPARE: "multi_doc_query",
        IntentCategory.EVIDENCE_TRACE: "knowledge_retrieve",
        IntentCategory.APPLICABILITY_ANALYSIS: "knowledge_retrieve",
        IntentCategory.FACT_LOOKUP: "knowledge_retrieve",
        IntentCategory.COMPLIANCE_CHECK: "security-auditor",
    }
    target = intent_to_skill.get(intent, "")
    if target:
        return SuggestedRoute(kind=RouteKind.SKILL, target=target, score=confidence,
                              reason=f"意图 {intent.value} → Skill {target}")

    # Default: direct handling
    return SuggestedRoute(kind=RouteKind.DIRECT, target="", score=0.0, reason="无特定路由匹配，由当前 Agent 直接处理")


def _build_suggested_routes(intent: IntentCategory, ctx: RoutingContext) -> List[SuggestedRoute]:
    """Build alternative routes for the given intent."""
    routes: List[SuggestedRoute] = []

    # Add tool suggestions based on intent
    tool_map = {
        IntentCategory.ORDER_QUERY: [("search", 0.5)],
        IntentCategory.REFUND_REQUEST: [("search", 0.5)],
        IntentCategory.CODE_REVIEW: [("file_operations", 0.6)],
        IntentCategory.CODE_GENERATION: [("file_operations", 0.7), ("code_execution", 0.5)],
        IntentCategory.BUG_FIX: [("file_operations", 0.6), ("code_execution", 0.5)],
        IntentCategory.E2E_TEST: [("browser", 0.8)],
        IntentCategory.RESEARCH: [("search", 0.7)],
        IntentCategory.SECURITY_AUDIT: [("file_operations", 0.5)],
    }
    for tool_name, score in tool_map.get(intent, []):
        routes.append(SuggestedRoute(kind=RouteKind.TOOL, target=tool_name, score=score,
                                     reason=f"意图 {intent.value} 常用 Tool: {tool_name}"))

    # Add agent alternatives (from YAML config)
    for alt in _AGENT_ALTERNATIVES.get(intent, []):
        routes.append(SuggestedRoute(kind=RouteKind.AGENT, target=alt, score=0.4,
                                     reason=f"备选 Agent: {alt}"))

    return routes


def _map_intent_to_skills(intent: IntentCategory, ctx: RoutingContext) -> List[str]:
    """Suggest incremental skills — only those NOT already bound to the agent."""
    existing = set(ctx.available_skills)
    extras = {
        IntentCategory.CODE_REVIEW: ["code_review", "code-hygiene"],
        IntentCategory.CODE_GENERATION: ["code_generation"],
        IntentCategory.BUG_FIX: ["root_cause_analysis"],
        IntentCategory.SECURITY_AUDIT: ["security-auditor"],
        IntentCategory.SUMMARY: ["summarize"],
        IntentCategory.TEST_GENERATION: ["test_case_generation"],
        IntentCategory.E2E_TEST: ["site_tester"],
        IntentCategory.RESEARCH: ["information_search", "multi_doc_query"],
    }.get(intent, [])
    return [s for s in extras if s not in existing]


def _map_intent_to_tools(intent: IntentCategory, ctx: RoutingContext) -> List[str]:
    """Suggest incremental tools — only those NOT already bound to the agent."""
    existing = set(ctx.available_tools)
    extras = {
        IntentCategory.CODE_REVIEW: ["file_operations"],
        IntentCategory.CODE_GENERATION: ["file_operations", "code_execution"],
        IntentCategory.BUG_FIX: ["file_operations", "code_execution"],
        IntentCategory.E2E_TEST: ["browser"],
        IntentCategory.RESEARCH: ["search"],
        IntentCategory.ORDER_QUERY: ["search"],
    }.get(intent, [])
    return [t for t in extras if t not in existing]


def _build_clarification_prompt(message: str, ctx: RoutingContext) -> str:
    """Build a clarification question when confidence is low."""
    agent_hint = f"（我是 {ctx.agent_name}，负责 {ctx.agent_description}）" if ctx.agent_name else ""
    return (
        f"抱歉，我不太确定你的具体需求 {agent_hint}。"
        f"能否再详细描述一下你想做什么？比如：\n"
        f"- 查询订单状态\n- 申请退款\n- 咨询产品功能\n- 报告技术问题"
    )


async def classify_with_llm(ctx: RoutingContext) -> RoutingResult:
    """LLM-based classification fallback for ambiguous cases.

    Uses the agent_creation model via a lightweight prompt.
    Should only be called when rule-based confidence < 0.50.
    """
    result = classify(ctx)
    if result.confidence >= _RULE_CONFIDENCE_MEDIUM:
        return result  # Rules were sufficient

    # LLM fallback
    try:
        from core.harness.utils.model_injection import create_selected_adapter, best_model_for_purpose
        from core.adapters.llm.base import LLMConfig

        model_name = best_model_for_purpose("agent_creation")
        adapter = create_selected_adapter(model_name=model_name)
        config = LLMConfig(model="", timeout=30)

        # Build minimal classification prompt
        intents_str = "\n".join([f"  - {i.value}: {i.name}" for i in IntentCategory])
        agent_ctx = ""
        if ctx.agent_name:
            agent_ctx = f"\n当前 Agent: {ctx.agent_name} ({ctx.agent_description or '通用'})"

        prompt = (
            f"分类用户意图。只输出 JSON，不要解释。\n\n"
            f"可用意图:\n{intents_str}\n"
            f"{agent_ctx}\n"
            f"用户输入: {ctx.user_message}\n\n"
            f'输出格式: {{"intent": "<意图>", "confidence": 0.8, "reason": "简短理由", '
            f'"entities": {{}}}}'
        )

        resp = await adapter.generate(
            [{"role": "user", "content": prompt}],
            config=config,
        )
        content = resp.content if hasattr(resp, 'content') else str(resp)

        # Parse LLM response
        import re as _re2
        clean = content.strip()
        if clean.startswith("```"):
            clean = _re2.sub(r'^```\w*\n?', '', clean)
            clean = _re2.sub(r'\n?```$', '', clean)
        match = _re2.search(r'\{[\s\S]*\}', clean)
        if match:
            data = _json.loads(match.group(0))
            llm_intent = data.get("intent", "")
            llm_confidence = float(data.get("confidence", 0.5))
            try:
                new_intent = IntentCategory(llm_intent)
                result.intent = new_intent
                result.confidence = llm_confidence
                result.confidence_level = (
                    ConfidenceLevel.HIGH if llm_confidence >= 0.8 else
                    ConfidenceLevel.MEDIUM if llm_confidence >= 0.5 else
                    ConfidenceLevel.LOW
                )
                result.reason = f"LLM classified: {data.get('reason', '')}"
                result.entities.update(data.get("entities", {}))
                result.primary_route = _build_primary_route(new_intent, llm_confidence, ctx)

                # Update skills/tools suggestions
                result.suggested_skill_ids = _map_intent_to_skills(new_intent, ctx)
                result.suggested_tool_ids = _map_intent_to_tools(new_intent, ctx)
            except ValueError:
                pass  # Keep rule-based result
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    return result
