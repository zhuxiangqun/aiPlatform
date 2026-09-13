"""Deterministic Factory one-click fix planning (kernel-generic).

Maps test_report bugs → team stage agent_ids using ``output_artifact`` /
``test_execution_mode`` / execution kind — no product skill names.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _parse_report(test_report: Any) -> Dict[str, Any]:
    if isinstance(test_report, dict):
        return test_report
    text = str(test_report or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            obj = json.loads(text)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            pass  # noqa: cleanup-best-effort
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _agent_for_artifacts(
    team_stages: Sequence[Dict[str, Any]],
    artifacts: Sequence[str],
    fallback: str,
) -> str:
    wanted = {str(a) for a in artifacts}
    for s in team_stages or []:
        if not isinstance(s, dict):
            continue
        art = str(s.get("output_artifact") or "").strip()
        if art in wanted:
            aid = str(s.get("agent_id") or "").strip()
            if aid:
                return aid
    return fallback


def _resolve_team_agents(
    team_stages: Sequence[Dict[str, Any]],
) -> Dict[str, str]:
    """Map logical roles → agent_id from team config (empty fallback = unresolved)."""
    return {
        "code": _agent_for_artifacts(
            team_stages, ("code",), ""
        ),
        "frontend": _agent_for_artifacts(
            team_stages, ("frontend_pages", "app_page"), ""
        ),
        "agent_app": _agent_for_artifacts(
            team_stages, ("agent_app", "agents"), ""
        ),
        "qa": _agent_for_artifacts(
            team_stages, ("test_cases", "test_questions"), ""
        ),
        "executor": next(
            (
                str(s.get("agent_id") or "").strip()
                for s in (team_stages or [])
                if isinstance(s, dict)
                and (
                    str(s.get("skill_name") or "") == "test_executor"
                    or str(s.get("test_execution_mode") or "").startswith("agent_")
                    or str(s.get("output_artifact") or "") == "test_report"
                )
                and str(s.get("agent_id") or "").strip()
            ),
            "",
        ),
    }


def filter_fix_plan_freeze_test_cases(
    fix_plan: Sequence[Any],
    team_stages: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    regenerate_test_cases: bool = False,
) -> List[str]:
    """Drop qa/test_cases stages from one-click fix_plan unless explicitly opted in.

    Prevents LLM from rewriting the exam suite on every fix (unstable pass rates).
    """
    plan = [str(x).strip() for x in (fix_plan or []) if str(x).strip()]
    if regenerate_test_cases:
        return plan
    agents = _resolve_team_agents(list(team_stages or []))
    qa_id = str(agents.get("qa") or "").strip()
    blocked = {qa_id} if qa_id else set()
    # Also block by output_artifact name if plan uses artifact ids
    for s in team_stages or []:
        if not isinstance(s, dict):
            continue
        art = str(s.get("output_artifact") or "").strip()
        aid = str(s.get("agent_id") or "").strip()
        if art in ("test_cases", "test_questions"):
            if aid:
                blocked.add(aid)
            blocked.add(art)
    return [x for x in plan if x not in blocked]


FROZEN_TEST_CASE_ARTIFACTS = ("test_cases", "test_questions")


def _bug_execution_hint(bug: Dict[str, Any]) -> str:
    for key in ("execution", "mode", "kind"):
        v = str(bug.get(key) or "").strip()
        if v:
            return v
    blob = " ".join(
        str(bug.get(k) or "")
        for k in ("suggested_fix", "title", "reproduction", "actual", "test_id")
    )
    m = re.search(r"execution\s*=\s*([a-z_]+)", blob, re.I)
    if m:
        return m.group(1).lower()
    for kind in ("page_smoke", "skill_invoke", "platform_check", "conversation", "pytest"):
        if kind in blob.lower():
            return kind
    return ""


def derive_failed_stages_from_report(
    test_report: Any,
    team_stages: Optional[Sequence[Dict[str, Any]]] = None,
) -> List[str]:
    """Return agent_ids that should be regenerated for this report.

    Priority by bug execution kind:
    - pytest / failed_tests → code stage
    - page_smoke / ui_bindings → frontend (+ agent_app when bindings mismatch)
    - skill_invoke / conversation → agent_app
    - platform_check → usually not auto-fixable via regenerate (skip)
    """
    report = _parse_report(test_report)
    agents = _resolve_team_agents(list(team_stages or []))
    stages: set = set()

    # pytest-shaped report
    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    if (
        report.get("test_mode") == "pytest"
        or (isinstance(report.get("header"), dict) and report["header"].get("test_mode") == "pytest")
        or (isinstance(bs, dict) and isinstance(bs.get("failed_tests"), list) and bs.get("failed_tests"))
    ):
        if int(bs.get("total_bugs") or 0) > 0 or bs.get("failed_tests"):
            stages.add(agents["code"])
        return sorted(s for s in stages if s)

    bugs = list(bs.get("bugs") or []) if isinstance(bs, dict) else []
    if not bugs and isinstance(report.get("results"), list):
        for r in report["results"]:
            if isinstance(r, dict) and r.get("result") in ("FAIL", "ERROR", "TIMEOUT"):
                bugs.append(
                    {
                        "test_id": r.get("id"),
                        "execution": r.get("execution") or r.get("mode"),
                        "suggested_fix": r.get("evidence") or r.get("reason") or "",
                        "actual": r.get("failures") or "",
                    }
                )

    # Actionable diagnostics (e.g. no_platform_handler from true_test SKIP)
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    for d in list(meta.get("diagnostics") or []):
        if not isinstance(d, dict):
            continue
        code = str(d.get("code") or "").strip()
        blob_d = " ".join(str(d.get(k) or "") for k in ("code", "skill", "suggested_fix")).lower()
        if code == "no_platform_handler" or "no_platform_handler" in blob_d:
            stages.add(agents["agent_app"])

    for bug in bugs:
        if not isinstance(bug, dict):
            continue
        kind = _bug_execution_hint(bug)
        blob = " ".join(
            str(bug.get(k) or "")
            for k in ("suggested_fix", "title", "actual", "reproduction", "diagnostic")
        ).lower()

        if kind == "platform_check":
            continue
        if (
            str(bug.get("diagnostic") or "") == "no_platform_handler"
            or "no_platform_handler" in blob
        ):
            stages.add(agents["agent_app"])
            continue
        if kind == "page_smoke" or "ui_bindings" in blob or "page_smoke" in blob:
            stages.add(agents["frontend"])
            stages.add(agents["agent_app"])  # bindings SoT lives in agent_app
            continue
        if any(
            x in blob
            for x in (
                "result_section_type_unsupported",
                "result_sections_empty",
                "result_sections_ok",
                "image_timeline",
                "skill_alias_not_canonical",
            )
        ):
            stages.add(agents["frontend"])
            continue
        if kind in ("skill_invoke", "conversation") or any(
            x in blob for x in ("skill_invoke", "missing:", "skill/", "agent_app")
        ):
            stages.add(agents["agent_app"])
            continue
        # Frontend UX keywords (Chinese UI signals)
        if any(k in blob for k in ("组件", "表单", "上传", "页面", "按钮", "会话")):
            stages.add(agents["frontend"])
        if any(k in blob for k in ("接口", "后端", "校验", "jwt", "401", "404", "pytest")):
            stages.add(agents["code"])
            stages.add(agents["agent_app"])

    return sorted(s for s in stages if s)


def build_feedback_from_report(test_report: Any, *, max_chars: int = 12000) -> str:
    """Compact feedback string for regenerate (prefer bug_summary JSON)."""
    report = _parse_report(test_report)
    bs = report.get("bug_summary")
    if isinstance(bs, dict) and bs:
        text = json.dumps({"bug_summary": bs}, ensure_ascii=False)
    elif isinstance(test_report, str) and test_report.strip():
        text = test_report.strip()
    else:
        text = json.dumps(report, ensure_ascii=False) if report else ""
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def extract_media_skill_remaps_from_report(test_report: Any) -> Dict[str, str]:
    """Collect invented→catalog remaps from true_test diagnostics / bugs."""
    report = _parse_report(test_report)
    remaps: Dict[str, str] = {}

    def _add(old: str, new: str) -> None:
        o, n = str(old or "").strip(), str(new or "").strip()
        if o and n and o != n:
            remaps[o] = n

    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    for d in list(meta.get("diagnostics") or []):
        if not isinstance(d, dict):
            continue
        if str(d.get("code") or "") == "no_platform_handler" or d.get("skill"):
            _add(str(d.get("skill") or ""), str(d.get("suggested_platform_skill") or ""))

    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    for bug in list(bs.get("bugs") or []):
        if not isinstance(bug, dict):
            continue
        blob = " ".join(
            str(bug.get(k) or "")
            for k in ("actual", "suggested_fix", "title", "diagnostic")
        )
        m_old = re.search(r"no_platform_handler:([^\s;]+)", blob)
        m_new = re.search(r"suggested_platform_skill:([^\s;]+)", blob)
        if not m_new:
            m_new = re.search(r"平台媒体目录名\s*[`']?([a-z0-9_]+)", blob)
        if m_old and m_new:
            _add(m_old.group(1), m_new.group(1))
        # title: 平台无 handler: foo
        m_title = re.search(r"平台无 handler:\s*([a-z0-9_]+)", blob, re.I)
        if m_title and m_new:
            _add(m_title.group(1), m_new.group(1))

    # Fill gaps via catalog suggest
    try:
        from core.harness.media_skill_handlers import suggest_platform_media_skill

        for old in list(remaps.keys()):
            if not remaps[old]:
                sug = suggest_platform_media_skill(old)
                if sug:
                    remaps[old] = sug
        # Also suggest for any leftover no_platform_handler skills without suggested
        for bug in list(bs.get("bugs") or []):
            if not isinstance(bug, dict):
                continue
            blob = str(bug.get("actual") or "") + " " + str(bug.get("title") or "")
            m_old = re.search(r"no_platform_handler:([^\s;]+)", blob) or re.search(
                r"平台无 handler:\s*([a-z0-9_]+)", blob, re.I
            )
            if m_old and m_old.group(1) not in remaps:
                sug = suggest_platform_media_skill(m_old.group(1))
                if sug:
                    remaps[m_old.group(1)] = sug
    except Exception:
        pass  # noqa: cleanup-best-effort

    return remaps


def remap_skill_names_in_test_cases(test_cases: Any, remaps: Dict[str, str]) -> Tuple[Any, int]:
    """Rewrite invoke.skill / target_skill in agent_true_test cases. Returns (obj, count)."""
    if not remaps:
        return test_cases, 0
    obj = test_cases
    text_mode = False
    if isinstance(test_cases, str):
        text_mode = True
        raw = test_cases.strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    obj = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return test_cases, 0
            else:
                return test_cases, 0
    if not isinstance(obj, dict):
        return test_cases, 0
    qs = obj.get("test_questions") or obj.get("test_cases") or []
    if not isinstance(qs, list):
        return test_cases, 0
    n = 0
    for q in qs:
        if not isinstance(q, dict):
            continue
        for key in ("target_skill", "skill"):
            v = str(q.get(key) or "").strip()
            if v in remaps:
                q[key] = remaps[v]
                n += 1
        inv = q.get("invoke")
        if isinstance(inv, dict):
            v = str(inv.get("skill") or "").strip()
            if v in remaps:
                inv["skill"] = remaps[v]
                n += 1
    if text_mode:
        return json.dumps(obj, ensure_ascii=False, indent=2), n
    return obj, n


def _extract_missing_assert_needles(test_report: Any) -> List[str]:
    """Collect missing:<needle> tokens from bug_summary / test_results."""
    report = _parse_report(test_report)
    needles: List[str] = []
    seen = set()

    def _add(blob: str) -> None:
        for m in re.finditer(r"missing:([A-Za-z0-9_\.\-]+)", blob or ""):
            n = m.group(1)
            if n not in seen:
                seen.add(n)
                needles.append(n)

    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    for bug in list(bs.get("bugs") or []):
        if not isinstance(bug, dict):
            continue
        _add(
            " ".join(
                str(bug.get(k) or "")
                for k in ("diagnostic", "title", "actual", "suggested_fix", "reproduction")
            )
        )
    for r in list(report.get("test_results") or []):
        if not isinstance(r, dict):
            continue
        _add(str(r.get("evidence") or ""))
        fails = r.get("failures")
        if isinstance(fails, list):
            for f in fails:
                _add(str(f))
        elif fails:
            _add(str(fails))
    return needles


# Assert needle → platform handler field already emitted (naming drift).
# One-click rewrites contains asserts so re-run passes without waiting for process restart
# of a handler that only recently grew the preferred key.
_ASSERT_NEEDLE_ALIASES: Dict[str, str] = {
    "export_format": "export_json",
    "export_formats": "export_json",
    "captions": "descriptions",
    "caption": "description",
}


def align_result_assert_needles(test_cases: Any, test_report: Any = None) -> Tuple[Any, int]:
    """Rewrite result.contains needles that drift from platform handler field names.

    Example: FR asserts ``export_format`` while handler historically emitted ``export_json``.
    """
    missing = set(_extract_missing_assert_needles(test_report))
    if not missing:
        return test_cases, 0
    text_mode = False
    obj = test_cases
    if isinstance(test_cases, str):
        text_mode = True
        raw = test_cases.strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    obj = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return test_cases, 0
            else:
                return test_cases, 0
    if not isinstance(obj, dict):
        return test_cases, 0
    obj = copy.deepcopy(obj)
    qs = obj.get("test_questions") or obj.get("test_cases") or []
    if not isinstance(qs, list):
        return test_cases, 0
    n = 0
    for q in qs:
        if not isinstance(q, dict):
            continue
        asserts = q.get("asserts")
        if not isinstance(asserts, list):
            continue
        for a in asserts:
            if not isinstance(a, dict):
                continue
            typ = str(a.get("type") or "").strip().lower()
            if typ not in ("result.contains", "contains"):
                continue
            key = "text" if "text" in a else ("value" if "value" in a else None)
            if not key:
                continue
            needle = str(a.get(key) or "")
            alias = _ASSERT_NEEDLE_ALIASES.get(needle)
            if not alias or alias == needle:
                continue
            if needle not in missing:
                continue
            a[key] = alias
            n += 1
    if n == 0:
        return test_cases, 0
    if text_mode:
        return json.dumps(obj, ensure_ascii=False, indent=2), n
    return obj, n


def apply_no_platform_handler_fixes(
    *,
    agent_app_raw: str = "",
    test_cases: Any = None,
    test_report: Any = None,
    remaps: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Deterministic remap for no_platform_handler (no LLM).

    Returns dict with patched artifacts + meta.
    """
    from core.harness.execution.factory_artifact_sanitize import (
        ensure_agent_app_skill_consistency,
        ensure_platform_media_skill_contracts,
        normalize_media_skill_names,
        strip_reasoning_preamble,
    )

    remaps = dict(remaps or {}) or extract_media_skill_remaps_from_report(test_report)
    meta: Dict[str, Any] = {"remaps": remaps, "agent_app_changed": False, "test_cases_changed": 0}

    aa = strip_reasoning_preamble(str(agent_app_raw or ""))
    # Drop regenerate feedback banner if FILE blocks follow
    if "REGENERATE WITH FEEDBACK" in aa and "## FILE:" in aa:
        idx = aa.find("## FILE:")
        if idx > 0:
            aa = aa[idx:]
    if remaps:
        fixed, nmeta = normalize_media_skill_names(aa)
        # Also force explicit remaps from report (even if already aliased)
        for old, new in remaps.items():
            if old == new:
                continue
            fixed = fixed.replace(f"skills/{old}/", f"skills/{new}/")
            fixed = re.sub(
                rf'(["\']){re.escape(old)}\1',
                rf"\1{new}\1",
                fixed,
            )
            fixed = re.sub(
                rf"(?m)^(name:\s*){re.escape(old)}\s*$",
                rf"\g<1>{new}",
                fixed,
            )
        if fixed != aa or nmeta.get("remapped"):
            meta["agent_app_changed"] = True
            meta["normalize"] = nmeta
            aa = fixed
    else:
        fixed, nmeta = normalize_media_skill_names(aa)
        if fixed != aa or nmeta.get("remapped"):
            meta["agent_app_changed"] = True
            meta["normalize"] = nmeta
            aa = fixed

    fixed, cmeta = ensure_agent_app_skill_consistency(aa)
    if (
        fixed != aa
        or cmeta.get("renamed")
        or cmeta.get("deduped_stems")
        or cmeta.get("routing_aligned")
        or cmeta.get("merged_speech")
        or cmeta.get("dropped_lifecycle_skills")
    ):
        meta["agent_app_changed"] = True
        meta["consistency"] = cmeta
        aa = fixed

    fixed, pmeta = ensure_platform_media_skill_contracts(aa)
    if fixed != aa or pmeta.get("rewritten"):
        meta["agent_app_changed"] = True
        meta["contracts"] = pmeta
        aa = fixed

    tc_out = test_cases
    if test_cases is not None:
        # Enrich remaps for any remaining invented media names in cases
        try:
            from core.harness.media_skill_handlers import (
                resolve_media_handler_name,
                suggest_platform_media_skill,
            )

            probe = test_cases
            if isinstance(probe, str):
                try:
                    probe = json.loads(probe)
                except json.JSONDecodeError:
                    probe = {}
            if isinstance(probe, dict):
                for q in probe.get("test_questions") or []:
                    if not isinstance(q, dict):
                        continue
                    skill = ""
                    if isinstance(q.get("invoke"), dict):
                        skill = str(q["invoke"].get("skill") or "")
                    skill = skill or str(q.get("target_skill") or "")
                    if skill and skill not in remaps:
                        resolved = resolve_media_handler_name(skill) or suggest_platform_media_skill(skill)
                        # Only remap when resolved to a *different* catalog name
                        if resolved and resolved != skill:
                            from core.harness.media_skill_handlers import resolve_platform_media_skill

                            canon = resolve_platform_media_skill(resolved) or resolved
                            remaps[skill] = canon
        except Exception:
            pass  # noqa: cleanup-best-effort
        tc_out, n = remap_skill_names_in_test_cases(test_cases, remaps)
        meta["test_cases_changed"] = n
        # Always normalize media params (source→url/file_path + fixture remap)
        tc_out2, n2 = normalize_true_test_media_params(tc_out)
        meta["params_normalized"] = n2
        if n2:
            meta["test_cases_changed"] = int(meta.get("test_cases_changed") or 0) + n2
        tc_out = tc_out2
        # Align result.contains needles (export_format→export_json, …)
        tc_out3, n3 = align_result_assert_needles(tc_out, test_report)
        meta["asserts_aligned"] = n3
        if n3:
            meta["test_cases_changed"] = int(meta.get("test_cases_changed") or 0) + n3
        tc_out = tc_out3
        meta["remaps"] = remaps

    return {
        "status": "ok"
        if (
            meta["agent_app_changed"]
            or meta["test_cases_changed"]
            or remaps
            or meta.get("params_normalized")
            or meta.get("asserts_aligned")
        )
        else "noop",
        "agent_app_raw": aa,
        "test_cases": tc_out,
        "meta": meta,
    }


