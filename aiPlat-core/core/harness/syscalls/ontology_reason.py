u"""
Ontology Agent — 5 步推理编排器 (v2.7).

Orchestrates: Task Understanding → Path Planning → Graph Query → Rule Scoring → Output.
Uses plan_execute mode for pre-defined paths, react_fallback for novel queries.

The first dedicated reasoning agent — complements MaterialsChatAgent (RAG) with
graph-based multi-hop reasoning.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ontology_agent")


@dataclass
class ReasoningTrace:
    step: int
    action: str
    output: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class OntologyAgentResult:
    task: str
    domain_id: str = ""
    selected_path: str = ""
    path_result: Optional[Any] = None
    scoring_results: List[Any] = field(default_factory=list)
    nl_output: str = ""
    reasoning_trace: List[Dict[str, Any]] = field(default_factory=list)
    mode: str = "plan_execute"  # plan_execute | react_fallback


async def sys_ontology_reason(
    task: str,
    *,
    domain_id: str = "",
    max_paths: int = 3,
    timeout_seconds: float = 60.0,
) -> Dict[str, Any]:
    u"""System call: run the 5-step ontology reasoning pipeline.

    Returns structured result with reasoning_trace for auditability.
    """
    result = OntologyAgentResult(task=task)
    start_time = _time.time()

    # ── Step 1: Task Understanding ──
    trace = ReasoningTrace(step=1, action="task_understanding")
    t0 = _time.time()
    try:
        from core.harness.knowledge.domain_router import DomainRouter

        if not domain_id:
            router = DomainRouter()
            classified = router.classify(task)
            domain_id = classified.get("domain_id", "") if classified else ""

        task_context = {"task": task, "intent": "", "entities": [], "target_class": "",
                         "filters": {}, "time_range": "this_month", "confidence": 0.0}

        # Extract entities from task (simple keyword extraction)
        import re
        words = re.findall(r'[\u4e00-\u9fa5a-zA-Z]+', task)
        task_context["entities"] = words[:5]

        # Try structured parsing if mapper is available
        try:
            from core.harness.knowledge.ontology_query_mapper import parse_to_logic_form
            structured = parse_to_logic_form(task)
            if structured:
                task_context["intent"] = structured.get("intent", "")
                task_context["target_class"] = structured.get("target_class", "")
                task_context["filters"] = structured.get("filters", {})
                task_context["time_range"] = structured.get("time_range", "this_month")
                task_context["confidence"] = structured.get("confidence", 0.5)
        except Exception:
            pass

        trace.output = {"domain_id": domain_id, "entities": task_context["entities"],
                         "intent": task_context["intent"], "confidence": task_context["confidence"]}
        trace.duration_ms = (_time.time() - t0) * 1000

    except Exception as e:
        trace.success = False
        trace.error = str(e)

    result.reasoning_trace.append(vars(trace))
    if not trace.success or not domain_id:
        result.mode = "react_fallback"
        result.nl_output = f"Unable to understand task: {trace.error}. Please rephrase."
        return _to_dict(result)

    # ── Step 1.5: Low-confidence clarification ──
    if task_context.get("confidence", 1.0) < 0.7:
        try:
            from core.harness.utils.model_injection import best_model_for_purpose
            model = best_model_for_purpose("code_gen")
            clarification_prompt = (
                f"用户输入: {task}\n"
                f"当前理解: domain={domain_id}, intent={task_context.get('intent','')}, "
                f"entities={task_context['entities']}\n"
                f"如果理解有偏差，请用一句话澄清用户意图。否则回复 OK。"
            )
            response = await model.agenerate(clarification_prompt)
            clarification = getattr(response, "content", "OK")
            if clarification.strip() != "OK" and len(clarification.strip()) > 2:
                task_context["clarification"] = clarification.strip()
                logger.info("Step 1.5 clarification: %s", clarification)
        except Exception:
            pass

    # ── Step 2: Path Planning ──
    trace = ReasoningTrace(step=2, action="path_planning")
    t0 = _time.time()
    candidates = []
    try:
        from core.harness.knowledge.path_planner import find_candidate_paths, execute_path
        candidates = find_candidate_paths(task_context, domain_id)
        trace.output = {"candidate_count": len(candidates),
                         "top_path": candidates[0].path.name if candidates else None,
                         "match_reason": candidates[0].match_reason if candidates else "none"}
    except Exception as e:
        trace.success = False
        trace.error = str(e)

    trace.duration_ms = (_time.time() - t0) * 1000
    result.reasoning_trace.append(vars(trace))

    if not candidates:
        result.mode = "react_fallback"
        result.nl_output = f"No reasoning path found for task in domain '{domain_id}'. Try a different question."
        return _to_dict(result)

    best = candidates[0]
    result.selected_path = best.path.name

    # ── Step 3: Graph Query Execution ──
    trace = ReasoningTrace(step=3, action="graph_query")
    t0 = _time.time()
    path_result = None
    tried_paths = 0
    for candidate in candidates:
        tried_paths += 1
        try:
            path_result = execute_path(
                candidate.path,
                task_context.get("entities", []),
                domain_id,
            )
            if path_result.completed:
                break
        except Exception:
            continue
        if tried_paths >= 3:
            break

    if path_result:
        trace.output = {"completed": path_result.completed,
                         "terminal_count": len(path_result.terminal_entities),
                         "hops": len(path_result.step_results),
                         "tried_paths": tried_paths}
    else:
        trace.success = False
        trace.error = "All candidate paths failed"

    trace.duration_ms = (_time.time() - t0) * 1000
    result.reasoning_trace.append(vars(trace))
    result.path_result = path_result

    # ── Step 4: Rule Application (Scoring) ──
    trace = ReasoningTrace(step=4, action="scoring")
    t0 = _time.time()
    scoring_results = []
    try:
        if best.path.scoring_model and path_result and path_result.terminal_entities:
            from core.harness.knowledge.scoring_engine import evaluate_batch, load_models
            import os, yaml
            base = os.path.expanduser(os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))
            yp = os.path.join(base, f"{domain_id}.yaml")
            if os.path.exists(yp):
                with open(yp) as f:
                    raw = yaml.safe_load(f) or {}
                models = {m.name: m for m in load_models(raw)}
                model = models.get(best.path.scoring_model)
                if model:
                    for entity in path_result.terminal_entities:
                        from core.harness.knowledge.scoring_engine import evaluate
                        r = evaluate(entity, model, domain_id)
                        if r.total_score > 0:
                            scoring_results.append(r)
        trace.output = {"scored_entities": len(scoring_results),
                         "model": best.path.scoring_model}
    except Exception as e:
        trace.success = False
        trace.error = str(e)

    trace.duration_ms = (_time.time() - t0) * 1000
    result.reasoning_trace.append(vars(trace))
    result.scoring_results = scoring_results

    # ── Step 5: NL Output ──
    trace = ReasoningTrace(step=5, action="nl_output")
    t0 = _time.time()
    try:
        if scoring_results:
            highs = [r for r in scoring_results if r.level == "high"]
            meds = [r for r in scoring_results if r.level == "medium"]
            parts = []
            if highs:
                parts.append(f"发现 {len(highs)} 个高风险实体：")
                for r in highs[:5]:
                    parts.append(f"  - {r.entity_name}: 风险评分 {r.total_score} ({r.level})")
            if meds:
                parts.append(f"发现 {len(meds)} 个中等风险实体")
            if not parts:
                parts.append(f"评估完成，无高风险实体。共评估 {len(scoring_results)} 个。")
            result.nl_output = "\n".join(parts)
        elif path_result and path_result.terminal_entities:
            result.nl_output = f"路径 '{best.path.label}' 执行完成，发现 {len(path_result.terminal_entities)} 个相关实体。"
        else:
            result.nl_output = "推理路径执行未产生结果。"
    except Exception as e:
        trace.success = False
        trace.error = str(e)

    trace.duration_ms = (_time.time() - t0) * 1000
    result.reasoning_trace.append(vars(trace))

    total_ms = (_time.time() - start_time) * 1000
    logger.info("OntologyAgent completed: %s, mode=%s, %.0fms", task[:50], result.mode, total_ms)
    return _to_dict(result)


def _to_dict(result: OntologyAgentResult) -> Dict[str, Any]:
    scoring_serialized = []
    for r in result.scoring_results:
        if hasattr(r, '__dict__'):
            d = vars(r).copy()
            d.pop('details', None)  # keep lightweight
            scoring_serialized.append(d)
        else:
            scoring_serialized.append(r)

    return {
        "task": result.task,
        "domain_id": result.domain_id,
        "selected_path": result.selected_path,
        "path_result": result.path_result.__dict__ if hasattr(result.path_result, '__dict__') else result.path_result,
        "scoring_results": scoring_serialized,
        "nl_output": result.nl_output,
        "reasoning_trace": result.reasoning_trace,
        "mode": result.mode,
    }
