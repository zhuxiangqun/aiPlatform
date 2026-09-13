"""Deterministic skill injection for factory ``app_page.json`` (kernel-generic).

Closed loop (no YAML / no domain word lists):

1. Agent engineering emits ``skill_routing`` + required ``ui_bindings``
   (platform component id → skill key) on ``agent_manifest.json``.
2. Frontend copies ``stage.skill`` from ``ui_bindings`` / ``skill_routing``.
3. This module only repairs empty / invented / duplicate skills from that
   same agent_app artifact (bindings first, then token-overlap fallback).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

_log = logging.getLogger(__name__)


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", str(s or "").lower()))


def extract_ui_bindings(source: Any) -> Dict[str, str]:
    """Manifest map: platform component id → skill name.

    Accepted keys on agent_manifest: ``ui_bindings``, ``component_skills``.
    """
    if isinstance(source, dict):
        for key in ("ui_bindings", "component_skills"):
            val = source.get(key)
            if isinstance(val, dict) and val:
                return {str(k): str(v) for k, v in val.items() if k and v}
        nested = source.get("agent_manifest") or source.get("manifest")
        if isinstance(nested, dict):
            got = extract_ui_bindings(nested)
            if got:
                return got
        raw = source.get("raw_output") or source.get("content") or ""
        if raw:
            return extract_ui_bindings(raw)
        return {}

    text = str(source or "")
    for block in re.split(r"^#{2,4}\s*FILE:\s*", text, flags=re.MULTILINE)[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) < 2 or "agent_manifest.json" not in lines[0]:
            continue
        body = lines[1].strip()
        body = re.sub(r"^```(?:json)?\s*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body)
        try:
            man = json.loads(body)
        except json.JSONDecodeError:
            m = re.search(r'"ui_bindings"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})', body)
            if not m:
                m = re.search(
                    r'"component_skills"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})', body
                )
            if not m:
                continue
            try:
                man = {"ui_bindings": json.loads(m.group(1))}
            except json.JSONDecodeError:
                continue
        got = extract_ui_bindings(man)
        if got:
            return got
    return {}


def extract_skill_routing(source: Any) -> Dict[str, str]:
    """Extract ``skill_routing`` map from agent_app raw text / dict / manifest."""
    if not source:
        return {}
    if isinstance(source, dict):
        for key in ("skill_routing",):
            val = source.get(key)
            if isinstance(val, dict) and val:
                return {str(k): str(v) for k, v in val.items() if k}
        nested = source.get("agent_manifest") or source.get("manifest")
        if isinstance(nested, dict):
            got = extract_skill_routing(nested)
            if got:
                return got
        raw = source.get("raw_output") or source.get("content") or ""
        if raw:
            return extract_skill_routing(raw)
        agents = source.get("agents")
        if isinstance(agents, list):
            routing: Dict[str, str] = {}
            for ag in agents:
                if not isinstance(ag, dict):
                    continue
                name = str(ag.get("name") or ag.get("agent_id") or "").strip()
                for sk in ag.get("skills") or ag.get("required_skills") or []:
                    sk_s = str(sk).strip()
                    if sk_s and sk_s not in routing:
                        routing[sk_s] = name or "agent"
            if routing:
                return routing
        return {}

    text = str(source)
    for block in re.split(r"^#{2,4}\s*FILE:\s*", text, flags=re.MULTILINE)[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) < 2:
            continue
        if "agent_manifest.json" not in lines[0]:
            continue
        body = lines[1].strip()
        body = re.sub(r"^```(?:json)?\s*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body)
        try:
            man = json.loads(body)
        except json.JSONDecodeError:
            m = re.search(r'"skill_routing"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})', body)
            if not m:
                continue
            try:
                man = {"skill_routing": json.loads(m.group(1))}
            except json.JSONDecodeError:
                continue
        got = extract_skill_routing(man)
        if got:
            return got

    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start : end + 1])
            got = extract_skill_routing(obj)
            if got:
                return got
        except json.JSONDecodeError:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return {}


def _canonicalize_skill(name: str, skills: List[str]) -> str:
    """Map an invented skill name onto the closest routing key via token overlap."""
    cur = str(name or "").strip()
    if not cur:
        return ""
    if cur in skills:
        return cur
    for s in skills:
        if s.lower() == cur.lower():
            return s
    tokens = _tokens(cur)
    if not tokens:
        return ""
    best, best_score = "", 0
    for s in skills:
        st = _tokens(s)
        score = len(tokens & st)
        if score > best_score or (score == best_score and score > 0 and len(s) > len(best)):
            best_score = score
            best = s
    need = 2 if len(tokens) >= 2 else 1
    return best if best_score >= need else ""


def _score_skill_for_component(component: str, skill: str) -> int:
    """Generic score: component id ↔ skill name token overlap only."""
    return len(_tokens(component) & _tokens(skill))


def _pick_skill(
    component: str,
    skills: List[str],
    used: set,
    *,
    ui_bindings: Optional[Dict[str, str]] = None,
) -> str:
    """Prefer manifest ui_bindings; else token overlap; else first unused routing key."""
    comp = str(component or "").strip()
    bindings = ui_bindings or {}
    bound = bindings.get(comp)
    if bound and bound in skills and bound not in used:
        return bound

    best, best_score = "", -1
    for s in skills:
        if s in used:
            continue
        sc = _score_skill_for_component(comp, s)
        if sc > best_score:
            best_score = sc
            best = s
    if best_score > 0 and best:
        return best
    for s in skills:
        if s not in used:
            return s
    return skills[0] if skills else ""


def parse_app_page_payload(raw: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (app_page_dict, format) where format is json|file_block|none."""
    text = str(raw or "").strip()
    if not text:
        return None, "none"

    for block in re.split(r"^#{2,4}\s*FILE:\s*", text, flags=re.MULTILINE)[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) < 2:
            continue
        if "app_page.json" not in lines[0] and "frontend" not in lines[0].lower():
            continue
        body = lines[1].strip()
        body = re.sub(r"^```(?:json)?\s*\n?", "", body)
        body = re.sub(r"\n?```\s*$", "", body)
        try:
            obj = json.loads(body)
            if isinstance(obj, dict) and isinstance(obj.get("stages"), list):
                return obj, "file_block"
        except json.JSONDecodeError:
            continue

    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict) and isinstance(obj.get("stages"), list):
                return obj, "json"
        except json.JSONDecodeError:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    return None, "none"