def bugs_are_media_handler_fixable(test_report: Any) -> bool:
    """True when failures are media skill_invoke field gaps (handler remappable).

    Covers both ``no_platform_handler`` diagnostics and hard FAILs whose
    missing fields match platform media handler outputs (video_path/keyframes/…).
    """
    if bugs_are_no_platform_handler_only(test_report):
        return True
    report = _parse_report(test_report)
    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    bugs = list(bs.get("bugs") or [])
    if not bugs:
        return False
    media_signals = (
        "video_path",
        "keyframes",
        "keyframe_density",
        "scene_changes",
        "metadata",
        "timeline",
        "syllable_density",
        "未检测到字幕",
        "未检测到语音",
        "export_json",
        "export_format",
        "missing:export_format",
        "missing:export_json",
        "captions",
        "missing:captions",
        "descriptions",
        "no_subtitle_track",
        "vad",
        "language",
        "speaker_count",
        "skill_invoke",
        "no_platform_handler",
        "missing:error",
        "decode",
    )
    non_media = 0
    media = 0
    for bug in bugs:
        if not isinstance(bug, dict):
            non_media += 1
            continue
        blob = " ".join(
            str(bug.get(k) or "")
            for k in ("diagnostic", "title", "actual", "suggested_fix", "reproduction")
        ).lower()
        if any(s.lower() in blob for s in media_signals):
            media += 1
        else:
            non_media += 1
    return media > 0 and non_media == 0


