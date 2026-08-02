"""
Context Assembly Bus — unified knowledge injection pipeline.

Replaces the ~200 lines of interleaved system_parts injection in registry.py
with a single assemble_field_assessment(params, system_parts) call.

Each context layer is a separate _inject_* method, making the pipeline:
  1. Readable (each layer is self-contained)
  2. Reusable (other subsystems can import individual injectors)
  3. Maintainable (add/remove layers without touching registry.py)

callers: registry.py field-assessment skill execution
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Estimate token count for mixed CJK/ASCII text.

    Chinese characters ~1.5 tokens each, ASCII ~0.25 tokens/char.
    Conservative estimate — over-estimates rather than under-estimates.
    """
    if not text:
        return 0
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
    ascii_chars = len(text) - cjk
    return int(cjk * 1.5 + ascii_chars * 0.25) + 1


def _estimate_total_tokens(parts: List[str]) -> int:
    """Sum estimated tokens across all system_parts."""
    return sum(_estimate_tokens(p) for p in parts)


def assemble_field_assessment(
    params: Dict[str, Any],
    system_parts: List[str],
    max_prompt_tokens: int = 0,
) -> tuple:
    """Assemble all context layers for field-assessment diagnosis.

    Args:
        params: Skill execution params (industry, company_name, pain_points, etc.)
        system_parts: Mutable list of system prompt parts (SOP, policy, etc.)
        max_prompt_tokens: Token budget for injected context layers.
            - 0 (default): read from env AIPLAT_FIELD_ASSESSMENT_MAX_PROMPT_TOKENS
              or fall back to max_layers * 2000 tokens.
            - > 0: explicit budget. Layers exceeding this will be skipped and
              diagnostics will record "truncated: token budget exceeded".

    Returns (system_parts, diagnostics) tuple.
    diagnostics: {layer_name: "ok" | "error: ..." | "truncated: ..."} for each layer.
    """
    from core.harness.knowledge.domain_router import DomainRouter

    # PR #4: 从 ControlProfile 读取 context_layers 上限
    try:
        from core.harness.meta.profile_registry import get_active_profile
        max_layers = get_active_profile().context_layers
    except Exception:
        max_layers = 10
        logger.debug("get_active_profile failed, using default max_layers=10", exc_info=True)

    diagnostics = {}
    domain_hint = (params.get("industry") or params.get("company_name") or "").strip()
    if not domain_hint:
        return system_parts, {"_skip": "no domain_hint"}

    did = DomainRouter().classify(domain_hint)
    cross_refs = []
    _layer_count = 0  # PR #4: track executed layers for profile-driven cap

    # Resolve token budget: explicit arg > env var > profile context_layers fallback
    if max_prompt_tokens <= 0:
        max_prompt_tokens = int(os.getenv("AIPLAT_FIELD_ASSESSMENT_MAX_PROMPT_TOKENS", "0") or 0)
    if max_prompt_tokens <= 0:
        max_prompt_tokens = max_layers * 2000

    def _check_budget(layer_name: str) -> bool:
        """Return False if token budget exceeded and layer should be skipped."""
        if max_prompt_tokens <= 0:
            return True
        current = _estimate_total_tokens(system_parts)
        if current > max_prompt_tokens:
            diagnostics[layer_name] = f"truncated: tokens={current} > budget={max_prompt_tokens}"
            return False
        return True

    # Layer 1
    if _layer_count < max_layers:
        _layer_count += 1
        before = len(system_parts)
        try:
            _inject_historical_cases(system_parts, did)
            if not _check_budget("historical_cases"):
                del system_parts[before:]
                return system_parts, diagnostics
            diagnostics["historical_cases"] = "ok"
        except Exception as e:
            diagnostics["historical_cases"] = f"error: {str(e)[:80]}"

    # Layer 2
    before = len(system_parts)
    try:
        cross_refs = _inject_cross_domain_analogs(system_parts, did, params)
        if not _check_budget("cross_domain_analogs"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["cross_domain_analogs"] = "ok"
    except Exception as e:
        diagnostics["cross_domain_analogs"] = f"error: {str(e)[:80]}"

    if _layer_count >= max_layers: return system_parts, diagnostics
    _layer_count += 1

    # Layer 3
    before = len(system_parts)
    if not _check_budget("evidence_rules"):
        return system_parts, diagnostics
    try:
        _inject_evidence_rules(system_parts, cross_refs, did, params)
        if not _check_budget("evidence_rules"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["evidence_rules"] = "ok"
    except Exception as e:
        diagnostics["evidence_rules"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 4
    before = len(system_parts)
    if not _check_budget("solution_archetypes"):
        return system_parts, diagnostics
    try:
        _inject_solution_archetypes(system_parts)
        if not _check_budget("solution_archetypes"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["solution_archetypes"] = "ok"
    except Exception as e:
        diagnostics["solution_archetypes"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 5
    before = len(system_parts)
    if not _check_budget("graph_traversal"):
        return system_parts, diagnostics
    try:
        _inject_graph_traversal(system_parts, did, params)
        if not _check_budget("graph_traversal"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["graph_traversal"] = "ok"
    except Exception as e:
        diagnostics["graph_traversal"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 6
    before = len(system_parts)
    if not _check_budget("delivery_history"):
        return system_parts, diagnostics
    try:
        _inject_delivery_history(system_parts, params)
        if not _check_budget("delivery_history"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["delivery_history"] = "ok"
    except Exception as e:
        diagnostics["delivery_history"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 7
    before = len(system_parts)
    if not _check_budget("self_optimization"):
        return system_parts, diagnostics
    try:
        _inject_self_optimization(system_parts)
        if not _check_budget("self_optimization"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["self_optimization"] = "ok"
    except Exception as e:
        diagnostics["self_optimization"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 8
    before = len(system_parts)
    if not _check_budget("multi_role_risk"):
        return system_parts, diagnostics
    try:
        _inject_multi_role_risk(system_parts)
        if not _check_budget("multi_role_risk"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["multi_role_risk"] = "ok"
    except Exception as e:
        diagnostics["multi_role_risk"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 9
    before = len(system_parts)
    if not _check_budget("term_dictionary"):
        return system_parts, diagnostics
    try:
        _inject_term_dictionary(system_parts)
        if not _check_budget("term_dictionary"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["term_dictionary"] = "ok"
    except Exception as e:
        diagnostics["term_dictionary"] = f"error: {str(e)[:80]}"

    _layer_count += 1
    if _layer_count >= max_layers:
        return system_parts, diagnostics

    # Layer 10
    before = len(system_parts)
    if not _check_budget("digital_employees"):
        return system_parts, diagnostics
    try:
        _inject_digital_employees(system_parts)
        if not _check_budget("digital_employees"):
            del system_parts[before:]
            return system_parts, diagnostics
        diagnostics["digital_employees"] = "ok"
    except Exception as e:
        diagnostics["digital_employees"] = f"error: {str(e)[:80]}"

    return system_parts, diagnostics


# ═══════════════════════════════════════════════════════════════
# Individual context layers
# ═══════════════════════════════════════════════════════════════

def _inject_historical_cases(parts: List[str], did: str):
    """Layer 1: Historical diagnosis cases in the same domain."""
    try:
        from core.harness.knowledge.wiki_engine import search_pages
        hist = search_pages("诊断报告", collection_id=did, limit=3)
        if hist:
            refs = "\n".join(
                f"- [{h.get('title', '')}] — {h.get('body', '')[:200]}"
                for h in hist
            )
            parts.append(
                f"## 域知识上下文：历史案例参考 ({did} 域)\n"
                f"以下为同域历史诊断报告摘要，可用于§4.65预期干预效果推理：\n{refs}"
            )
    except Exception:
        logger.debug("_inject_historical_cases: search_pages failed for did=%s", did, exc_info=True)


def _inject_cross_domain_analogs(parts: List[str], did: str,
                                  params: Dict) -> List[str]:
    """Layer 2: Cross-domain analog discovery for pain points."""
    cross_refs = []
    pain_points = params.get("pain_points") or ""
    if not pain_points:
        return cross_refs

    try:
        from core.harness.knowledge.ontology_query_mapper import discover_cross_domain_analogs
        analogs = discover_cross_domain_analogs(pain_points[:200], threshold=0.65)
        if analogs:
            lines = []
            for a_did, matches in analogs.items():
                if a_did == did:
                    continue
                for m in matches[:2]:
                    lines.append(f"- {a_did}域 → {m['class_label']} (相似度 {m['score']})")
                    cross_refs.append(f"{a_did}域/{m['class_label']}")
            if lines:
                parts.append(
                    "## 跨域类比发现\n"
                    f"当前概念「{pain_points[:60]}」在以下域中存在语义相似的类，可用于§1来源列引用：\n"
                    + "\n".join(lines)
                )
    except Exception:
        logger.debug("_inject_cross_domain_analogs failed", exc_info=True)
    return cross_refs


def _inject_evidence_rules(parts: List[str], cross_refs: List[str],
                            did: str, params: Dict):
    """Layer 3: Evidence annotation rules (P0)."""
    ontology_refs = ", ".join(cross_refs[:3]) if cross_refs else "无"
    hist_refs = "有" if did else "无"
    parts.append(
        "## 诊断溯源规则（必读）\n"
        "报告 §1 表的「证据等级」列必须从以下三级中选择其一：\n"
        f"- **本体实例**：该结论可映射到某个域本体类的已知属性/案例。当前已知：跨域类比={ontology_refs}。\n"
        f"- **历史案例**：该结论在历史诊断报告中有相似模式。当前历史案例：{hist_refs}。\n"
        "- **LLM推测**：该结论无本体实例也无历史案例支撑，纯基于模型训练知识的推断。\n"
        "规则：禁止全列标注为LLM推测。至少50%的行应标注为本体实例或历史案例。"
    )


def _inject_solution_archetypes(parts: List[str]):
    """Layer 4: Solution archetype table (P2)."""
    try:
        from core.harness.knowledge.ontology_bus import render_solution_table
        parts.append(render_solution_table())
    except Exception:
        logger.debug("_inject_solution_archetypes failed", exc_info=True)


def _inject_graph_traversal(parts: List[str], did: str, params: Dict):
    """Layer 5: Graph traversal for pain-point entities."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.ontology_engine.graph_traversal import traverse

        g = GraphIndex.load(did)
        stats = g.stats()
        if stats.get("node_count", 0) == 0:
            return

        pain_keywords = (params.get("pain_points") or "").split()
        found_paths = []
        for kw in pain_keywords[:5]:
            node = g.find_by_name(kw)
            if not node:
                continue
            tr = traverse(node.entity_name, g, max_hops=2, direction="both")
            for path in tr.paths[:3]:
                desc = " → ".join(
                    f"{s.entity_name}({s.relation_label or s.relation_name or '关联'})"
                    for s in path.steps
                )
                found_paths.append(desc)

        if found_paths:
            path_fmt = "\n".join(f"- {p}" for p in found_paths[:8])
            parts.append(
                f"## 知识图谱上下文 ({did} 域)\n"
                f"当前域知识图谱有 {stats['node_count']} 个实体、{stats['edge_count']} 条关系。\n"
                f"与客户痛点相关的实体遍历路径：\n{path_fmt}\n"
                f"请在 §1 来源列引用这些图谱关系，标注为「本体实例」。"
            )
    except Exception:
        logger.debug("_inject_graph_traversal failed for did=%s", did, exc_info=True)


def _inject_delivery_history(parts: List[str], params: Dict):
    """Layer 6: Delivery tracking history for §4.6 ROI (A3)."""
    domain_hint = (params.get("industry") or params.get("company_name") or "").strip()
    if not domain_hint:
        return

    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.domain_router import DomainRouter
        router = DomainRouter()
        domains = router.list_domains()
        delivered = total_sessions = industry_sessions = 0
        industry_lower = (params.get("industry") or "").strip().lower()

        for domain_id in domains:
            try:
                g = GraphIndex.load(domain_id)
            except Exception:
                continue
            for _, node in list(g._nodes.items())[:100]:
                nb = g.get_neighbor_edges(getattr(node, "entity_id", ""), direction="outgoing")
                if any(e.relation_name == "has_action" for _, e in nb):
                    delivered += 1
                total_sessions += 1
                if industry_lower and industry_lower in node.entity_name.lower():
                    industry_sessions += 1

        if total_sessions > 0:
            rate = round(delivered / total_sessions * 100) if total_sessions else 0
            parts.append("\n".join([
                "## FDE 交付跟踪统计",
                f"- 历史诊断总数：{total_sessions} 次",
                f"- 已创建交付行动：{delivered} 次（行动创建率 {rate}%）",
                f"- 同行业「{industry_lower}」诊断：{industry_sessions} 次",
                "",
                "在 §4.6 ROI 估算中参考以上数据。若交付率偏低（<40%），",
                "在 §7 部署路线图中增加阶段性验证节点。",
            ]))
    except Exception:
        logger.debug("_inject_delivery_history failed", exc_info=True)


def _inject_self_optimization(parts: List[str]):
    """Layer 7: History-driven self-optimization hints (E)."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.domain_router import DomainRouter
        router = DomainRouter()
        domains = router.list_domains()
        sessions = []
        for domain_id in domains:
            try:
                g = GraphIndex.load(domain_id)
            except Exception:
                continue
            for _, node in list(g._nodes.items())[:200]:
                nb = g.get_neighbor_edges(getattr(node, "entity_id", ""), direction="outgoing")
                has_action = any(e.relation_name == "has_action" for _, e in nb)
                sessions.append({"name": node.entity_name, "has_actions": has_action})

        if sessions:
            action_count = sum(1 for s in sessions if s["has_actions"])
            rate = round(action_count / len(sessions) * 100) if sessions else 0
            if rate >= 60:
                hint = f"历史交付率={rate}%（{action_count}/{len(sessions)}）。对相似行业的 AI 机会建议可标记较高置信度（≥80%）。§6 优先推荐曾在历史案例中成功落地的方案原型。"
            elif rate >= 30:
                hint = f"历史交付率={rate}%（{action_count}/{len(sessions)}），中等。§1 置信度保守标注（≤70%），§7 增加更多验证节点。"
            else:
                hint = f"历史交付率偏低={rate}%（{action_count}/{len(sessions)}）。§1 置信度一律标注为「中」或「低」。§6 仅推荐低风险方案。§7 必须包含 3 个以上阶段性验证节点。"
            parts.append(f"## 诊断自优化 ({len(sessions)}条历史)\n{hint}")

            # P2: Knowledge freshness check
            try:
                from core.harness.ontology_engine.graph_index import GraphIndex
                from datetime import timezone as _tz, timedelta as _td
                import time as _time_fresh
                kg = GraphIndex.load("knowledge-atom")
                stale = 0
                cutoff = int(_time_fresh.time()) - 90 * 86400
                for _, n in kg._nodes.items():
                    if getattr(n, "class_name", "") != "SECI知识原子":
                        continue
                    try:
                        ts = int(getattr(n, "source_doc_id", "0"))
                        if 0 < ts < cutoff:
                            stale += 1
                    except ValueError:
                        continue
                if stale >= 5:
                    parts.append(f"## 知识新鲜度提醒\n{stale} 个知识原子超过 90 天未更新，可能影响诊断准确性。建议重新诊断对应客户或检查知识原子。")
            except Exception:
                logger.debug("_inject_self_optimization: knowledge freshness check failed", exc_info=True)
    except Exception:
        logger.debug("_inject_self_optimization failed", exc_info=True)


def _inject_multi_role_risk(parts: List[str]):
    """Layer 8: Multi-role adoption risk assessment (F)."""
    parts.append("\n".join([
        "## 多角色采纳风险评估（§7 必读）",
        "",
        "请在 §7 部署路线图中，从以下三个角色的视角分别标注采纳风险：",
        "",
        "| 角色 | 关注点 | 风险信号（出现即降低优先级） |",
        "| :--- | :--- | :--- |",
        "| **CIO/决策者** | 预算、组织就绪、战略对齐 | 方案需新招团队/预算超标/与现有IT架构冲突 |",
        "| **开发/技术** | 可行性、集成复杂度、技能缺口 | 需要客户方不具备的技术栈/数据格式不兼容/缺少API |",
        "| **终端用户** | 流程冲击、学习成本、实际使用率 | 需要大量手动标注/改变既有工作习惯/界面过于复杂 |",
        "",
        "规则：若任一角色出现 2 个以上风险信号，该方案在 §5 排序中降 1 位，并在 §7 标注「需引入该角色参与评估」。",
    ]))


def _inject_term_dictionary(parts: List[str]):
    """Layer 9: Term dictionary from GraphIndex (R)."""
    try:
        from core.harness.ontology_engine.graph_index import GraphIndex
        from core.harness.knowledge.domain_router import DomainRouter

        terms = []
        for domain_id in DomainRouter().list_domains():
            try:
                g = GraphIndex.load(domain_id)
                for _, n in getattr(g, '_nodes', {}).items():
                    cn = getattr(n, "class_name", "")
                    if cn in ("Term", "术语"):
                        terms.append({"name": n.entity_name[:80], "domain": domain_id,
                                      "source": getattr(n, "source_doc_id", "")[:30]})
            except Exception:
                continue
        if terms:
            lines = [
                "## 业务语义字典", "",
                f"以下为已注册的 {len(terms)} 个业务术语。§1 的「来源」列可引用术语名称作为语义锚点。", "",
                "| 术语名 | 来源会话 |", "| :--- | :--- |",
            ]
            for t in terms[:15]:
                lines.append(f"| {t['name']} | {t['source']} |")
            parts.append("\n".join(lines))
        else:
            parts.append(
                "## 业务语义字典\n"
                "术语字典为空。随诊断次数增加，知识缺口会自动播种术语定义。\n"
                "§1 的「来源」列可引用术语名称作为语义锚点。"
            )
    except Exception:
        parts.append("## 业务语义字典\n术语字典不可用。§1 的「来源」列可引用域本体类名作为语义锚点。")


def _inject_digital_employees(parts: List[str]):
    """Layer 10: Digital employee role mapping (Y)."""
    try:
        from core.harness.knowledge.ontology_bus import render_digital_employee_table
        parts.append(render_digital_employee_table())
    except Exception:
        logger.debug("_inject_digital_employees failed", exc_info=True)


# ═══════════════════════════════════════════════════════════════
# Multi-subsystem context assemblers
# ═══════════════════════════════════════════════════════════════

def assemble_agent_context(params: dict, system_parts: list) -> list:
    """Lightweight context for Agent conversations (3 layers only).

    Agents need domain awareness but not the full diagnosis pipeline.
    Injects: term dictionary, digital employees, and solution archetypes.
    """
    try:
        _inject_term_dictionary(system_parts)
    except Exception:
        logger.debug("assemble_agent_context: _inject_term_dictionary failed", exc_info=True)
    try:
        _inject_digital_employees(system_parts)
    except Exception:
        logger.debug("assemble_agent_context: _inject_digital_employees failed", exc_info=True)
    try:
        _inject_solution_archetypes(system_parts)
    except Exception:
        logger.debug("assemble_agent_context: _inject_solution_archetypes failed", exc_info=True)
    return system_parts


def assemble_skill_context(params: dict, system_parts: list) -> list:
    """Lightweight context for Skill execution (2 layers only).

    Skills need terminology awareness and evidence rules.
    """
    try:
        _inject_term_dictionary(system_parts)
    except Exception:
        logger.debug("assemble_skill_context: _inject_term_dictionary failed", exc_info=True)
    try:
        _inject_solution_archetypes(system_parts)
    except Exception:
        logger.debug("assemble_skill_context: _inject_solution_archetypes failed", exc_info=True)
    return system_parts


def assemble_pipeline_context(params: dict, system_parts: list) -> list:
    """Lightweight context for Pipeline execution (3 layers).

    Pipelines need delivery history, self-optimization, and term awareness.
    """
    try:
        _inject_delivery_history(system_parts, params)
    except Exception:
        logger.debug("assemble_pipeline_context: _inject_delivery_history failed", exc_info=True)
    try:
        _inject_self_optimization(system_parts)
    except Exception:
        logger.debug("assemble_pipeline_context: _inject_self_optimization failed", exc_info=True)
    try:
        _inject_term_dictionary(system_parts)
    except Exception:
        logger.debug("assemble_pipeline_context: _inject_term_dictionary failed", exc_info=True)
    return system_parts


# ═══════════════════════════════════════════════════════════════
# SESSION_START Hook — inject domain context into all Agents
# ═══════════════════════════════════════════════════════════════

_hook_registered = False


def register_context_hook() -> bool:
    global _hook_registered
    if _hook_registered:
        return False

    async def _context_start_hook(ctx):
        try:
            parts = []
            _inject_term_dictionary(parts)
            _inject_digital_employees(parts)
            text = "\n".join(parts)
            if text.strip():
                logger.debug("ContextBus: domain context injected at session start (%d chars)", len(text))
            return [{"domain_context": text[:2000]}]
        except Exception as e:
            logger.debug("ContextBus SESSION_START skip: %s", str(e))
            return []

    try:
        from core.harness.infrastructure.hooks.hook_manager import HookManager, HookPhase

        class _ContextStartHook:
            phase = HookPhase.SESSION_START
            priority = 30
            name = "context_bus_domain_injection"

            async def __call__(self, ctx):
                return await _context_start_hook(ctx)

        HookManager().register(_ContextStartHook())
        _hook_registered = True
        logger.info("ContextBus hook registered on SESSION_START (priority=30)")
        return True
    except Exception as e:
        logger.debug("ContextBus hook registration failed: %s", str(e))
        return False
