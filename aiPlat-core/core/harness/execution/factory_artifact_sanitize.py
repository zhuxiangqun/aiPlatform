"""Deterministic factory artifact sanitizers (kernel-generic).

Triggers belong in PipelineStageConfig fields:
  architecture_mode / test_execution_mode / quality_gate.*
Never match business keywords, agent_id, or skill_name.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


_log = logging.getLogger(__name__)

# F5b: canonical media SKILL bodies live under workspace_seeds/factory_sanitize/
_FACTORY_SANITIZE_SEEDS = Path(__file__).resolve().parents[2] / "workspace_seeds" / "factory_sanitize"


def _load_factory_sanitize_skill(filename: str, **subs: str) -> Optional[str]:
    """Load a SKILL seed and substitute ``{{key}}`` placeholders. None if missing."""
    try:
        from core.harness.team_factory_seeds import resolve_factory_sanitize_file

        seed = resolve_factory_sanitize_file(filename)
    except Exception:
        seed = None
    if seed is None:
        seed = _FACTORY_SANITIZE_SEEDS / filename
        if not seed.is_file():
            return None
    text = seed.read_text(encoding="utf-8")
    for key, val in subs.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def load_canonical_media_skill_md(skill_name: str, app_name: str) -> str:
    """Public loader for factory_sanitize canonical media SKILL templates."""
    mapping = {
        "frame_analyzer": "frame_analyzer.SKILL.md",
        "speech_analyzer": "speech_analyzer.SKILL.md",
        "video_downloader": "video_downloader.SKILL.md",
        "report_json_export": "report_json_export.SKILL.md",
    }
    fname = mapping.get(str(skill_name or "").strip())
    if not fname:
        raise ValueError(f"unknown canonical media skill: {skill_name!r}")
    loaded = _load_factory_sanitize_skill(fname, app_name=app_name)
    if loaded is not None:
        return loaded
    raise FileNotFoundError(f"factory sanitize seed missing: {_FACTORY_SANITIZE_SEEDS / fname}")


_REASONING_HEAD = re.compile(
    r"(?m)^(?:#{1,3}\s*)?(?:步骤\s*[0-9]|分析关键约束|列出\s*[0-9]|方案\s*[ABC]|取舍|"
    r"比较方案|可行方案|Checklist\s*验证|步骤\d|Code Step|Agent Step|"
    r"🛑\s*REGENERATE|REGENERATE WITH FEEDBACK)"
)
_FILE_MARK = re.compile(r"(?m)^#{2,4}\s*FILE:\s*")
_JSON_READY = re.compile(r"(?m)^\s*\{")
_PYTEST_FILE = re.compile(r"(?m)^#{2,4}\s*FILE:\s*.*tests?/.*\.py", re.I)
_REAL_ROUTE_DECO = re.compile(
    r"""@(?:app|router)\.(?:get|post|put|delete|patch)\(\s*['\"]([^'\"]+)['\"]"""
)
_AGENT_DEF_FILE = re.compile(
    r"(?m)^#{2,4}\s*FILE:\s*.*(?:AGENT\.md|SKILL\.md|agent_manifest\.json)",
    re.I,
)


def strip_reasoning_preamble(text: str) -> str:
    """Drop leading step/scheme analysis so the first payload is the artifact."""
    s = str(text or "")
    if not s.strip():
        return s
    m = _FILE_MARK.search(s)
    if m and m.start() > 0 and _REASONING_HEAD.search(s[: m.start()]):
        return s[m.start() :].lstrip()
    m = re.search(r"(?m)^##\s+\S+", s)
    if m and m.start() > 0 and _REASONING_HEAD.search(s[: m.start()]):
        fm = _FILE_MARK.search(s)
        if fm:
            return s[fm.start() :].lstrip()
        return s[m.start() :].lstrip()
    m = _JSON_READY.search(s)
    if m and m.start() > 0 and _REASONING_HEAD.search(s[: m.start()]):
        return s[m.start() :].lstrip()
    return s


def _parse_json_obj_rest(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Parse first JSON object; tolerate trailing FILE/markdown (raw_decode)."""
    s = str(text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s, count=1).strip()
    start = 0
    if not s.startswith("{"):
        brace = s.find("{")
        if brace < 0:
            return None, str(text or "")
        start = brace
    try:
        obj, idx = json.JSONDecoder().raw_decode(s[start:])
    except json.JSONDecodeError:
        return None, str(text or "")
    if not isinstance(obj, dict):
        return None, str(text or "")
    rest = s[start + idx :]
    return obj, rest


def _try_json_obj(text: str) -> Optional[Dict[str, Any]]:
    obj, _ = _parse_json_obj_rest(text)
    return obj


def _repair_glued_file_headers(text: str) -> str:
    """Ensure ``## FILE:`` markers start on their own line (LLM often glues ``---## FILE:``)."""
    s = str(text or "")
    if not s:
        return s
    return re.sub(r"([^\n])(#{2,4}\s*FILE:\s*)", r"\1\n\2", s)


def ensure_dual_component_stages(
    page: Dict[str, Any],
    *,
    ui_bindings: Optional[Dict[str, str]] = None,
    primary_component: str = "file_upload",
    secondary_component: str = "data_form",
    secondary_stage_id: str = "secondary_input",
    secondary_title: str = "Additional input",
    secondary_field_name: str = "input_value",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """If ui_bindings declares both components but page only has primary, add secondary."""
    meta: Dict[str, Any] = {"added_secondary": False, "ok": True}
    if not isinstance(page, dict):
        return page, {**meta, "ok": False}
    bindings = ui_bindings or {}
    if primary_component not in bindings or secondary_component not in bindings:
        return page, meta

    stages = page.get("stages")
    if not isinstance(stages, list):
        return page, meta

    comps = {
        str(s.get("component") or "")
        for s in stages
        if isinstance(s, dict)
    }
    if primary_component in comps and secondary_component in comps:
        return page, meta
    if primary_component not in comps:
        return page, meta

    skill = str(bindings.get(secondary_component) or bindings.get(primary_component) or "")
    if not skill:
        return page, meta

    insert_at = 0
    next_id = "next"
    for i, s in enumerate(stages):
        if isinstance(s, dict) and s.get("component") == primary_component:
            insert_at = i + 1
            next_id = str(s.get("next") or "next")
            s["next"] = secondary_stage_id
            break

    stages.insert(
        insert_at,
        {
            "id": secondary_stage_id,
            "title": secondary_title,
            "skill": skill,
            "component": secondary_component,
            "config": {
                "fields": [
                    {
                        "name": secondary_field_name,
                        "label": secondary_field_name,
                        "type": "text",
                        "required": True,
                    }
                ]
            },
            "next": next_id,
        },
    )
    page["stages"] = stages
    meta["added_secondary"] = True
    return page, meta


def ensure_dual_ingest_stages(
    page: Dict[str, Any],
    *,
    prd_src: Any = None,  # noqa: ARG001 — ignored (legacy API)
    ui_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Compatibility wrapper: dual file_upload + data_form from ui_bindings only."""
    out, meta = ensure_dual_component_stages(
        page,
        ui_bindings=ui_bindings,
        primary_component="file_upload",
        secondary_component="data_form",
        secondary_stage_id="url_import",
        secondary_title="URL input",
        secondary_field_name="url",
    )
    if meta.get("added_secondary"):
        meta["added_data_form"] = True
    return out, meta


_URL_FIELD_HINTS = ("url", "link", "source_url", "video_url", "href")
_INGEST_SKILL_HINTS = (
    "download",
    "upload",
    "ingest",
    "import",
    "fetcher",
    "fetch",
)


def _field_is_url_like(field: Dict[str, Any]) -> bool:
    name = str(field.get("name") or "").lower()
    ftype = str(field.get("type") or "").lower()
    if ftype == "url":
        return True
    return any(h in name for h in _URL_FIELD_HINTS)


def _skill_looks_ingest(skill: str, ingest_skills: set) -> bool:
    s = str(skill or "").strip()
    if not s:
        return True
    if s in ingest_skills:
        return True
    low = s.lower()
    return any(h in low for h in _INGEST_SKILL_HINTS)


def _prior_stage_id(
    stages: List[Any],
    idx: int,
    prefer_components: Tuple[str, ...],
) -> Optional[str]:
    for j in range(idx - 1, -1, -1):
        s = stages[j]
        if not isinstance(s, dict):
            continue
        if str(s.get("component") or "") in prefer_components:
            return str(s.get("id") or "") or None
    for j in range(idx - 1, -1, -1):
        s = stages[j]
        if isinstance(s, dict) and s.get("id"):
            return str(s["id"])
    return None


def ensure_wizard_stage_io(
    page: Dict[str, Any],
    *,
    ui_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Kernel-generic wizard I/O repair for factory ``app_page.json``.

    - data_form: URL-like fields get ``show_when`` when a source_type selector exists
    - progress_poller: wire ``task_id``/``video_path`` from prior upload/source;
      if skill is still the ingest/download skill, remap to result_dashboard skill
      (sync analysis pipeline returns terminal ``status`` for ProgressPoller)
    - result_dashboard: wire ``task_id``/``video_path`` from progress
    """
    meta: Dict[str, Any] = {
        "ok": True,
        "show_when": 0,
        "progress_input": False,
        "progress_skill_remap": False,
        "results_input": False,
    }
    if not isinstance(page, dict):
        return page, {**meta, "ok": False}
    stages = page.get("stages")
    if not isinstance(stages, list):
        return page, meta

    bindings = {str(k): str(v) for k, v in (ui_bindings or {}).items() if k and v}
    ingest_skills = {
        bindings[c]
        for c in ("file_upload", "data_form")
        if c in bindings and bindings[c]
    }
    analysis_skill = (
        bindings.get("result_dashboard")
        or bindings.get("progress_poller")
        or ""
    )

    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        comp = str(stage.get("component") or "")
        cfg = stage.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
            stage["config"] = cfg

        if comp == "data_form":
            fields = cfg.get("fields")
            if isinstance(fields, list):
                has_source_type = any(
                    isinstance(f, dict)
                    and str(f.get("name") or "").lower() in ("source_type", "source")
                    for f in fields
                )
                if has_source_type:
                    for f in fields:
                        if not isinstance(f, dict) or not _field_is_url_like(f):
                            continue
                        sw = f.get("show_when")
                        if not isinstance(sw, dict) or not sw:
                            f["show_when"] = {"source_type": "url"}
                            meta["show_when"] += 1

        elif comp == "progress_poller":
            prior = _prior_stage_id(
                stages, i, ("file_upload", "data_form")
            ) or "upload"
            inp = cfg.get("input")
            if not isinstance(inp, dict):
                inp = {}
                cfg["input"] = inp
            changed = False
            if not str(inp.get("task_id") or "").strip():
                inp["task_id"] = f"{{{{{prior}.task_id}}}}"
                changed = True
            # Generic path wiring (media: video_path; docs/files: file_path)
            has_path = any(
                str(inp.get(k) or "").strip()
                for k in (
                    "video_path",
                    "file_path",
                    "upload_file_path",
                    "local_path",
                    "document_path",
                    "artifact_path",
                )
            )
            if not has_path:
                inp.setdefault("file_path", f"{{{{{prior}.file_path}}}}")
                inp.setdefault("video_path", f"{{{{{prior}.video_path}}}}")
                changed = True
            if changed:
                meta["progress_input"] = True

            cur_skill = str(stage.get("skill") or "").strip()
            # Prefer analysis/report skill when progress still points at ingest
            target = analysis_skill or bindings.get("result_dashboard") or ""
            try:
                from core.harness.media_skill_handlers import resolve_media_handler_name

                target = resolve_media_handler_name(target) or target
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
            if target and _skill_looks_ingest(cur_skill, ingest_skills):
                if cur_skill != target:
                    stage["skill"] = target
                    meta["progress_skill_remap"] = True
            elif not cur_skill and target:
                stage["skill"] = target
                meta["progress_skill_remap"] = True
            else:
                # Alias on progress (report_assembly) → canonical catalog name
                try:
                    from core.harness.media_skill_handlers import resolve_media_handler_name

                    canon = resolve_media_handler_name(cur_skill)
                    if canon and canon != cur_skill:
                        stage["skill"] = canon
                        meta["progress_skill_remap"] = True
                except Exception:
                    logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

            labels = cfg.get("labels")
            if not isinstance(labels, dict):
                labels = {}
                cfg["labels"] = labels
            labels.setdefault("analyzing", "分析处理中")
            labels.setdefault("processing", "分析处理中")
            labels.setdefault("completed", "已完成")
            labels.setdefault("ready", "素材就绪")
            labels.setdefault("failed", "分析失败")

        elif comp == "result_dashboard":
            prior = _prior_stage_id(stages, i, ("progress_poller",)) or "progress"
            inp = cfg.get("input")
            if not isinstance(inp, dict):
                inp = {}
                cfg["input"] = inp
            changed = False
            if not str(inp.get("task_id") or "").strip():
                inp["task_id"] = f"{{{{{prior}.task_id}}}}"
                changed = True
            has_path = any(
                str(inp.get(k) or "").strip()
                for k in (
                    "video_path",
                    "file_path",
                    "upload_file_path",
                    "local_path",
                    "document_path",
                    "artifact_path",
                )
            )
            if not has_path:
                inp.setdefault("file_path", f"{{{{{prior}.file_path}}}}")
                inp.setdefault("video_path", f"{{{{{prior}.video_path}}}}")
                changed = True
            if changed:
                meta["results_input"] = True
            dash_skill = bindings.get("result_dashboard")
            try:
                from core.harness.media_skill_handlers import resolve_media_handler_name

                dash_skill = resolve_media_handler_name(dash_skill) or dash_skill
                cur = str(stage.get("skill") or "").strip()
                canon_cur = resolve_media_handler_name(cur) if cur else None
                if canon_cur and canon_cur != cur:
                    stage["skill"] = canon_cur
                    cur = canon_cur
            except Exception:
                cur = str(stage.get("skill") or "").strip()
            if dash_skill and (
                not cur
                or _skill_looks_ingest(cur, ingest_skills)
            ):
                stage["skill"] = dash_skill

    page["stages"] = stages
    return page, meta


def canonicalize_app_page_media_skills(
    page: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Rewrite app_page stage.skill aliases to platform media catalog canonical names.

    ``report_assembly`` → ``report_json_export`` so routing/ui_bindings/page stay aligned.
    Non-media skills are left unchanged.
    """
    meta: Dict[str, Any] = {"ok": True, "remapped": {}}
    if not isinstance(page, dict):
        return page, {**meta, "ok": False}
    stages = page.get("stages")
    if not isinstance(stages, list):
        return page, meta
    try:
        from core.harness.media_skill_handlers import resolve_media_handler_name
    except Exception as exc:  # noqa: BLE001
        return page, {**meta, "ok": False, "reason": str(exc)[:120]}

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        sk = str(stage.get("skill") or "").strip()
        if not sk:
            continue
        canon = resolve_media_handler_name(sk)
        if canon and canon != sk:
            stage["skill"] = canon
            meta["remapped"][sk] = canon
    return page, meta


def _speech_pipeline_from_src(src: Any) -> str:
    """Best-effort extract decisions.speech_pipeline from PRD / artifact blob."""
    obj: Any = src
    if isinstance(src, dict):
        raw = src.get("raw_output")
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                obj = src
        elif isinstance(raw, dict):
            obj = raw
    if isinstance(obj, str) and obj.strip().startswith("{"):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            return ""
    if not isinstance(obj, dict):
        return ""
    decisions = obj.get("decisions") if isinstance(obj.get("decisions"), dict) else {}
    sp = str(decisions.get("speech_pipeline") or "").strip().lower()
    if sp:
        return sp
    # Heuristic from FR / description when decisions missing
    blob = json.dumps(obj, ensure_ascii=False)
    if any(k in blob for k in ("语音转写", "ASR", "asr", "speech_to_text", "语音识别")):
        if "不转写" not in blob and "不进行语音到文字" not in blob:
            return "asr"
    if "audio_features_only" in blob or "声学粗标签" in blob or "不转写" in blob:
        return "audio_features_only"
    return ""


def ensure_result_dashboard_sections(
    page: Dict[str, Any],
    *,
    speech_pipeline: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Remap unknown result_dashboard section types to platform-supported ones.

    Factory must emit types the platform ResultDashboard can render; this is the
    deterministic repair when generation invents aliases (e.g. ``gallery``).
    When ``speech_pipeline`` is asr/hybrid (or inferred), ensure a transcript panel;
    when audio_features_only, do not inject transcript.
    """
    from core.harness.execution.true_test_runtime import (
        RESULT_DASHBOARD_SECTION_TYPES,
        normalize_result_section_type,
    )

    meta: Dict[str, Any] = {"ok": True, "remapped": 0, "filled_defaults": 0}
    sp = str(speech_pipeline or "").strip().lower()
    if isinstance(page, dict):
        meta["speech_pipeline"] = sp or None
    if not isinstance(page, dict):
        return page, {**meta, "ok": False}
    stages = page.get("stages")
    if not isinstance(stages, list):
        return page, meta

    want_transcript = sp in ("asr", "hybrid")
    ban_transcript = sp in ("audio_features_only", "features_only", "none")

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if str(stage.get("component") or "") != "result_dashboard":
            continue
        cfg = stage.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
            stage["config"] = cfg
        sections = cfg.get("sections")
        if not isinstance(sections, list) or not sections:
            cfg["sections"] = [
                {"key": "metadata", "label": "元数据", "type": "key_value"},
                {"key": "summary", "label": "摘要", "type": "markdown"},
            ]
            meta["filled_defaults"] += 1
            sections = cfg["sections"]

        for sec in sections:
            if not isinstance(sec, dict):
                continue
            raw_t = str(sec.get("type") or "").strip()
            canon = normalize_result_section_type(raw_t)
            if not canon:
                key = str(sec.get("key") or "").lower()
                if any(x in key for x in ("frame", "image", "thumb", "keyframe")):
                    canon = "image_timeline"
                elif any(x in key for x in ("subtitle", "caption", "字幕", "transcript", "转写")):
                    canon = "subtitle_timeline"
                elif any(x in key for x in ("vad", "scene", "segment", "timeline")):
                    canon = "timeline"
                elif any(x in key for x in ("summary", "摘要", "markdown")):
                    canon = "markdown"
                elif any(x in key for x in ("tag", "label")):
                    canon = "tag_cloud"
                else:
                    canon = "key_value"
            if canon not in RESULT_DASHBOARD_SECTION_TYPES:
                canon = "key_value"
            if str(sec.get("type") or "") != canon:
                sec["type"] = canon
                meta["remapped"] += 1
            if not str(sec.get("key") or "").strip():
                sec["key"] = "field"
                meta["remapped"] += 1
            if not str(sec.get("label") or "").strip():
                sec["label"] = str(sec.get("key") or "字段")

        keys = {
            str(s.get("key") or "")
            for s in sections
            if isinstance(s, dict)
        }

        if ban_transcript and "transcript" in keys:
            sections[:] = [
                s
                for s in sections
                if not (isinstance(s, dict) and str(s.get("key") or "") == "transcript")
            ]
            cfg["sections"] = sections
            meta["removed_transcript"] = True
            keys.discard("transcript")

        # Default: content apps with speech/vad get transcript unless explicitly features-only
        need_tx = want_transcript or (
            (not ban_transcript)
            and (not sp)
            and ("speech" in keys or "vad" in keys)
        )
        if need_tx and "transcript" not in keys:
            insert_at = len(sections)
            for i, s in enumerate(sections):
                if isinstance(s, dict) and str(s.get("key") or "") in (
                    "speech",
                    "vad",
                    "subtitle",
                ):
                    insert_at = i + 1
            sections.insert(
                insert_at,
                {
                    "key": "transcript",
                    "label": "语音转写",
                    "type": "subtitle_timeline",
                },
            )
            cfg["sections"] = sections
            meta["filled_defaults"] += 1
            meta["added_transcript"] = True

    return page, meta


def repair_frontend_pages_with_prd(
    raw: str,
    agent_app_src: Any,
    prd_src: Any = None,
) -> Tuple[str, Dict[str, Any]]:
    """Skill inject + dual-component + wizard I/O + section-type repair."""
    from core.harness.execution.app_page_skill_inject import (
        extract_ui_bindings,
        repair_frontend_pages_raw,
    )

    raw = strip_reasoning_preamble(raw)
    repaired, meta = repair_frontend_pages_raw(raw, agent_app_src)
    page = _try_json_obj(repaired)
    if isinstance(page, dict):
        bindings = extract_ui_bindings(agent_app_src)
        page, dual_meta = ensure_dual_ingest_stages(page, ui_bindings=bindings)
        page, wiz_meta = ensure_wizard_stage_io(page, ui_bindings=bindings)
        page, canon_meta = canonicalize_app_page_media_skills(page)
        sp = _speech_pipeline_from_src(prd_src)
        page, sec_meta = ensure_result_dashboard_sections(page, speech_pipeline=sp)
        meta = {
            **meta,
            **dual_meta,
            "wizard_io": wiz_meta,
            "media_skill_canonical": canon_meta,
            "result_sections": sec_meta,
        }
        repaired = json.dumps(page, ensure_ascii=False, indent=2)
    return repaired, meta


def resolve_architecture_mode(stage: Any, state: Dict[str, Any], stages: Any = None) -> str:
    mode = str(getattr(stage, "architecture_mode", "") or "").strip()
    if mode:
        return mode
    mode = str((state or {}).get("architecture_mode") or "").strip()
    if mode:
        return mode
    for s in stages or []:
        m = str(getattr(s, "architecture_mode", "") or "").strip()
        if m:
            return m
    return ""


def extract_real_http_routes(*blobs: Any) -> List[str]:
    routes: List[str] = []
    seen = set()
    for blob in blobs:
        text = ""
        if isinstance(blob, dict):
            text = str(blob.get("raw_output") or blob.get("markdown") or "")
            if not text:
                text = json.dumps(blob, ensure_ascii=False)
        else:
            text = str(blob or "")
        if _AGENT_DEF_FILE.search(text) and not _REAL_ROUTE_DECO.search(text):
            continue
        for m in _REAL_ROUTE_DECO.finditer(text):
            path = m.group(1)
            if path not in seen:
                seen.add(path)
                routes.append(path)
    return routes


def sanitize_architecture_artifact(
    raw: str, *, architecture_mode: str
) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"ok": True}
    text = strip_reasoning_preamble(raw)
    mode = (architecture_mode or "").strip().lower()
    if mode != "agent":
        return text, meta

    obj = _try_json_obj(text)
    if not isinstance(obj, dict):
        return text, meta

    # Structural code-mode fields only — narrative security/quality chapters are allowed
    # on agent architecture documents.
    code_keys = (
        "components",
        "api_design",
        "database_schema",
        "deployment",
        "folder_structure",
    )
    has_code = any(obj.get(k) for k in code_keys)
    has_agent = bool(obj.get("agents") or obj.get("skill_routing"))

    if has_agent:
        stripped = [k for k in code_keys if k in obj]
        for k in stripped:
            obj.pop(k, None)
        if stripped:
            meta["stripped_code_fields"] = stripped
        obj["architecture_mode"] = "agent"
        obj.setdefault("document_type", "architecture_design")
        return json.dumps(obj, ensure_ascii=False, indent=2), meta

    if has_code:
        repaired = {
            "title": obj.get("title") or "untitled",
            "overview": str(obj.get("overview") or "")[:2000],
            "architecture_mode": "agent",
            "document_type": "architecture_design",
            "context": str(obj.get("overview") or "")[:1500],
            "goals": [],
            "non_goals": [],
            "design_decisions": [],
            "agents": [],
            "skill_routing": {},
            "data_flow": "user → agent → skill → reply",
            "error_handling": "clarify / degrade",
            "_sanitize": {
                "rejected_code_architecture": True,
                "message": "architecture_mode=agent: code-mode fields stripped",
            },
        }
        meta["rejected_code_architecture"] = True
        meta["ok"] = False
        return json.dumps(repaired, ensure_ascii=False, indent=2), meta

    obj.setdefault("architecture_mode", "agent")
    return json.dumps(obj, ensure_ascii=False, indent=2), meta


def _normalize_ui_bindings(man: Dict[str, Any]) -> bool:
    """Ensure ui_bindings values are skill_routing keys (not agent ids).

    If a value matches an agent name, remap to the first of that agent's skills
    that appears in skill_routing. Returns True if mutated.
    """
    routing = man.get("skill_routing") if isinstance(man.get("skill_routing"), dict) else {}
    ub = man.get("ui_bindings")
    if not isinstance(ub, dict) or not routing:
        return False
    agents_by_name: Dict[str, Dict[str, Any]] = {}
    for a in man.get("agents") or []:
        if isinstance(a, dict) and a.get("name"):
            agents_by_name[str(a["name"])] = a
    changed = False
    fixed: Dict[str, str] = {}
    for comp, val in list(ub.items()):
        skill = str(val or "").strip()
        if not skill:
            continue
        if skill in routing:
            fixed[str(comp)] = skill
            continue
        agent = agents_by_name.get(skill)
        if agent:
            candidates = [
                str(sk).strip()
                for sk in (agent.get("skills") or agent.get("required_skills") or [])
                if str(sk).strip() in routing
            ]
            used = set(fixed.values())
            # Prefer report-like skills when binding result_dashboard
            if str(comp) == "result_dashboard":
                ranked = sorted(
                    candidates,
                    key=lambda c: (0 if _is_report_like_skill(c) else 1, candidates.index(c)),
                )
                pick = next((c for c in ranked if c not in used), None) or (
                    ranked[0] if ranked else ""
                )
            else:
                pick = next((c for c in reversed(candidates) if c not in used), None) or (
                    candidates[-1] if candidates else ""
                )
            if pick:
                fixed[str(comp)] = pick
                changed = True
            continue
        changed = True  # drop invalid
    if dict(ub) != fixed:
        man["ui_bindings"] = fixed
        return True
    return False


def ensure_manifest_ui_binding_pair(
    raw: str,
    *,
    pair: Optional[Sequence[str]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """If quality_gate declares a component pair and one binding exists, fill the other.

    Also normalizes ui_bindings values to skill_routing keys (not agent ids).
    No PRD / domain text sniffing — only completes an incomplete declared pair.
    """
    meta: Dict[str, Any] = {"patched_ui_bindings": False, "normalized_ui_bindings": False}
    text = strip_reasoning_preamble(raw)
    comps = [str(c).strip() for c in (pair or ()) if str(c).strip()]
    # Allow normalize-only when pair incomplete
    if len(comps) != 2:
        comps = []
    primary = comps[0] if comps else ""
    secondary = comps[1] if comps else ""

    parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", text)
    if len(parts) == 1:
        return text, meta

    buf: List[str] = [parts[0]]
    i = 1
    patched = False
    normalized = False
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        if "agent_manifest.json" not in header:
            buf.append(header + "\n" + body)
            continue
        body_clean = body.strip()
        fence = False
        rest = ""
        if body_clean.startswith("```"):
            fence = True
            body_clean = re.sub(r"^```(?:json)?\s*", "", body_clean)
            body_clean = re.sub(r"\s*```\s*$", "", body_clean)
        try:
            man = json.loads(body_clean)
        except json.JSONDecodeError:
            start, end = body_clean.find("{"), body_clean.rfind("}")
            if 0 <= start < end:
                try:
                    man = json.loads(body_clean[start : end + 1])
                    rest = body_clean[end + 1 :]
                except json.JSONDecodeError:
                    buf.append(header + "\n" + body)
                    continue
            else:
                buf.append(header + "\n" + body)
                continue
        if not isinstance(man, dict):
            buf.append(header + "\n" + body)
            continue
        if _normalize_ui_bindings(man):
            normalized = True
        ub = man.get("ui_bindings")
        if not isinstance(ub, dict):
            ub = {}
        if primary and secondary:
            left = ub.get(primary)
            right = ub.get(secondary)
            if left and not right:
                ub[secondary] = left
                patched = True
            elif right and not left:
                ub[primary] = right
                patched = True
            if patched:
                man["ui_bindings"] = ub
        dumped = json.dumps(man, ensure_ascii=False, indent=2)
        if fence:
            dumped = "```json\n" + dumped + "\n```"
        buf.append(header + "\n" + dumped + "\n" + (rest or ""))
    meta["patched_ui_bindings"] = patched
    meta["normalized_ui_bindings"] = normalized
    return "".join(buf), meta


def ensure_manifest_dual_ui_bindings(
    raw: str, *, prd_src: Any = None, pair: Optional[Sequence[str]] = None  # noqa: ARG001
) -> Tuple[str, Dict[str, Any]]:
    """Legacy name — completes file_upload/data_form pair when one side exists."""
    return ensure_manifest_ui_binding_pair(
        raw, pair=pair or ("file_upload", "data_form")
    )


_REPORT_SKILL_TOKENS = frozenset(
    {"report", "export", "summar", "dashboard", "aggregate", "presentation", "result"}
)
_DEFAULT_REPORT_SKILL = "report_json_export"


def _is_report_like_skill(name: str) -> bool:
    toks = set(re.findall(r"[a-z0-9]+", str(name or "").lower()))
    return bool(toks & _REPORT_SKILL_TOKENS)


def _pick_orchestrator_agent(man: Dict[str, Any]) -> str:
    agents = man.get("agents") if isinstance(man.get("agents"), list) else []
    for a in agents:
        if isinstance(a, dict) and str(a.get("role") or "").lower() == "orchestrator":
            return str(a.get("name") or "")
    for a in agents:
        if isinstance(a, dict) and a.get("name"):
            return str(a["name"])
    return "orchestrator"


def _report_skill_md(app_name: str, skill_name: str) -> str:
    path = f"~/.aiplat/apps/{app_name}/skills/{skill_name}/SKILL.md"
    body = _load_factory_sanitize_skill(
        "report_skill_generic.SKILL.md",
        app_name=app_name,
        skill_name=skill_name,
    )
    if body is None:
        # Minimal fallback when seed file is absent (dev / partial checkout).
        _log.warning("factory_sanitize seed missing: report_skill_generic.SKILL.md")
        body = (
            f"---\nname: {skill_name}\n"
            "description: Aggregate processor outputs into a unified report.\n"
            "execution_type: prompt\nversion: 1.0.0\nstatus: enabled\n"
            f"effects:\n  - type: write\n"
            f"    resources: [filesystem:~/.aiplat/apps/{app_name}/reports]\n"
            "input_schema:\n  task_id:\n    type: string\n    required: true\n"
            "output_schema:\n  status:\n    type: string\n    required: true\n"
            "  report_json:\n    type: object\n    required: true\n"
            "  report_id:\n    type: string\n    required: true\n"
            "---\n# Report export\n"
        )
    return f"## FILE: {path}\n{body}\n"



# --- Platform catalog Skill contracts (handler SoT; LLM must not redefine) ---

_DOWNLOADER_OUT_KEYS = (
    "media_ref",
    "video_path",
    "segments",
    "duration_seconds",
    "duration_sec",
    "download_status",
)
_REPORT_OUT_KEYS = ("report", "report_json", "timeline", "report_path")
_DOWNLOADER_IMPORT_ONLY_HINTS = (
    "创建分析任务",
    "返回 task_id 与 PENDING",
    "status=PENDING",
    "不创建任务",
    "写入审计日志",
)
_DOWNLOADER_MUST_HINTS = ("下载", "分段", "media_ref", "segments", "duration")
_REPORT_PROGRESS_ONLY_HINTS = (
    "进度查询",
    "询问任务进度",
    "current_stage",
    "block_status",
    "处理到哪一步",
)
_REPORT_MUST_HINTS = ("结构化报告", "时间轴", "timeline", "report_path", "汇聚")


def _schema_has_any(body: str, keys: tuple) -> bool:
    b = body or ""
    for k in keys:
        if re.search(rf"(?m)^(?:\s{{2}}){k}:\s*$", b) or re.search(
            rf"(?m)^\s+-\s*name:\s*{k}\s*$", b
        ):
            return True
        # output_schema nested style: `  media_ref:` under output_schema
        if re.search(rf"(?ms)^output_schema:.*?^\s{{2}}{k}:", b):
            return True
    return False


def _schema_input_required(body: str, field: str) -> bool:
    """True when input_schema marks ``field`` as required: true."""
    b = body or ""
    # Block under input_schema until next top-level key
    m = re.search(r"(?ms)^input_schema:\n(.*?)(?=^[a-z_]+:|\Z)", b)
    block = m.group(1) if m else b
    fm = re.search(
        rf"(?ms)^\s{{2}}{re.escape(field)}:\n(.*?)(?=^\s{{2}}[a-z_]+:|\Z)",
        block,
    )
    if not fm:
        return False
    return bool(re.search(r"(?m)^\s{4}required:\s*true\s*$", fm.group(1)))


def _downloader_contract_ok(body: str) -> bool:
    has_media = _schema_has_any(body, ("media_ref", "video_path", "file_path"))
    has_dur = _schema_has_any(body, ("duration_seconds", "duration_sec", "duration"))
    has_seg = _schema_has_any(body, ("segments",))
    has_status = _schema_has_any(body, ("download_status", "status"))
    text = body or ""
    import_only = sum(1 for h in _DOWNLOADER_IMPORT_ONLY_HINTS if h in text) >= 2
    must = sum(1 for h in _DOWNLOADER_MUST_HINTS if h.lower() in text.lower() or h in text)
    if import_only and must < 2:
        return False
    # Path0 handler auto-creates task_id — must not require it for ingress UI
    if _schema_input_required(body, "task_id"):
        return False
    return bool(has_media and has_dur and has_seg and has_status)


def _report_contract_ok(body: str) -> bool:
    has_report = _schema_has_any(body, ("report", "report_json"))
    has_tl = _schema_has_any(body, ("timeline",))
    has_path = _schema_has_any(body, ("report_path",))
    text = body or ""
    progress_only = sum(1 for h in _REPORT_PROGRESS_ONLY_HINTS if h in text) >= 2
    must = sum(1 for h in _REPORT_MUST_HINTS if h.lower() in text.lower() or h in text)
    if progress_only and must < 2:
        return False
    # Handler can create/reuse task_id from media_ref
    if _schema_input_required(body, "task_id") and not _schema_has_any(
        body, ("media_ref", "video_path", "file_path")
    ):
        # task_id-only ingress is OK for poll; still require report outputs
        pass
    if _schema_input_required(body, "tenant_id"):
        return False
    return bool(has_report and has_tl and has_path)


def _frame_contract_ok(body: str) -> bool:
    if _schema_input_required(body, "task_id"):
        return False
    if _schema_input_required(body, "duration_seconds"):
        return False
    if _schema_input_required(body, "tenant_id"):
        return False
    # Must mention keyframes / captions outputs
    return _schema_has_any(body, ("keyframes", "keyframe_count", "captions", "descriptions"))


def _speech_contract_ok(body: str) -> bool:
    if _schema_input_required(body, "task_id"):
        return False
    if _schema_input_required(body, "duration_seconds"):
        return False
    if _schema_input_required(body, "tenant_id"):
        return False
    return _schema_has_any(body, ("transcript", "transcript_text", "transcript_segments"))


def _canonical_frame_analyzer_skill_md(app_name: str) -> str:
    return load_canonical_media_skill_md("frame_analyzer", app_name)


def _canonical_speech_analyzer_skill_md(app_name: str) -> str:
    return load_canonical_media_skill_md("speech_analyzer", app_name)


def _canonical_video_downloader_skill_md(app_name: str) -> str:
    return load_canonical_media_skill_md("video_downloader", app_name)


def _canonical_report_json_export_skill_md(app_name: str) -> str:
    return load_canonical_media_skill_md("report_json_export", app_name)


def ensure_platform_media_skill_contracts(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Rewrite catalog SKILL.md bodies that violate platform handler contracts.

    Blocks LLM redefining ``video_downloader`` as import-only or
    ``report_json_export`` as progress-only.
    """
    meta: Dict[str, Any] = {"ok": True, "rewritten": [], "unchanged": 0}
    text = _repair_glued_file_headers(strip_reasoning_preamble(raw))
    parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", text)
    if len(parts) == 1:
        return text, {**meta, "ok": False, "reason": "no_file_blocks"}

    # app_name from first skills path or manifest
    app_name = "app"
    m_app = re.search(r"apps/([^/]+)/", text)
    if m_app:
        app_name = m_app.group(1)

    out_parts: List[str] = [parts[0]]
    i = 1
    changed = False
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        m_skill = re.search(r"skills/([^/]+)/SKILL\.md", header)
        if not m_skill:
            out_parts.append(header + "\n" + body)
            continue
        stem = m_skill.group(1)
        try:
            from core.harness.media_skill_handlers import resolve_media_handler_name

            canon = resolve_media_handler_name(stem) or stem
        except Exception:
            canon = stem
        new_body = body
        if canon == "video_downloader" and not _downloader_contract_ok(body):
            new_body = _canonical_video_downloader_skill_md(app_name)
            if not new_body.endswith("\n"):
                new_body += "\n"
            meta["rewritten"].append("video_downloader")
            changed = True
            # ensure path stem is canonical
            header = re.sub(
                r"skills/[^/]+/SKILL\.md",
                "skills/video_downloader/SKILL.md",
                header,
            )
        elif canon == "report_json_export" and not _report_contract_ok(body):
            new_body = _canonical_report_json_export_skill_md(app_name)
            if not new_body.endswith("\n"):
                new_body += "\n"
            meta["rewritten"].append("report_json_export")
            changed = True
            header = re.sub(
                r"skills/[^/]+/SKILL\.md",
                "skills/report_json_export/SKILL.md",
                header,
            )
        elif canon == "frame_analyzer" and not _frame_contract_ok(body):
            new_body = _canonical_frame_analyzer_skill_md(app_name)
            if not new_body.endswith("\n"):
                new_body += "\n"
            meta["rewritten"].append("frame_analyzer")
            changed = True
            header = re.sub(
                r"skills/[^/]+/SKILL\.md",
                "skills/frame_analyzer/SKILL.md",
                header,
            )
        elif canon == "speech_analyzer" and not _speech_contract_ok(body):
            new_body = _canonical_speech_analyzer_skill_md(app_name)
            if not new_body.endswith("\n"):
                new_body += "\n"
            meta["rewritten"].append("speech_analyzer")
            changed = True
            header = re.sub(
                r"skills/[^/]+/SKILL\.md",
                "skills/speech_analyzer/SKILL.md",
                header,
            )
        out_parts.append(header + "\n" + new_body)

    if not changed:
        meta["unchanged"] = 1
        return text, meta
    return "".join(out_parts), meta


def _media_skill_canonical_target(name: str) -> Optional[str]:
    """Return canonical catalog name when ``name`` is an alias or inventable media skill."""
    n = str(name or "").strip()
    if not n:
        return None
    try:
        from core.harness.media_skill_handlers import (
            resolve_media_handler_name,
            suggest_platform_media_skill,
        )
    except Exception:
        return None
    canon = resolve_media_handler_name(n)
    if canon and canon != n:
        return canon
    sug = suggest_platform_media_skill(n)
    return sug if sug and sug != n else None


def _apply_media_skill_remap_to_manifest(
    man: Dict[str, Any], remap: Dict[str, str]
) -> None:
    """In-place rewrite skill_routing / ui_bindings / agents[*].skills via remap."""
    routing = man.get("skill_routing")
    if isinstance(routing, dict):
        new_routing: Dict[str, Any] = {}
        for k, v in routing.items():
            nk = remap.get(str(k), str(k))
            if nk in new_routing and nk != str(k):
                continue
            new_routing[nk] = v
        man["skill_routing"] = new_routing
    ub = man.get("ui_bindings")
    if isinstance(ub, dict):
        for bk, bv in list(ub.items()):
            ub[bk] = remap.get(str(bv), str(bv))
    for a in man.get("agents") or []:
        if not isinstance(a, dict):
            continue
        skills = a.get("skills")
        if isinstance(skills, list):
            seen: set = set()
            new_skills: List[str] = []
            for sk in skills:
                ns = remap.get(str(sk), str(sk))
                if ns not in seen:
                    seen.add(ns)
                    new_skills.append(ns)
            a["skills"] = new_skills


def normalize_media_skill_names(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Remap media skill aliases + invented names onto the platform catalog.

    Promotes aliases (``report_assembly`` → ``report_json_export``) and invented
    names via ``suggest_platform_media_skill``. Updates skill_routing /
    ui_bindings / agents[*].skills and ``## FILE: …/skills/<name>/`` headers.
    Also accepts plain JSON agent_manifest (no FILE blocks).
    """
    meta: Dict[str, Any] = {"ok": True, "remapped": {}, "unchanged": 0}
    text = _repair_glued_file_headers(strip_reasoning_preamble(raw))
    try:
        from core.harness.media_skill_handlers import (  # noqa: F401 — catalog probe
            HANDLERS,
        )
    except Exception as exc:  # noqa: BLE001 — optional infra
        return text, {**meta, "ok": False, "reason": f"catalog_unavailable:{exc}"}

    parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", text)
    if len(parts) == 1:
        # Plain JSON agent_manifest (deploy / output without FILE wrappers)
        obj, _rest = _parse_json_obj_rest(text)
        if not isinstance(obj, dict):
            return text, {**meta, "ok": False, "reason": "no_file_blocks"}
        remap: Dict[str, str] = {}
        routing = obj.get("skill_routing") if isinstance(obj.get("skill_routing"), dict) else {}
        for k in list(routing.keys()):
            tgt = _media_skill_canonical_target(str(k))
            if tgt:
                remap[str(k)] = tgt
        ub = obj.get("ui_bindings") if isinstance(obj.get("ui_bindings"), dict) else {}
        for v in list(ub.values()):
            tgt = _media_skill_canonical_target(str(v))
            if tgt:
                remap[str(v)] = tgt
        for a in obj.get("agents") or []:
            if not isinstance(a, dict):
                continue
            for sk in list(a.get("skills") or []):
                tgt = _media_skill_canonical_target(str(sk))
                if tgt:
                    remap[str(sk)] = tgt
        if not remap:
            meta["unchanged"] = 1
            return text, meta
        _apply_media_skill_remap_to_manifest(obj, remap)
        meta["remapped"] = dict(remap)
        return json.dumps(obj, ensure_ascii=False, indent=2), meta

    remap = {}

    def _target(name: str) -> Optional[str]:
        return _media_skill_canonical_target(name)

    # First pass: discover remaps from skill_routing / FILE skill dirs
    i = 1
    man: Optional[Dict[str, Any]] = None
    man_header = ""
    man_fence = False
    man_rest = ""
    other_blocks: List[Tuple[str, str]] = []

    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        m_skill = re.search(r"skills/([^/]+)/SKILL\.md", header)
        if m_skill:
            old = m_skill.group(1)
            tgt = _target(old)
            if tgt:
                remap[old] = tgt
        if "agent_manifest.json" in header:
            man_header = header
            body_clean = body.strip()
            if body_clean.startswith("```"):
                man_fence = True
            obj, rest = _parse_json_obj_rest(body_clean)
            if isinstance(obj, dict):
                man = obj
                man_rest = rest or ""
                routing = man.get("skill_routing") if isinstance(man.get("skill_routing"), dict) else {}
                for k in list(routing.keys()):
                    tgt = _target(str(k))
                    if tgt:
                        remap[str(k)] = tgt
                ub = man.get("ui_bindings") if isinstance(man.get("ui_bindings"), dict) else {}
                for v in list(ub.values()):
                    tgt = _target(str(v))
                    if tgt:
                        remap[str(v)] = tgt
                for a in man.get("agents") or []:
                    if not isinstance(a, dict):
                        continue
                    for sk in list(a.get("skills") or []):
                        tgt = _target(str(sk))
                        if tgt:
                            remap[str(sk)] = tgt
            else:
                other_blocks.append((header, body))
        else:
            other_blocks.append((header, body))

    # AGENT.md: only rewrite invent names under required_skills: (not free-text / error codes)
    for _h, b in other_blocks:
        if "AGENT.md" not in _h:
            continue
        block = re.search(
            r"(?ms)^required_skills:\s*\n((?:[ \t]+-[ \t]+[^\n]+\n?)+)",
            b,
        )
        if not block:
            continue
        for m in re.finditer(r"(?m)^[ \t]+-[ \t]+([a-zA-Z0-9_\-]+)[ \t]*$", block.group(1)):
            sk = m.group(1)
            tgt = _target(sk)
            if tgt:
                remap[sk] = tgt

    if not remap:
        meta["unchanged"] = 1
        return text, meta

    meta["remapped"] = dict(remap)

    # Apply remaps to manifest
    if isinstance(man, dict):
        _apply_media_skill_remap_to_manifest(man, remap)

    out_parts: List[str] = [parts[0]]
    if man_header and isinstance(man, dict):
        dumped = json.dumps(man, ensure_ascii=False, indent=2)
        if man_fence:
            dumped = "```json\n" + dumped + "\n```"
        out_parts.append(man_header + "\n" + dumped + "\n" + (man_rest or ""))
    for h, b in other_blocks:
        nh = h
        for old, new in remap.items():
            nh = nh.replace(f"skills/{old}/", f"skills/{new}/")
        nb = _rewrite_skill_refs_in_markdown(b, remap)
        out_parts.append(nh + "\n" + nb)
    return "".join(out_parts), meta


def _rewrite_skill_refs_in_markdown(body: str, remap: Dict[str, str]) -> str:
    """Rewrite frontmatter name, YAML list items, and `skill` backticks via remap.

    Only applies keys already in ``remap`` (discovered from routing / FILE / required_skills).
    """
    nb = body or ""
    for old, new in remap.items():
        if not old or old == new:
            continue
        # Avoid rewriting ALL_CAPS error codes accidentally added to remap
        if old.isupper() and "_" in old:
            continue
        nb = re.sub(
            rf"(?m)^(name:\s*){re.escape(old)}\s*$",
            rf"\g<1>{new}",
            nb,
        )
        nb = re.sub(
            rf"(?m)^(\s+-\s+){re.escape(old)}\s*$",
            rf"\g<1>{new}",
            nb,
        )
        nb = re.sub(rf"`{re.escape(old)}`", f"`{new}`", nb)
    return _dedupe_required_skills_yaml(nb)


def _dedupe_required_skills_yaml(body: str) -> str:
    """Drop duplicate entries under ``required_skills:`` after invent→canonical remap."""

    def _repl(m: re.Match) -> str:
        seen: set = set()
        lines_out: List[str] = []
        for line in m.group(1).splitlines():
            mm = re.match(r"^([ \t]+-[ \t]+)([a-zA-Z0-9_\-]+)[ \t]*$", line)
            if mm:
                sk = mm.group(2)
                if sk in seen:
                    continue
                seen.add(sk)
            lines_out.append(line)
        block = "\n".join(lines_out)
        if block and not block.endswith("\n"):
            block += "\n"
        return "required_skills:\n" + block

    return re.sub(
        r"(?ms)^required_skills:\s*\n((?:[ \t]+-[ \t]+[^\n]+\n?)+)",
        _repl,
        body or "",
    )


_QA_BODY_HINTS = (
    "问答",
    "citation",
    "citations",
    "video_qa",
    "引用时间戳",
    "timestamp_cite",
    "多模态问答",
    "answer_with_cite",
)
_DOWNLOAD_BODY_HINTS = (
    "下载",
    "download",
    "ssrf",
    "video_url",
    "upload_file",
    "http/https",
    "仅支持 HTTP",
    "file_validate",
)


def _skill_frontmatter_name(body: str) -> Optional[str]:
    m = re.search(r"(?m)^name:\s*([^\s#]+)\s*$", body or "")
    return m.group(1).strip() if m else None


def _set_skill_frontmatter_name(body: str, name: str) -> str:
    if re.search(r"(?m)^name:\s*", body or ""):
        return re.sub(
            r"(?m)^(name:\s*)[^\s#]+\s*$",
            rf"\g<1>{name}",
            body,
            count=1,
        )
    # Insert after opening --- if present
    if (body or "").lstrip().startswith("---"):
        return re.sub(
            r"(?m)^(---\s*\n)",
            rf"\g<1>name: {name}\n",
            body,
            count=1,
        )
    return f"---\nname: {name}\n---\n{body}"


def _body_score(body: str, hints: tuple) -> int:
    b = (body or "").lower()
    raw = body or ""
    return sum(1 for h in hints if h.lower() in b or h in raw)


def _looks_like_mislabeled_video_qa(stem: str, body: str) -> bool:
    """True when FILE is under video_downloader but SOP is Q&A, not ingest."""
    if stem != "video_downloader":
        return False
    qa = _body_score(body, _QA_BODY_HINTS)
    dl = _body_score(body, _DOWNLOAD_BODY_HINTS)
    return qa >= 2 and qa > dl


_SPEECH_ASR_HINTS = (
    "转写",
    "asr",
    "transcript",
    "transcribe",
    "whisper",
    "语音识别",
)
_SPEECH_ACOUSTIC_HINTS = (
    "声学",
    "acoustic",
    "vad",
    "语种",
    "说话人",
    "情绪",
    "speaker",
    "emotion",
    "energy",
)


def _merge_skill_bodies(stem: str, body_a: str, body_b: str) -> str:
    """Prefer richer body; for speech_analyzer merge ASR + acoustic scopes."""
    if not body_a:
        return body_b
    if not body_b:
        return body_a
    if stem != "speech_analyzer":
        return body_a if len(body_a) >= len(body_b) else body_b

    def _has(body: str, hints: tuple) -> bool:
        return _body_score(body, hints) > 0

    a_asr, b_asr = _has(body_a, _SPEECH_ASR_HINTS), _has(body_b, _SPEECH_ASR_HINTS)
    a_ac, b_ac = _has(body_a, _SPEECH_ACOUSTIC_HINTS), _has(body_b, _SPEECH_ACOUSTIC_HINTS)
    # Complementary pair → keep ASR-leaning as base, append acoustic desc clause
    if (a_asr and b_ac and not a_ac) or (b_asr and a_ac and not b_ac):
        primary = body_a if a_asr else body_b
        secondary = body_b if a_asr else body_a
        if _has(primary, _SPEECH_ACOUSTIC_HINTS):
            return primary
        sec_desc = ""
        m = re.search(r"(?m)^description:\s*(.+)$", secondary)
        if m:
            sec_desc = m.group(1).strip()
        clause = "同时输出语种/说话人/情绪等声学标签。"
        if sec_desc and (
            "语种" in sec_desc
            or "声学" in sec_desc
            or "acoustic" in sec_desc.lower()
        ):
            clause = sec_desc
        if re.search(r"(?m)^description:\s*", primary):

            def _append_desc(m: re.Match) -> str:
                base = m.group(2).rstrip("。.;；")
                extra = clause.lstrip("；;")
                end = "" if extra.endswith(("。", ".", "；", ";")) else "。"
                return m.group(1) + base + "；" + extra + end

            return re.sub(
                r"(?m)^(description:\s*)(.+)$",
                _append_desc,
                primary,
                count=1,
            )
        return primary + "\n\n## Acoustic scope\n" + clause + "\n"
    # Same role or both dual → longer
    return body_a if len(body_a) >= len(body_b) else body_b


_NON_PLATFORM_LIFECYCLE_SKILLS = frozenset(
    {
        "task_lifecycle",
        "task_manager",
        "task_store",
        "task_status",
        "task_tracker",
        "audit_logger",
        "lifecycle_manager",
    }
)


def ensure_agent_app_skill_consistency(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Triple consistency: skill_routing key ≡ skills/<stem>/ ≡ frontmatter name.

    - Rename Q&A body mis-filed as ``video_downloader`` → ``video_qa`` (prompt-only)
    - Align frontmatter ``name:`` with directory stem
    - Deduplicate FILE blocks that share the same ``skills/<stem>/SKILL.md`` (merge speech)
    - Drop duplicate frontmatter names across stems by merging onto first stem
    - Drop invented lifecycle skills (``task_lifecycle`` etc.) — Path0 handlers own task_id
    """
    meta: Dict[str, Any] = {
        "ok": True,
        "renamed": {},
        "frontmatter_fixed": [],
        "deduped_stems": [],
        "routing_aligned": False,
        "merged_speech": False,
        "dropped_lifecycle_skills": [],
    }
    text = _repair_glued_file_headers(strip_reasoning_preamble(raw))
    parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", text)
    if len(parts) == 1:
        return text, {**meta, "ok": False, "reason": "no_file_blocks"}

    prefix = parts[0]
    man: Optional[Dict[str, Any]] = None
    man_header = ""
    man_fence = False
    man_rest = ""
    skill_blocks: List[Tuple[str, str, str]] = []  # header, body, stem
    other_blocks: List[Tuple[str, str]] = []
    remap: Dict[str, str] = {}
    qa_from_downloader = False

    i = 1
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        m_skill = re.search(r"skills/([^/]+)/SKILL\.md", header)
        if m_skill:
            stem = m_skill.group(1)
            if stem in _NON_PLATFORM_LIFECYCLE_SKILLS:
                # Drop invented lifecycle skills — progress uses report_json_export;
                # task_id is created by video_downloader / media handlers.
                meta["dropped_lifecycle_skills"].append(stem)
                remap[stem] = "report_json_export"
                continue
            if _looks_like_mislabeled_video_qa(stem, body):
                # Path rename only — do NOT remap video_downloader globally yet
                # (a real ingest skill may still exist under the same stem).
                stem = "video_qa"
                header = re.sub(
                    r"skills/[^/]+/SKILL\.md",
                    "skills/video_qa/SKILL.md",
                    header,
                )
                body = _set_skill_frontmatter_name(body, "video_qa")
                meta["renamed"]["video_downloader→video_qa"] = True
                qa_from_downloader = True
            skill_blocks.append((header, body, stem))
            continue
        if "agent_manifest.json" in header:
            man_header = header
            body_clean = body.strip()
            if body_clean.startswith("```"):
                man_fence = True
            obj, rest = _parse_json_obj_rest(body_clean)
            if isinstance(obj, dict):
                man = obj
                man_rest = rest or ""
            else:
                other_blocks.append((header, body))
        else:
            other_blocks.append((header, body))

    # Align frontmatter name ↔ stem; collect by stem (dedupe / merge)
    by_stem: Dict[str, Tuple[str, str]] = {}
    name_owner: Dict[str, str] = {}
    for header, body, stem in skill_blocks:
        fm = _skill_frontmatter_name(body)
        if fm and fm != stem:
            # Prefer stem (path is SoT after media normalize); fix frontmatter
            body = _set_skill_frontmatter_name(body, stem)
            meta["frontmatter_fixed"].append({"stem": stem, "was": fm})
            fm = stem
        elif not fm:
            body = _set_skill_frontmatter_name(body, stem)
            meta["frontmatter_fixed"].append({"stem": stem, "was": None})
            fm = stem
        # Duplicate frontmatter name on a different stem → fold into first owner
        owner = name_owner.get(fm)
        if owner and owner != stem:
            remap[stem] = owner
            meta["deduped_stems"].append({"dropped": stem, "kept": owner, "name": fm})
            continue
        name_owner[fm] = stem
        prev = by_stem.get(stem)
        header = re.sub(
            r"skills/[^/]+/SKILL\.md",
            f"skills/{stem}/SKILL.md",
            header,
        )
        if prev is None:
            by_stem[stem] = (header, body)
        else:
            merged = _merge_skill_bodies(stem, prev[1], body)
            if stem == "speech_analyzer" and merged != prev[1] and merged != body:
                meta["merged_speech"] = True
            meta["deduped_stems"].append({"dropped_dup_path": stem})
            by_stem[stem] = (header, merged)

    # Only remap video_downloader→video_qa when no real downloader FILE remains
    if qa_from_downloader and "video_downloader" not in by_stem:
        remap["video_downloader"] = "video_qa"

    if isinstance(man, dict) and remap:
        _apply_media_skill_remap_to_manifest(man, remap)
        meta["routing_aligned"] = True

    # Align routing keys that still point at dropped stems / ensure keys ⊆ file stems ∪ prompt-only
    if isinstance(man, dict):
        routing = man.get("skill_routing")
        if isinstance(routing, dict):
            file_stems = set(by_stem.keys())
            new_routing: Dict[str, Any] = {}
            for k, v in routing.items():
                ks = str(k)
                if ks in remap:
                    ks = remap[ks]
                # Keep prompt-only and file stems; drop orphans that duplicate remapped
                if ks in new_routing and ks != str(k):
                    continue
                new_routing[ks] = v
            # Ensure every skill file has a routing entry (bind to first agent if missing)
            agents = man.get("agents") if isinstance(man.get("agents"), list) else []
            default_agent = None
            if agents and isinstance(agents[0], dict):
                default_agent = agents[0].get("name") or agents[0].get("id")
            for stem in file_stems:
                if stem not in new_routing and default_agent:
                    new_routing[stem] = default_agent
                    meta["routing_aligned"] = True
            # skill_routing is SoT for ownership — one skill → one agent
            owner_of = {str(k): str(v) for k, v in new_routing.items()}
            try:
                from core.harness.media_skill_handlers import is_prompt_only_skill_name
            except Exception:  # noqa: BLE001

                def is_prompt_only_skill_name(_n: str) -> bool:  # type: ignore
                    return False

            for a in agents:
                if not isinstance(a, dict):
                    continue
                aname = str(a.get("name") or a.get("id") or "")
                skills = a.get("skills")
                if not isinstance(skills, list):
                    continue
                kept: List[str] = []
                seen: set = set()
                for sk in skills:
                    sks = str(sk)
                    # Drop invented names already remapped away / without FILE
                    if sks not in file_stems and not is_prompt_only_skill_name(sks):
                        if sks in remap:
                            sks = remap[sks]
                        else:
                            meta["routing_aligned"] = True
                            continue
                    owner = owner_of.get(sks)
                    if owner and aname and owner != aname:
                        meta["routing_aligned"] = True
                        continue
                    if sks not in seen:
                        seen.add(sks)
                        kept.append(sks)
                # Ensure owner agent lists every skill routed to it
                for sks, owner in owner_of.items():
                    if owner == aname and sks not in seen and (
                        sks in file_stems or is_prompt_only_skill_name(sks)
                    ):
                        kept.append(sks)
                        seen.add(sks)
                        meta["routing_aligned"] = True
                a["skills"] = kept
            # Drop worker agents left with zero skills (e.g. transcription after ownership fold)
            kept_agents: List[Any] = []
            dropped_agents: List[str] = []
            for a in agents:
                if not isinstance(a, dict):
                    kept_agents.append(a)
                    continue
                skills = a.get("skills")
                role = str(a.get("role") or "").lower()
                aname = str(a.get("name") or a.get("id") or "")
                if (
                    isinstance(skills, list)
                    and len(skills) == 0
                    and role in ("worker", "specialist", "")
                    and aname
                    and aname not in set(owner_of.values())
                ):
                    dropped_agents.append(aname)
                    meta["routing_aligned"] = True
                    continue
                kept_agents.append(a)
            if dropped_agents:
                meta["dropped_empty_agents"] = dropped_agents
                man["agents"] = kept_agents
                agents = kept_agents
            # progress_poller on ingest-only → report_json_export when present
            ub = man.get("ui_bindings")
            if isinstance(ub, dict) and "report_json_export" in file_stems:
                prog = str(ub.get("progress_poller") or "")
                if prog in (
                    "video_downloader",
                    "video_import",
                    "video_ingest",
                    "media_import",
                    "task_lifecycle",
                    "task_manager",
                    "task_store",
                    "task_tracker",
                ) or (
                    prog
                    and prog in file_stems
                    and prog
                    not in (
                        "report_json_export",
                        "frame_analyzer",
                        "speech_analyzer",
                        "subtitle_extractor",
                    )
                    and "download" in prog
                ):
                    ub["progress_poller"] = "report_json_export"
                    meta["routing_aligned"] = True
            # Ensure agents[*].skills include video_qa for its routing owner
            if qa_from_downloader and "video_qa" in file_stems:
                for a in agents:
                    if not isinstance(a, dict):
                        continue
                    skills = a.get("skills")
                    owner = owner_of.get("video_qa")
                    aname = str(a.get("name") or a.get("id") or "")
                    if (
                        isinstance(skills, list)
                        and owner == aname
                        and "video_qa" not in skills
                    ):
                        skills.append("video_qa")
                        meta["routing_aligned"] = True
            man["skill_routing"] = new_routing

    changed = bool(
        meta["renamed"]
        or meta["frontmatter_fixed"]
        or meta["deduped_stems"]
        or meta.get("merged_speech")
        or meta.get("dropped_lifecycle_skills")
        or remap
    )
    if not changed and not meta.get("routing_aligned"):
        meta["unchanged"] = 1
        return text, meta

    # Drop glued agent FILE bodies that were stuck after manifest (now in man_rest)
    # — if man_rest still contains ## FILE markers, peel them into other_blocks
    if man_rest and re.search(r"(?m)^#{2,4}\s*FILE:\s*", man_rest):
        rest_parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", man_rest)
        man_rest = rest_parts[0]
        j = 1
        while j < len(rest_parts):
            other_blocks.append(
                (rest_parts[j], rest_parts[j + 1] if j + 1 < len(rest_parts) else "")
            )
            j += 2

    out_parts: List[str] = [prefix]
    if man_header and isinstance(man, dict):
        dumped = json.dumps(man, ensure_ascii=False, indent=2)
        if man_fence:
            dumped = "```json\n" + dumped + "\n```"
        trailing = (man_rest or "").strip()
        out_parts.append(
            man_header + "\n" + dumped + ("\n" + trailing + "\n" if trailing else "\n")
        )
    for h, b in other_blocks:
        # Drop AGENT.md for agents removed as empty
        dropped = set(meta.get("dropped_empty_agents") or [])
        if dropped:
            m_ag = re.search(r"agents/([^/]+)/AGENT\.md", h)
            if m_ag and m_ag.group(1) in dropped:
                continue
        out_parts.append(h + "\n" + b)
    for stem in sorted(by_stem.keys()):
        h, b = by_stem[stem]
        out_parts.append(h + "\n" + b)
    return "".join(out_parts), meta


def ensure_result_dashboard_skill(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Ensure a report/export skill exists and ui_bindings.result_dashboard points to it.

    Config-driven sanitizer (platform component ``result_dashboard``), no product names.
    """
    meta: Dict[str, Any] = {"ok": True, "added_skill": False, "bound": False}
    text = strip_reasoning_preamble(raw)
    parts = re.split(r"(?m)^(#{2,4}\s*FILE:\s*[^\n]+)\n", text)
    if len(parts) == 1:
        return text, {**meta, "ok": False, "reason": "no_file_blocks"}

    buf: List[str] = [parts[0]]
    i = 1
    man: Optional[Dict[str, Any]] = None
    man_header = ""
    man_fence = False
    man_rest = ""
    other_blocks: List[Tuple[str, str]] = []
    existing_skill_files: set = set()

    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        i += 2
        if "agent_manifest.json" in header:
            man_header = header
            body_clean = body.strip()
            if body_clean.startswith("```"):
                man_fence = True
                body_clean = re.sub(r"^```(?:json)?\s*", "", body_clean)
                body_clean = re.sub(r"\s*```\s*$", "", body_clean)
            try:
                obj = json.loads(body_clean)
            except json.JSONDecodeError:
                start, end = body_clean.find("{"), body_clean.rfind("}")
                if 0 <= start < end:
                    try:
                        obj = json.loads(body_clean[start : end + 1])
                        man_rest = body_clean[end + 1 :]
                    except json.JSONDecodeError:
                        other_blocks.append((header, body))
                        continue
                else:
                    other_blocks.append((header, body))
                    continue
            if isinstance(obj, dict):
                man = obj
            else:
                other_blocks.append((header, body))
        else:
            m = re.search(r"skills/([^/]+)/SKILL\.md", header)
            if m:
                existing_skill_files.add(m.group(1))
            other_blocks.append((header, body))

    if not isinstance(man, dict):
        return text, {**meta, "ok": False, "reason": "no_manifest"}

    _normalize_ui_bindings(man)
    routing = man.setdefault("skill_routing", {})
    if not isinstance(routing, dict):
        routing = {}
        man["skill_routing"] = routing
    ub = man.setdefault("ui_bindings", {})
    if not isinstance(ub, dict):
        ub = {}
        man["ui_bindings"] = ub

    report_skills = [k for k in routing.keys() if _is_report_like_skill(str(k))]
    current = str(ub.get("result_dashboard") or "").strip()
    need_add = False
    skill_name = ""

    if current and current in routing and _is_report_like_skill(current):
        skill_name = current
        meta["bound"] = True
    elif report_skills:
        # Prefer unused report skill
        used = {str(v) for k, v in ub.items() if k != "result_dashboard"}
        skill_name = next((s for s in report_skills if s not in used), report_skills[-1])
        ub["result_dashboard"] = skill_name
        meta["bound"] = True
    else:
        skill_name = _DEFAULT_REPORT_SKILL
        need_add = True
        orch = _pick_orchestrator_agent(man)
        routing[skill_name] = orch
        # Attach to orchestrator agent skills list
        for a in man.get("agents") or []:
            if isinstance(a, dict) and str(a.get("name") or "") == orch:
                skills = a.get("skills")
                if not isinstance(skills, list):
                    skills = []
                    a["skills"] = skills
                if skill_name not in skills:
                    skills.append(skill_name)
                break
        ub["result_dashboard"] = skill_name
        meta["added_skill"] = True
        meta["bound"] = True

    app_name = str(man.get("app_name") or "app").strip() or "app"
    append_file = ""
    if need_add and skill_name not in existing_skill_files:
        append_file = _report_skill_md(app_name, skill_name)

    dumped = json.dumps(man, ensure_ascii=False, indent=2)
    if man_fence:
        dumped = "```json\n" + dumped + "\n```"
    buf.append(man_header + "\n" + dumped + "\n" + (man_rest or ""))
    for h, b in other_blocks:
        buf.append(h + "\n" + b)
    out = "".join(buf)
    if append_file:
        if not out.endswith("\n"):
            out += "\n"
        out += append_file
    return out, meta


def _pick_routed_media_skill(
    routing: Dict[str, str], *candidates: str
) -> str:
    """Prefer a skill present in routing that resolves to a platform media handler."""
    try:
        from core.harness.media_skill_handlers import resolve_media_handler_name
    except Exception:
        resolve_media_handler_name = lambda n: None  # type: ignore

    keys = list(routing.keys()) if isinstance(routing, dict) else []
    for c in candidates:
        c = str(c or "").strip()
        if not c:
            continue
        if c in keys and resolve_media_handler_name(c):
            return c
    for c in candidates:
        c = str(c or "").strip()
        if not c:
            continue
        for k in keys:
            if resolve_media_handler_name(k) and resolve_media_handler_name(k) == resolve_media_handler_name(c):
                return k
        if resolve_media_handler_name(c):
            return c
    return str(candidates[0] if candidates else "")


def enrich_media_true_test_questions(
    questions: List[Dict[str, Any]],
    *,
    routing_src: Any = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Fill missing invoke/asserts for media true-test stubs (FR-AC / conversation).

    Driven by question text + skill_routing catalog resolve — not product names.
    """
    meta: Dict[str, Any] = {"enriched": 0, "skipped": 0}
    routing: Dict[str, str] = {}
    try:
        from core.harness.execution.app_page_skill_inject import extract_skill_routing

        routing = extract_skill_routing(routing_src) or {}
    except Exception:
        routing = {}
    if not routing and isinstance(routing_src, dict):
        nested = routing_src.get("skill_routing")
        if isinstance(nested, dict) and nested:
            routing = {str(k): str(v) for k, v in nested.items() if k}
        else:
            # Accept flat {skill: agent} maps (tests / callers)
            routing = {
                str(k): str(v)
                for k, v in routing_src.items()
                if k
                and k not in ("ui_bindings", "agents", "app_name")
                and isinstance(v, (str, int))
            }

    out: List[Dict[str, Any]] = []
    for q in questions or []:
        if not isinstance(q, dict):
            continue
        q2 = dict(q)
        inv = q2.get("invoke")
        if isinstance(inv, dict) and str(inv.get("skill") or "").strip():
            meta["skipped"] += 1
            out.append(q2)
            continue
        if q2.get("execution") in ("platform_check", "page_smoke") and q2.get("asserts"):
            meta["skipped"] += 1
            out.append(q2)
            continue

        blob = " ".join(
            str(q2.get(k) or "")
            for k in ("question", "min_expectation", "category", "id", "ac_ref")
        ).lower()

        # SSRF / scheme blocks
        if any(x in blob for x in ("内网", "file://", "ssrf", "192.168", "10.x", "169.254")):
            url = "http://192.168.1.10/video.mp4"
            if "file://" in blob:
                url = "file:///tmp/video.mp4"
            q2["execution"] = "platform_check"
            q2["asserts"] = [
                {
                    "type": "platform.ssrf_block",
                    "url": url,
                    "expect_blocked": True,
                }
            ]
            meta["enriched"] += 1
            out.append(q2)
            continue

        # Extension / size file rules
        if any(x in blob for x in (".exe", "扩展名", "白名单", "非视频", "非白名单")):
            q2["execution"] = "platform_check"
            q2["asserts"] = [
                {
                    "type": "platform.file_rules",
                    "file_name": "malware.exe",
                    "file_size": 1024,
                    "allowed_extensions": ["mp4", "avi", "mkv", "mov"],
                    "max_bytes": 524288000,
                    "expect_ok": False,
                }
            ]
            meta["enriched"] += 1
            out.append(q2)
            continue
        if any(x in blob for x in ("500mb", "500 mb", "大小上限", "超过", "file_too_large")):
            too_large = any(x in blob for x in ("超过", "501", "拒绝"))
            size = 525336576 if too_large else 524288000
            q2["execution"] = "platform_check"
            q2["asserts"] = [
                {
                    "type": "platform.file_rules",
                    "file_name": "clip.mp4",
                    "file_size": size,
                    "allowed_extensions": ["mp4", "avi", "mkv", "mov"],
                    "max_bytes": 524288000,
                    "expect_ok": not too_large,
                }
            ]
            meta["enriched"] += 1
            out.append(q2)
            continue

        # Page smoke — structural wizard I/O is mandatory for media frontends
        if any(x in blob for x in ("前端", "页面", "page_smoke", "stage 组件", "报告页", "向导")):
            q2["execution"] = "page_smoke"
            q2["invoke_skills"] = False
            q2["asserts"] = [
                {"type": "stage.component_ok"},
                {"type": "stage.skill_in_routing"},
                {"type": "stage.wizard_io_ok"},
            ]
            meta["enriched"] += 1
            out.append(q2)
            continue

        skill = ""
        params: Dict[str, Any] = {"task_id": str(q2.get("id") or "t-media")}
        asserts: List[Dict[str, Any]] = []

        # Report / timeline alignment before modality keywords (subtitle/speech appear in report text)
        if any(
            x in blob
            for x in ("汇总", "统一报告", "导出", "时间轴对齐", "时间轴同步", "json 格式", "export")
        ) or ("报告" in blob and "画面分析报告" not in blob):
            skill = _pick_routed_media_skill(
                routing, "report_assembly", "report_json_export", "report_aggregator"
            )
            params["video_path"] = "/tmp/videosense/sample.mp4"
            if any(x in blob for x in ("缺失", "占位", "无字幕")) and "字幕/" not in blob:
                asserts = [{"type": "result.contains", "text": "未检测到字幕轨道"}]
            else:
                asserts = [
                    {"type": "result.contains", "text": "timeline"},
                    {"type": "result.contains", "text": "json"},
                ]
        elif any(x in blob for x in ("字幕", "srt", "subtitle")):
            skill = _pick_routed_media_skill(
                routing, "subtitle_extractor", "subtitle_extract", "subtitle_track_extraction"
            )
            no_sub = any(x in blob for x in ("无字幕", "未检测", "缺失"))
            params["video_path"] = (
                "/tmp/videosense/no_subtitle.mp4" if no_sub else "/tmp/videosense/with_subtitle.mp4"
            )
            asserts = (
                [{"type": "result.contains", "text": "未检测到字幕轨道"}]
                if no_sub
                else [
                    {"type": "result.contains", "text": "srt"},
                    {"type": "result.contains", "text": "timeline"},
                ]
            )
        elif any(x in blob for x in ("语音", "vad", "音节", "说话人", "语种", "speech", "audio")):
            skill = _pick_routed_media_skill(
                routing, "speech_analyzer", "speech_acoustic_analysis", "audio_feature_analysis"
            )
            no_audio = any(x in blob for x in ("无语音", "未检测", "缺失", "无音频"))
            params["video_path"] = (
                "/tmp/videosense/no_audio.mp4" if no_audio else "/tmp/videosense/sample.mp4"
            )
            if no_audio:
                asserts = [{"type": "result.contains", "text": "未检测到语音轨道"}]
            elif "音节" in blob or "字/分钟" in blob or "wpm" in blob:
                asserts = [
                    {"type": "result.contains", "text": "syllable_density"},
                    {"type": "result.must_not_contain", "text": "字/分钟"},
                ]
            else:
                asserts = [
                    {"type": "result.contains", "text": "language"},
                    {"type": "result.contains", "text": "speaker_count"},
                    {"type": "result.contains", "text": "emotion"},
                    {"type": "result.contains", "text": "vad"},
                ]
        elif any(x in blob for x in ("关键帧", "画面", "场景切换", "keyframe", "frame")):
            skill = _pick_routed_media_skill(
                routing, "frame_analyzer", "keyframe_extraction", "visual_scene_analysis"
            )
            params["video_path"] = "/tmp/videos/t-v-002_100s.mp4"
            if "10 秒" in blob or "每 10" in blob or "密度" in blob:
                asserts = [
                    {
                        "type": "result.field_equals",
                        "field": "keyframe_density_ok",
                        "value": True,
                    }
                ]
            elif any(x in blob for x in ("损坏", "corrupt", "失败原因", "error")):
                params["video_path"] = "/media/corrupt.mp4"
                asserts = [{"type": "result.contains", "text": "error"}]
            else:
                asserts = [
                    {"type": "result.contains", "text": "keyframes"},
                    {"type": "result.contains", "text": "scene_changes"},
                ]
        elif any(x in blob for x in ("上传", "本地文件", "upload", "task_id")):
            skill = _pick_routed_media_skill(
                routing, "video_ingest", "video_download", "video_downloader"
            )
            params.update(
                {
                    "source_type": "upload",
                    "upload_file_path": "/tmp/uploads/user_video.mp4",
                }
            )
            asserts = [
                {"type": "result.contains", "text": "video_path"},
                {"type": "result.contains", "text": "task_id"},
            ]
        elif any(x in blob for x in ("http", "https", "直链", "下载", "url", "ingest")):
            skill = _pick_routed_media_skill(
                routing, "video_ingest", "video_download", "video_downloader"
            )
            params.update(
                {
                    "source_type": "url",
                    "source_url": "https://example.com/video.mp4",
                }
            )
            asserts = [
                {"type": "result.contains", "text": "video_path"},
                {"type": "result.contains", "text": "metadata"},
            ]

        if skill:
            q2["execution"] = "skill_invoke"
            q2["target_skill"] = skill
            q2["invoke"] = {"skill": skill, "params": params}
            q2["asserts"] = asserts
            meta["enriched"] += 1
        else:
            meta["skipped"] += 1
        out.append(q2)

    # Always ensure one structural page_smoke case when wizard-shaped UI exists
    # (media or any domain — driven by stage graph / ui_bindings, not product names)
    qs2, wmeta = ensure_wizard_io_true_test_case(
        out,
        routing_src=routing_src,
        frontend_pages_src=None,
    )
    if wmeta.get("injected_wizard_io"):
        meta["injected_wizard_io"] = True
        meta["enriched"] = int(meta.get("enriched") or 0) + 1
        out = qs2

    return out, meta


_INGEST_HINTS_FOR_ENRICH = (
    "download",
    "upload",
    "ingest",
    "frame",
    "subtitle",
    "speech",
    "report",
    "video",
    "media",
)


def _page_needs_wizard_io(page: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(page, dict):
        return False
    comps = {
        str(s.get("component") or "")
        for s in (page.get("stages") or [])
        if isinstance(s, dict)
    }
    return "progress_poller" in comps or (
        "file_upload" in comps and "result_dashboard" in comps
    )


def _bindings_need_wizard_io(bindings: Dict[str, str]) -> bool:
    if not bindings:
        return False
    if "progress_poller" in bindings:
        return True
    return "file_upload" in bindings and "result_dashboard" in bindings


def ensure_wizard_io_true_test_case(
    questions: List[Dict[str, Any]],
    *,
    routing_src: Any = None,
    frontend_pages_src: Any = None,
    ui_bindings: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Inject structural ``page_smoke`` + ``stage.wizard_io_ok`` for any wizard app.

    Domain-agnostic: triggers from app_page stage graph or ui_bindings shape,
    not from media/product skill names.
    """
    meta: Dict[str, Any] = {"injected_wizard_io": False, "ok": True}
    out = [q for q in (questions or []) if isinstance(q, dict)]

    has_wizard_smoke = any(
        q.get("execution") == "page_smoke"
        and any(
            isinstance(a, dict) and str(a.get("type") or "") == "stage.wizard_io_ok"
            for a in (q.get("asserts") or [])
        )
        for q in out
    )
    if has_wizard_smoke:
        return out, meta

    bindings = dict(ui_bindings or {})
    if not bindings:
        try:
            from core.harness.execution.app_page_skill_inject import extract_ui_bindings

            bindings = extract_ui_bindings(routing_src) or {}
        except Exception:
            bindings = {}

    page = None
    if frontend_pages_src is not None:
        try:
            from core.harness.execution.app_page_skill_inject import parse_app_page_payload

            if isinstance(frontend_pages_src, dict) and frontend_pages_src.get("stages"):
                page = frontend_pages_src
            else:
                raw = frontend_pages_src
                if isinstance(raw, dict):
                    raw = raw.get("raw_output") or json.dumps(raw, ensure_ascii=False)
                page, _ = parse_app_page_payload(str(raw or ""))
        except Exception:
            page = None

    needs = _page_needs_wizard_io(page) or _bindings_need_wizard_io(bindings)
    if not needs:
        # Fallback: media routing still implies upload→analyze→report wizard
        try:
            from core.harness.execution.app_page_skill_inject import extract_skill_routing
            from core.harness.media_skill_handlers import resolve_media_handler_name

            routing = extract_skill_routing(routing_src) or {}
            if not routing and isinstance(routing_src, dict):
                nested = routing_src.get("skill_routing")
                routing = dict(nested) if isinstance(nested, dict) else {
                    str(k): str(v)
                    for k, v in routing_src.items()
                    if k and k not in ("ui_bindings", "agents", "app_name")
                }
            needs = any(resolve_media_handler_name(k) for k in routing.keys())
        except Exception:
            needs = False

    if not needs:
        return out, meta

    out.append(
        {
            "id": "TQ-PAGE-WIZARD-IO",
            "execution": "page_smoke",
            "invoke_skills": False,
            "check_wizard_io": True,
            "category": "boundary",
            "question": "Wizard stage I/O: progress/results inputs and progress skill ≠ ingest",
            "min_expectation": "progress has task_id+path; progress skill is analysis/report when available",
            "asserts": [
                {"type": "stage.component_ok"},
                {"type": "stage.skill_in_routing"},
                {"type": "stage.wizard_io_ok"},
                {"type": "stage.result_sections_ok"},
            ],
        }
    )
    meta["injected_wizard_io"] = True
    return out, meta


def _questions_from_structured_requirements(
    req_src: Any, routing_src: Any = None
) -> List[Dict[str, Any]]:
    doc: Dict[str, Any] = {}
    if isinstance(req_src, dict):
        doc = req_src
        if not doc.get("functional_requirements") and doc.get("raw_output"):
            try:
                from core.harness.execution.prd_markdown import parse_prd_markdown

                doc = parse_prd_markdown(str(doc.get("raw_output")))
            except Exception:
                logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)
    routing: Dict[str, str] = {}
    try:
        from core.harness.execution.app_page_skill_inject import extract_skill_routing

        routing = extract_skill_routing(routing_src) or {}
    except Exception:
        routing = {}
    skill_keys = list(routing.keys())
    qs: List[Dict[str, Any]] = []
    for fr in doc.get("functional_requirements") or []:
        if not isinstance(fr, dict):
            continue
        fr_id = str(fr.get("id") or "FR")
        name = str(fr.get("name") or fr_id)
        acs = fr.get("acceptance_criteria") or [f"{name} happy path"]
        target = ""
        fr_tok = set(re.findall(r"[a-z0-9]+", (name + " " + fr_id).lower()))
        best = 0
        for sk in skill_keys:
            ov = len(fr_tok & set(re.findall(r"[a-z0-9]+", sk.lower())))
            if ov > best:
                best = ov
                target = sk
        for i, ac in enumerate(acs[:3], 1):
            cat = "happy_path" if i == 1 else ("boundary" if i == 2 else "exception")
            qs.append(
                {
                    "id": f"{fr_id}-AC{i}",
                    "ac_ref": fr_id,
                    "category": cat,
                    "question": f"Verify [{name}]: {ac}",
                    "min_expectation": str(ac),
                    "target_skill": target,
                }
            )
    return qs


def _normalize_true_test_category(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    mapping = {
        "happy_path": "happy_path",
        "happy": "happy_path",
        "正常流程": "happy_path",
        "正常": "happy_path",
        "exception": "exception",
        "异常流程": "exception",
        "异常": "exception",
        "boundary": "boundary",
        "边界测试": "boundary",
        "边界": "boundary",
        "smoke": "smoke",
        "冒烟": "smoke",
    }
    if s in mapping:
        return mapping[s]
    # Chinese labels without lowercasing help
    c = str(raw or "").strip()
    return mapping.get(c, s or "happy_path")


def _assert_blob(q: Dict[str, Any]) -> str:
    return json.dumps(q.get("asserts") or [], ensure_ascii=False).lower()


def _question_has_transcript_assert(q: Dict[str, Any]) -> bool:
    blob = _assert_blob(q)
    return "transcript" in blob


def ensure_true_test_suite_quality(
    questions: List[Any],
    *,
    speech_pipeline: str = "",
    routing_src: Any = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Normalize categories, cap SSRF spam, ensure ASR transcript happy-paths.

    Kernel-generic: uses decisions.speech_pipeline + skill_routing catalog resolve.
    """
    meta: Dict[str, Any] = {
        "ok": True,
        "normalized_category": 0,
        "trimmed_ssrf": 0,
        "injected": [],
    }
    routing: Dict[str, str] = {}
    try:
        from core.harness.execution.app_page_skill_inject import extract_skill_routing

        routing = extract_skill_routing(routing_src) or {}
    except Exception:
        routing = {}

    out: List[Dict[str, Any]] = []
    ssrf_kept = 0
    for q in questions or []:
        if not isinstance(q, dict):
            continue
        q2 = dict(q)
        cat0 = q2.get("category")
        cat = _normalize_true_test_category(cat0)
        if str(cat0 or "") != cat:
            meta["normalized_category"] += 1
        q2["category"] = cat

        asserts = q2.get("asserts") if isinstance(q2.get("asserts"), list) else []
        is_ssrf = any(
            str(a.get("type") or "").lower() in ("platform.ssrf_block", "platform.ssrf_allow")
            for a in asserts
            if isinstance(a, dict)
        )
        if is_ssrf and str(q2.get("execution") or "") == "platform_check":
            if ssrf_kept >= 2:
                meta["trimmed_ssrf"] += 1
                continue
            ssrf_kept += 1
        out.append(q2)

    sp = str(speech_pipeline or "").strip().lower()
    meta["speech_pipeline"] = sp or None

    def _next_id(prefix: str = "TQ-AUTO") -> str:
        n = len(out) + 1
        existing = {str(x.get("id") or "") for x in out}
        while f"{prefix}-{n:03d}" in existing or f"TQ-{n:03d}" in existing:
            n += 1
        return f"{prefix}-{n:03d}"

    if sp in ("asr", "hybrid"):
        has_tx_invoke = any(
            _question_has_transcript_assert(q) and str(q.get("execution") or "") == "skill_invoke"
            for q in out
        )
        speech_skill = _pick_routed_media_skill(
            routing, "speech_analyzer", "speech_acoustic_analysis", "audio_feature_analysis"
        ) or "speech_analyzer"
        report_skill = _pick_routed_media_skill(
            routing, "report_json_export", "report_assembly", "report_aggregator"
        ) or "report_json_export"

        if not has_tx_invoke:
            out.append(
                {
                    "id": _next_id(),
                    "ac_ref": "FR-ASR",
                    "category": "happy_path",
                    "execution": "skill_invoke",
                    "question": "对含音轨视频执行 ASR 转写并返回转写文本",
                    "min_expectation": "结果包含 transcript 字段及转写内容",
                    "target_skill": speech_skill,
                    "invoke": {
                        "skill": speech_skill,
                        "params": {
                            "video_path": "/tmp/media/with_audio.mp4",
                            "task_id": "task-asr-1",
                        },
                    },
                    "asserts": [{"type": "result.contains", "text": "transcript"}],
                    "_sanitize": "injected_asr_transcript",
                }
            )
            meta["injected"].append("asr_speech_transcript")

        has_report_tx = any(
            _question_has_transcript_assert(q)
            and (
                "report" in str(q.get("target_skill") or "").lower()
                or "report" in str((q.get("invoke") or {}).get("skill") or "").lower()
                or "报告" in str(q.get("question") or "")
            )
            for q in out
        )
        if not has_report_tx:
            out.append(
                {
                    "id": _next_id(),
                    "ac_ref": "FR-ASR",
                    "category": "happy_path",
                    "execution": "skill_invoke",
                    "question": "任务完成后导出结构化报告（含转写章节）",
                    "min_expectation": "报告 JSON 含 transcript",
                    "target_skill": report_skill,
                    "invoke": {
                        "skill": report_skill,
                        "params": {
                            "video_path": "/tmp/media/with_audio.mp4",
                            "task_id": "task-asr-report",
                        },
                    },
                    "asserts": [
                        {"type": "result.contains", "text": "transcript"},
                        {"type": "result.status_in", "field": "status", "values": ["completed"]},
                    ],
                    "_sanitize": "injected_asr_report_transcript",
                }
            )
            meta["injected"].append("asr_report_transcript")

    # Soft ratio stats (informational; injects above improve happy_path)
    cats = [_normalize_true_test_category(q.get("category")) for q in out]
    non_smoke = [c for c in cats if c != "smoke"]
    if non_smoke:
        happy = sum(1 for c in non_smoke if c == "happy_path")
        meta["happy_path_ratio"] = round(happy / len(non_smoke), 3)
        meta["counts"] = {
            "happy_path": sum(1 for c in cats if c == "happy_path"),
            "exception": sum(1 for c in cats if c == "exception"),
            "boundary": sum(1 for c in cats if c == "boundary"),
            "smoke": sum(1 for c in cats if c == "smoke"),
            "total": len(cats),
        }
    return out, meta


def sanitize_test_cases_artifact(
    raw: str,
    *,
    architecture_mode: str = "",
    test_execution_mode: str = "",
    requirements_src: Any = None,
    routing_src: Any = None,
    code_blobs: Optional[List[Any]] = None,
    prd_src: Any = None,
    agent_app_src: Any = None,
    frontend_pages_src: Any = None,
) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"ok": True, "mode": "passthrough"}
    text = strip_reasoning_preamble(raw)
    mode = (architecture_mode or "").strip().lower()
    tem = (test_execution_mode or "").strip().lower()
    req = requirements_src if requirements_src is not None else prd_src
    routing = routing_src if routing_src is not None else agent_app_src
    routes = extract_real_http_routes(*(code_blobs or []))
    looks_pytest = bool(_PYTEST_FILE.search(text) or re.search(r"\bTestClient\b", text))
    obj = _try_json_obj(text)
    has_questions = isinstance(obj, dict) and isinstance(obj.get("test_questions"), list)

    force_agent = (
        mode == "agent"
        or tem in ("agent_conversation", "agent_true_test", "true_test")
        or (not routes and looks_pytest)
    )
    if not force_agent and routes and looks_pytest:
        meta["mode"] = "code_pytest"
        meta["routes"] = routes
        return text, meta

    agent_out_mode = (
        "agent_conversation"
        if tem == "agent_conversation"
        else "agent_true_test"
    )

    def _apply_wizard_smoke(qs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if agent_out_mode != "agent_true_test":
            return qs
        qs2, wmeta = ensure_wizard_io_true_test_case(
            qs,
            routing_src=routing,
            frontend_pages_src=frontend_pages_src,
        )
        if wmeta.get("injected_wizard_io"):
            meta["wizard_io_true_test"] = wmeta
        return qs2

    def _apply_suite_quality(qs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if agent_out_mode != "agent_true_test":
            return qs
        sp = _speech_pipeline_from_src(prd_src if prd_src is not None else req)
        qs2, qmeta = ensure_true_test_suite_quality(
            qs, speech_pipeline=sp, routing_src=routing
        )
        if qmeta.get("injected") or qmeta.get("trimmed_ssrf") or qmeta.get("normalized_category"):
            meta["suite_quality"] = qmeta
        return qs2

    if has_questions and not looks_pytest:
        if isinstance(obj, dict):
            # Preserve structured true-test fields; upgrade legacy conversation mode label
            if tem != "agent_conversation":
                obj["mode"] = obj.get("mode") if obj.get("mode") in (
                    "agent_true_test",
                    "true_test",
                ) else agent_out_mode
            qs = obj.get("test_questions") or []
            if isinstance(qs, list) and agent_out_mode == "agent_true_test":
                qs2, emeta = enrich_media_true_test_questions(qs, routing_src=routing)
                cur = qs2 if (emeta.get("enriched") or emeta.get("injected_wizard_io")) else list(qs)
                if emeta.get("enriched") or emeta.get("injected_wizard_io"):
                    meta["media_invoke_enrich"] = emeta
                cur = _apply_wizard_smoke(cur)
                obj["test_questions"] = _apply_suite_quality(cur)
            meta["mode"] = str(obj.get("mode") or agent_out_mode)
            return json.dumps(obj, ensure_ascii=False, indent=2), meta
        meta["mode"] = agent_out_mode
        return json.dumps(obj, ensure_ascii=False, indent=2), meta

    if force_agent and (looks_pytest or not has_questions):
        qs = _questions_from_structured_requirements(req, routing)
        if agent_out_mode == "agent_true_test":
            qs, emeta = enrich_media_true_test_questions(qs, routing_src=routing)
            meta["media_invoke_enrich"] = emeta
            qs = _apply_wizard_smoke(qs)
            qs = _apply_suite_quality(qs)
        out = {
            "mode": agent_out_mode,
            "test_questions": qs,
            "_sanitize": {
                "coerced_from_pytest": looks_pytest,
                "reason": "agent test mode or no real HTTP routes in upstream artifacts",
                "real_routes_found": routes,
                "media_invoke_enrich": meta.get("media_invoke_enrich"),
                "wizard_io_true_test": meta.get("wizard_io_true_test"),
                "suite_quality": meta.get("suite_quality"),
            },
        }
        meta["mode"] = agent_out_mode
        meta["coerced_from_pytest"] = looks_pytest
        return json.dumps(out, ensure_ascii=False, indent=2), meta

    return text, meta


def collect_upstream_blobs(state: Dict[str, Any], stage: Any) -> List[Any]:
    keys = getattr(stage, "input_artifacts", None) or []
    out: List[Any] = []
    for k in keys:
        if isinstance(state, dict) and state.get(k) is not None:
            out.append(state.get(k))
    return out


def find_structured_requirements(state: Dict[str, Any], stage: Any) -> Any:
    gate = getattr(stage, "quality_gate", None) or {}
    key = gate.get("requirements_artifact")
    if key and isinstance(state, dict) and state.get(key) is not None:
        return state.get(key)
    for blob in collect_upstream_blobs(state, stage):
        if isinstance(blob, dict) and blob.get("functional_requirements"):
            return blob
    return None


def pick_routing_blob(state: Dict[str, Any], stage: Any) -> Any:
    gate = getattr(stage, "quality_gate", None) or {}
    key = gate.get("routing_artifact")
    if key and isinstance(state, dict) and state.get(key) is not None:
        return state.get(key)
    for blob in collect_upstream_blobs(state, stage):
        raw = ""
        if isinstance(blob, dict):
            if blob.get("ui_bindings") or blob.get("skill_routing"):
                return blob
            raw = str(blob.get("raw_output") or "")
        else:
            raw = str(blob or "")
        if "ui_bindings" in raw or "skill_routing" in raw:
            return blob
    blobs = collect_upstream_blobs(state, stage)
    return blobs[0] if blobs else None


def apply_stage_output_sanitizers(
    *,
    stage: Any,
    state: Dict[str, Any],
    result: str,
    elapsed_sec: float,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Config-driven post-process. Returns (result, artifact_dict, meta).

    Only quality_gate / architecture_mode / test_execution_mode trigger work —
    never skill_name or output_artifact string matching.
    """
    gate = getattr(stage, "quality_gate", None) or {}
    out = result
    art: Dict[str, Any] = {"raw_output": out, "elapsed_sec": elapsed_sec}
    meta: Dict[str, Any] = {}
    arch_mode = resolve_architecture_mode(stage, state)
    stage_arch = str(getattr(stage, "architecture_mode", "") or "").strip()
    tem = str(getattr(stage, "test_execution_mode", "") or "").strip()

    if gate.get("finalize_structured_doc") or gate.get("finalize_prd"):
        try:
            from core.harness.execution.prd_quality_gate import materialize_prd_artifact

            prd_art = materialize_prd_artifact(out, elapsed_sec=elapsed_sec)
            if isinstance(prd_art, dict) and (
                prd_art.get("functional_requirements") or prd_art.get("title")
            ):
                art = prd_art
                out = str(prd_art.get("raw_output") or out)
                meta["finalize_structured_doc"] = True
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    if gate.get("sanitize_architecture"):
        fixed, ameta = sanitize_architecture_artifact(
            out, architecture_mode=arch_mode or stage_arch
        )
        if fixed != out:
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": ameta}
            meta["architecture"] = ameta

    pair = gate.get("ensure_ui_binding_pair")
    if pair or gate.get("ensure_dual_ui_bindings"):
        pair_list = pair if isinstance(pair, (list, tuple)) else ("file_upload", "data_form")
        fixed, mmeta = ensure_manifest_ui_binding_pair(out, pair=pair_list)
        if mmeta.get("patched_ui_bindings") or mmeta.get("normalized_ui_bindings") or fixed != out:
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": mmeta}
            meta["ui_bindings"] = mmeta

    if gate.get("ensure_result_dashboard_skill"):
        fixed, dmeta = ensure_result_dashboard_skill(out)
        if dmeta.get("added_skill") or dmeta.get("bound") or fixed != out:
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": dmeta}
            meta["result_dashboard_skill"] = dmeta

    if gate.get("normalize_media_skill_names"):
        fixed, nmeta = normalize_media_skill_names(out)
        if nmeta.get("remapped") or fixed != out:
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": nmeta}
            meta["normalize_media_skill_names"] = nmeta

    if gate.get("ensure_agent_app_skill_consistency") or gate.get("normalize_media_skill_names"):
        fixed, cmeta = ensure_agent_app_skill_consistency(out)
        if (
            cmeta.get("renamed")
            or cmeta.get("frontmatter_fixed")
            or cmeta.get("deduped_stems")
            or cmeta.get("routing_aligned")
            or cmeta.get("merged_speech")
            or cmeta.get("dropped_lifecycle_skills")
            or fixed != out
        ):
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": cmeta}
            meta["ensure_agent_app_skill_consistency"] = cmeta

    if (
        gate.get("ensure_platform_media_skill_contracts")
        or gate.get("normalize_media_skill_names")
        or gate.get("ensure_agent_app_skill_consistency")
    ):
        fixed, pmeta = ensure_platform_media_skill_contracts(out)
        if pmeta.get("rewritten") or fixed != out:
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": pmeta}
            meta["ensure_platform_media_skill_contracts"] = pmeta

    if gate.get("repair_app_page"):
        aa = pick_routing_blob(state, stage)
        fixed, rmeta = repair_frontend_pages_with_prd(
            out, aa or {}, (state or {}).get("prd")
        )
        wiz = rmeta.get("wizard_io") if isinstance(rmeta, dict) else {}
        if (
            fixed != out
            or rmeta.get("added_data_form")
            or rmeta.get("filled")
            or rmeta.get("replaced")
            or (isinstance(wiz, dict) and any(
                wiz.get(k)
                for k in (
                    "show_when",
                    "progress_input",
                    "progress_skill_remap",
                    "results_input",
                )
            ))
        ):
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "skill_inject": rmeta}
            meta["repair_app_page"] = rmeta
        elif rmeta.get("ok") and rmeta.get("routing_keys"):
            art = dict(art)
            art["skill_inject"] = rmeta
            meta["repair_app_page"] = rmeta

    run_tests = bool(gate.get("sanitize_test_cases")) or tem in (
        "agent_conversation",
        "agent_true_test",
        "true_test",
    )
    if run_tests and tem != "pytest":
        blobs = collect_upstream_blobs(state, stage)
        fixed, tmeta = sanitize_test_cases_artifact(
            out,
            architecture_mode=arch_mode or stage_arch,
            test_execution_mode=tem
            or (
                "agent_true_test"
                if (arch_mode or stage_arch) == "agent"
                else ""
            ),
            requirements_src=find_structured_requirements(state, stage),
            routing_src=pick_routing_blob(state, stage),
            code_blobs=blobs,
            frontend_pages_src=(state or {}).get("frontend_pages"),
        )
        if fixed != out or tmeta.get("coerced_from_pytest"):
            out = fixed
            art = {"raw_output": out, "elapsed_sec": elapsed_sec, "sanitize": tmeta}
            meta["test_cases"] = tmeta

    if not meta:
        art = {"raw_output": out, "elapsed_sec": elapsed_sec}
    return out, art, meta