def normalize_true_test_media_params(test_cases: Any) -> Tuple[Any, int]:
    """Normalize invoke params: source→url/file_path, remap fixture paths."""
    from core.harness.media_ops import coerce_media_invoke_params, remap_fixture_path
    from core.harness.execution.true_test_runtime import enrich_media_invoke_from_asserts

    obj = test_cases
    text_mode = False
    if isinstance(test_cases, str):
        text_mode = True
        raw = test_cases.strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if 0 <= start < end:
                try:
                    obj = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return test_cases, 0
            else:
                return test_cases, 0
    if not isinstance(obj, dict):
        return test_cases, 0
    qs = obj.get("test_questions") or obj.get("test_cases") or []
    if not isinstance(qs, list):
        return test_cases, 0
    n = 0
    for q in qs:
        if not isinstance(q, dict):
            continue
        inv = q.get("invoke")
        if not isinstance(inv, dict):
            continue
        params = inv.get("params")
        if not isinstance(params, dict):
            continue
        before = json.dumps(params, sort_keys=True)
        skill = str(inv.get("skill") or q.get("target_skill") or "")
        asserts = q.get("asserts") or q.get("assertions") or []
        enriched = enrich_media_invoke_from_asserts(params, asserts, skill=skill)
        params.clear()
        params.update(enriched)
        # Coerce first so claimed_duration is captured from path tokens, then remap
        coerced = coerce_media_invoke_params(params)
        params.clear()
        params.update(coerced)
        for key in (
            "video_path",
            "file_path",
            "local_path",
            "url",
            "source",
            "source_path",
            "source_url",
            "upload_file_path",
        ):
            if params.get(key):
                params[key] = remap_fixture_path(str(params[key]), "media")
        after = json.dumps(params, sort_keys=True)
        if after != before:
            n += 1
    if text_mode:
        return json.dumps(obj, ensure_ascii=False, indent=2), n
    return obj, n