def inject_app_page_skills(
    app_page: Dict[str, Any],
    skill_routing: Dict[str, str],
    *,
    overwrite_nonempty: bool = False,
    ui_bindings: Optional[Dict[str, str]] = None,
    agent_app_source: Any = None,
) -> Dict[str, Any]:
    """Fill / correct ``stage.skill`` from agent_app bindings + routing.

    Priority for each stage:
    0. Manifest ``ui_bindings[component]`` when value ∈ skill_routing (**SoT — always wins**)
    1. Keep skill if it is already a routing key (unless overwrite_nonempty)
    2. Canonicalize invented names onto routing keys (token overlap)
    3. Component↔skill token overlap (last-resort, no YAML)
    4. First unused routing key
    5. Dedupe: if two stages share a skill and unused keys remain, reassign later stage
    """
    if not isinstance(app_page, dict):
        return app_page
    routing = {str(k): str(v) for k, v in (skill_routing or {}).items() if k}
    if not routing:
        return app_page

    skills = list(routing.keys())
    stages = app_page.get("stages")
    if not isinstance(stages, list):
        return app_page

    bindings = dict(ui_bindings or {})
    if not bindings and agent_app_source is not None:
        bindings = extract_ui_bindings(agent_app_source)
    # Drop invalid binding targets (e.g. agent id instead of skill key)
    bindings = {
        str(k): str(v)
        for k, v in bindings.items()
        if k and v and str(v) in routing
    }
    if not bindings and not extract_ui_bindings(agent_app_source or {}):
        _log.warning(
            "app_page skill inject: agent_manifest missing ui_bindings; "
            "falling back to token overlap on skill_routing keys only"
        )
    elif extract_ui_bindings(agent_app_source or {}) and not bindings:
        _log.warning(
            "app_page skill inject: ui_bindings values not in skill_routing "
            "(likely agent ids); ignoring invalid bindings"
        )

    filled = 0
    replaced = 0

    # Pass 0: ui_bindings SoT — overwrite even when current skill is a valid routing key
    for st in stages:
        if not isinstance(st, dict):
            continue
        comp = str(st.get("component") or "").strip()
        expected = bindings.get(comp)
        if not expected:
            continue
        cur = str(st.get("skill") or "").strip()
        if cur != expected:
            st["skill"] = expected
            replaced += 1

    # Pass 1: canonicalize / clear invalid (stages without binding)
    for st in stages:
        if not isinstance(st, dict):
            continue
        comp = str(st.get("component") or "").strip()
        if comp in bindings:
            continue  # already forced in pass 0
        cur = str(st.get("skill") or "").strip()
        if not cur:
            continue
        if cur in routing and not overwrite_nonempty:
            continue
        canon = _canonicalize_skill(cur, skills)
        if canon and canon in routing:
            if canon != cur:
                st["skill"] = canon
                replaced += 1
        else:
            st["skill"] = ""
            replaced += 1

    # Pass 2: fill empties (bindings first via _pick_skill)
    used = {
        str(s.get("skill") or "").strip()
        for s in stages
        if isinstance(s, dict) and str(s.get("skill") or "").strip() in routing
    }
    for st in stages:
        if not isinstance(st, dict):
            continue
        cur = str(st.get("skill") or "").strip()
        if cur and cur in routing:
            continue
        picked = _pick_skill(
            str(st.get("component") or ""),
            skills,
            used,
            ui_bindings=bindings,
        )
        if picked:
            st["skill"] = picked
            used.add(picked)
            filled += 1

    # Pass 3: unique skills across stages when unused keys remain —
    # but never break a stage whose component has an explicit ui_binding
    seen: Dict[str, int] = {}
    for idx, st in enumerate(stages):
        if not isinstance(st, dict):
            continue
        cur = str(st.get("skill") or "").strip()
        if not cur:
            continue
        if cur not in seen:
            seen[cur] = idx
            continue
        comp = str(st.get("component") or "").strip()
        if comp in bindings:
            continue
        used_others = {
            str(s.get("skill") or "").strip()
            for j, s in enumerate(stages)
            if isinstance(s, dict) and j != idx and str(s.get("skill") or "").strip()
        }
        alt = _pick_skill(
            str(st.get("component") or ""),
            skills,
            used_others,
            ui_bindings=bindings,
        )
        if alt and alt != cur:
            st["skill"] = alt
            replaced += 1

    app_page["skill_routing"] = dict(routing)
    if bindings:
        app_page["ui_bindings"] = dict(bindings)
    if filled or replaced:
        _log.info(
            "app_page skill inject: filled=%d replaced=%d skills=%s",
            filled,
            replaced,
            [str(s.get("skill")) for s in stages if isinstance(s, dict)],
        )
    app_page["_skill_inject_stats"] = {"filled": filled, "replaced": replaced}
    return app_page