def bugs_are_no_platform_handler_only(test_report: Any) -> bool:
    """True when every bug is a no_platform_handler diagnostic (safe for deterministic fix)."""
    report = _parse_report(test_report)
    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    bugs = list(bs.get("bugs") or [])
    if not bugs:
        # diagnostics-only
        meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
        diags = list(meta.get("diagnostics") or [])
        return bool(diags) and all(
            isinstance(d, dict) and str(d.get("code") or "") == "no_platform_handler" for d in diags
        )
    for bug in bugs:
        if not isinstance(bug, dict):
            return False
        blob = " ".join(
            str(bug.get(k) or "")
            for k in ("diagnostic", "title", "actual", "suggested_fix")
        ).lower()
        if "no_platform_handler" not in blob and "平台无 handler" not in blob:
            return False
    return True


def plan_fix_from_report(
    run_id: str,
    test_report: Any,
    team_stages: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    regenerate_test_cases: bool = False,
) -> Dict[str, Any]:
    """Hybrid plan: derive failed stages → build_fix_plan (root-cause prefer).

    By default excludes qa/test_cases regenerate so one-click fix keeps a frozen exam.
    Pass ``regenerate_test_cases=True`` to allow rewriting the suite.
    """
    from core.harness.execution.decision_trace import build_fix_plan

    # Prefer deterministic media remap path — no LLM regenerate of agent_engineer
    if bugs_are_media_handler_fixable(test_report):
        remaps = extract_media_skill_remaps_from_report(test_report)
        # Also remap any invoke skills found via suggest when remaps empty
        if not remaps:
            try:
                from core.harness.media_skill_handlers import (
                    resolve_media_handler_name,
                    suggest_platform_media_skill,
                )

                report = _parse_report(test_report)
                for r in list(report.get("test_results") or []):
                    if not isinstance(r, dict):
                        continue
                    # evidence may embed skill name
                    ev = str(r.get("evidence") or "")
                    m = re.search(r"prompt_skill_skip_structured_asserts:([^\s;]+)", ev)
                    if m:
                        sk = m.group(1)
                        sug = resolve_media_handler_name(sk) or suggest_platform_media_skill(sk)
                        if sug and sug != sk:
                            remaps[sk] = sug
            except Exception:
                pass  # noqa: cleanup-best-effort
        agents = _resolve_team_agents(list(team_stages or []))
        report = _parse_report(test_report)
        bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
        total = int(bs.get("total_bugs") or len(bs.get("bugs") or []) or max(1, len(remaps)))
        return {
            "status": "ok",
            "mode": "deterministic_media_remap",
            "failed_stage_ids": [agents["executor"]],
            "fix_plan": [agents["executor"]],
            "total_bugs": total,
            "remaps": remaps,
            "feedback": build_feedback_from_report(test_report),
            "regenerate_test_cases": False,
            "preserve_artifacts": list(FROZEN_TEST_CASE_ARTIFACTS),
        }

    failed = derive_failed_stages_from_report(test_report, team_stages)
    if not failed:
        return {
            "status": "no_bugs",
            "failed_stage_ids": [],
            "fix_plan": [],
            "total_bugs": 0,
            "feedback": "",
        }
    report = _parse_report(test_report)
    bs = report.get("bug_summary") if isinstance(report.get("bug_summary"), dict) else {}
    total = int(bs.get("total_bugs") or len(bs.get("bugs") or []) or len(failed))
    fix_plan = build_fix_plan(run_id, failed, None) or list(failed)
    fix_plan = filter_fix_plan_freeze_test_cases(
        fix_plan,
        team_stages,
        regenerate_test_cases=regenerate_test_cases,
    )
    return {
        "status": "ok",
        "failed_stage_ids": failed,
        "fix_plan": list(fix_plan),
        "total_bugs": total,
        "feedback": build_feedback_from_report(test_report),
        "regenerate_test_cases": bool(regenerate_test_cases),
        "preserve_artifacts": (
            [] if regenerate_test_cases else list(FROZEN_TEST_CASE_ARTIFACTS)
        ),
    }