def repair_frontend_pages_raw(
    frontend_raw: str,
    agent_app_source: Any,
) -> Tuple[str, Dict[str, Any]]:
    """Parse frontend raw_output, inject skills from agent_app, re-serialize."""
    routing = extract_skill_routing(agent_app_source)
    bindings = extract_ui_bindings(agent_app_source)
    page, fmt = parse_app_page_payload(frontend_raw)
    meta: Dict[str, Any] = {
        "ok": False,
        "filled": 0,
        "format": fmt,
        "routing_keys": list(routing.keys()),
        "ui_bindings": dict(bindings),
        "has_ui_bindings": bool(bindings),
    }
    if not page:
        meta["reason"] = "no_app_page_json"
        return frontend_raw, meta
    if not routing:
        meta["reason"] = "no_skill_routing"
        return frontend_raw, meta

    before_empty = sum(
        1
        for s in (page.get("stages") or [])
        if isinstance(s, dict) and not str(s.get("skill") or "").strip()
    )
    before_invalid = sum(
        1
        for s in (page.get("stages") or [])
        if isinstance(s, dict)
        and str(s.get("skill") or "").strip()
        and str(s.get("skill") or "").strip() not in routing
    )
    inject_app_page_skills(
        page, routing, ui_bindings=bindings, agent_app_source=agent_app_source
    )
    stats = page.pop("_skill_inject_stats", {}) or {}
    after_empty = sum(
        1
        for s in (page.get("stages") or [])
        if isinstance(s, dict) and not str(s.get("skill") or "").strip()
    )
    after_invalid = sum(
        1
        for s in (page.get("stages") or [])
        if isinstance(s, dict)
        and str(s.get("skill") or "").strip()
        and str(s.get("skill") or "").strip() not in routing
    )
    meta["filled"] = int(stats.get("filled") or max(0, before_empty - after_empty))
    meta["replaced"] = int(stats.get("replaced") or 0)
    meta["invalid_before"] = before_invalid
    meta["ok"] = after_empty == 0 and after_invalid == 0
    meta["empty_before"] = before_empty
    meta["empty_after"] = after_empty

    new_json = json.dumps(page, ensure_ascii=False, indent=2)
    if fmt == "file_block" or "app_page.json" in str(frontend_raw):
        new_raw = f"## FILE: app_page.json\n{new_json}\n"
    else:
        new_raw = new_json
    return new_raw, meta


def skill_routing_context_block(agent_app_source: Any) -> str:
    """Compact prompt block: skill_routing + required ui_bindings for FE."""
    routing = extract_skill_routing(agent_app_source)
    if not routing:
        return ""
    lines = [
        "## skill_routing（工厂强制 — stage.skill 必须从此表精确复制 key，禁止留空、禁止编造）",
        json.dumps(routing, ensure_ascii=False, indent=2),
    ]
    bindings = extract_ui_bindings(agent_app_source)
    if bindings:
        lines.append(
            "## ui_bindings（工厂强制 — component → skill；每个 stage 优先按此表填 skill）"
        )
        lines.append(json.dumps(bindings, ensure_ascii=False, indent=2))
    else:
        lines.append(
            "## ui_bindings 缺失警告：agent_manifest 应含 ui_bindings；"
            "请仅用 skill_routing 的 key，禁止编造；引擎将用 token 重叠兜底"
        )
    return "\n".join(lines)


def speech_pipeline_context_block(prd_source: Any) -> str:
    """Prompt block so FE follows PRD decisions.speech_pipeline for transcript UI."""
    try:
        from core.harness.execution.factory_artifact_sanitize import (
            _speech_pipeline_from_src,
        )
    except Exception:
        return ""
    sp = _speech_pipeline_from_src(prd_source)
    if not sp:
        return ""
    lines = [
        "## speech_pipeline（工厂强制 — 来自 PRD decisions，决定结果页转写区块）",
        f"value: {sp}",
    ]
    if sp in ("asr", "hybrid"):
        lines.append(
            "要求：result_dashboard.sections **必须**含 "
            '{"key":"transcript","label":"语音转写","type":"subtitle_timeline"}；'
            "禁止仅用 subtitle/summary 冒充转写。"
        )
    elif sp in ("audio_features_only", "features_only", "none"):
        lines.append(
            "要求：sections **禁止**「语音识别/转写/ASR」文案与 transcript section；"
            "用「语音声学特征 / VAD」。"
        )
    return "\n".join(lines)
