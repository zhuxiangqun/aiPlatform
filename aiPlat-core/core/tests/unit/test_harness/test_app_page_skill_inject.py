"""Tests for factory app_page skill injection (ui_bindings + skill_routing, no YAML)."""
from __future__ import annotations

import json
from copy import deepcopy

from core.harness.execution.app_page_skill_inject import (
    extract_skill_routing,
    extract_ui_bindings,
    inject_app_page_skills,
    repair_frontend_pages_raw,
    skill_routing_context_block,
    speech_pipeline_context_block,
)


AGENT_APP_RAW = """
## FILE: ~/.aiplat/apps/videosense/agent_manifest.json
{
  "app_name": "videosense",
  "mode": "multi_agent",
  "agents": [{"name": "orchestrator_agent", "skills": ["video_source_ingest", "check_progress"]}],
  "skill_routing": {
    "video_source_ingest": "orchestrator_agent",
    "video_download": "download_agent",
    "video_visual_analysis": "visual_agent",
    "subtitle_extraction": "content_agent",
    "audio_content_analysis": "content_agent",
    "check_progress": "orchestrator_agent"
  },
  "ui_bindings": {
    "file_upload": "video_source_ingest",
    "progress_poller": "check_progress",
    "result_dashboard": "video_visual_analysis"
  }
}
"""

EMPTY_PAGE = {
    "app_name": "videosense",
    "mode": "wizard",
    "stages": [
        {"id": "source", "title": "视频来源", "skill": "", "component": "file_upload"},
        {"id": "progress", "title": "处理中", "skill": "", "component": "progress_poller"},
        {"id": "results", "title": "结果", "skill": "", "component": "result_dashboard"},
    ],
}


def test_extract_skill_routing_from_file_block():
    routing = extract_skill_routing(AGENT_APP_RAW)
    assert routing["video_source_ingest"] == "orchestrator_agent"
    assert "check_progress" in routing
    assert len(routing) == 6


def test_extract_ui_bindings_from_manifest():
    bindings = extract_ui_bindings(AGENT_APP_RAW)
    assert bindings["file_upload"] == "video_source_ingest"
    assert bindings["progress_poller"] == "check_progress"
    assert bindings["result_dashboard"] == "video_visual_analysis"


def test_extract_from_agent_app_dict_with_raw_output():
    routing = extract_skill_routing({"raw_output": AGENT_APP_RAW, "elapsed_sec": 12})
    assert "video_visual_analysis" in routing
    assert extract_ui_bindings({"raw_output": AGENT_APP_RAW})["file_upload"] == "video_source_ingest"


def test_inject_fills_empty_skills_via_ui_bindings():
    page = {**EMPTY_PAGE, "stages": [dict(s) for s in EMPTY_PAGE["stages"]]}
    routing = extract_skill_routing(AGENT_APP_RAW)
    out = inject_app_page_skills(page, routing, agent_app_source=AGENT_APP_RAW)
    assert out["stages"][0]["skill"] == "video_source_ingest"
    assert out["stages"][1]["skill"] == "check_progress"
    assert out["stages"][2]["skill"] == "video_visual_analysis"
    assert out.get("ui_bindings", {}).get("file_upload") == "video_source_ingest"


def test_ui_bindings_overwrite_wrong_but_valid_routing_skills():
    """FE often invents valid skill names on wrong components; bindings must win."""
    page = {
        "app_name": "videosense",
        "mode": "wizard",
        "stages": [
            {"id": "source", "skill": "video_source_ingest", "component": "file_upload"},
            {"id": "url", "skill": "subtitle_extraction", "component": "data_form"},
            {"id": "progress", "skill": "audio_content_analysis", "component": "progress_poller"},
            {"id": "results", "skill": "video_download", "component": "result_dashboard"},
        ],
    }
    # Extend bindings with data_form
    raw = AGENT_APP_RAW.replace(
        '"file_upload": "video_source_ingest"',
        '"file_upload": "video_source_ingest",\n    "data_form": "video_download"',
    )
    routing = extract_skill_routing(raw)
    out = inject_app_page_skills(deepcopy(page), routing, agent_app_source=raw)
    assert out["stages"][0]["skill"] == "video_source_ingest"
    assert out["stages"][1]["skill"] == "video_download"
    assert out["stages"][2]["skill"] == "check_progress"
    assert out["stages"][3]["skill"] == "video_visual_analysis"
    page = {
        "app_name": "videosense",
        "mode": "wizard",
        "stages": [
            {"id": "ingest", "title": "获取视频", "skill": "video_ingest", "component": "file_upload"},
            {"id": "progress", "title": "分析中", "skill": "check_progress", "component": "progress_poller"},
            {"id": "results", "title": "分析结果", "skill": "check_progress", "component": "result_dashboard"},
        ],
    }
    routing = extract_skill_routing(AGENT_APP_RAW)
    out = inject_app_page_skills(deepcopy(page), routing, agent_app_source=AGENT_APP_RAW)
    assert out["stages"][0]["skill"] == "video_source_ingest"
    assert out["stages"][1]["skill"] == "check_progress"
    assert out["stages"][2]["skill"] == "video_visual_analysis"

    new_raw, meta = repair_frontend_pages_raw(json.dumps(page), {"raw_output": AGENT_APP_RAW})
    assert meta["ok"] is True
    assert meta.get("has_ui_bindings") is True
    assert meta.get("replaced", 0) >= 1
    from core.harness.execution.app_page_skill_inject import parse_app_page_payload

    fixed, _ = parse_app_page_payload(new_raw)
    assert fixed["stages"][0]["skill"] == "video_source_ingest"
    assert fixed["stages"][2]["skill"] == "video_visual_analysis"


def test_ui_bindings_override_token_guess():
    raw = """
## FILE: agent_manifest.json
{
  "skill_routing": {
    "alpha_skill": "a",
    "beta_skill": "b",
    "gamma_skill": "c"
  },
  "ui_bindings": {
    "file_upload": "beta_skill",
    "progress_poller": "gamma_skill",
    "result_dashboard": "alpha_skill"
  }
}
"""
    page = {
        "stages": [
            {"skill": "", "component": "file_upload"},
            {"skill": "", "component": "progress_poller"},
            {"skill": "", "component": "result_dashboard"},
        ]
    }
    routing = extract_skill_routing(raw)
    out = inject_app_page_skills(page, routing, agent_app_source=raw)
    assert out["stages"][0]["skill"] == "beta_skill"
    assert out["stages"][1]["skill"] == "gamma_skill"
    assert out["stages"][2]["skill"] == "alpha_skill"


def test_token_overlap_fallback_without_ui_bindings():
    """Legacy manifests without ui_bindings still fill via skill-name token overlap."""
    raw = """
## FILE: agent_manifest.json
{
  "skill_routing": {
    "upload_file": "a",
    "poll_progress": "b",
    "show_result": "c"
  }
}
"""
    page = {
        "stages": [
            {"skill": "", "component": "file_upload"},
            {"skill": "", "component": "progress_poller"},
            {"skill": "", "component": "result_dashboard"},
        ]
    }
    routing = extract_skill_routing(raw)
    out = inject_app_page_skills(page, routing, agent_app_source=raw)
    assert out["stages"][0]["skill"] == "upload_file"
    assert out["stages"][1]["skill"] == "poll_progress"
    assert out["stages"][2]["skill"] == "show_result"


def test_repair_frontend_pages_raw_end_to_end():
    raw = json.dumps(EMPTY_PAGE, ensure_ascii=False)
    new_raw, meta = repair_frontend_pages_raw(raw, {"raw_output": AGENT_APP_RAW})
    assert meta["filled"] == 3
    assert meta["ok"] is True
    assert meta["empty_after"] == 0
    assert meta["has_ui_bindings"] is True
    from core.harness.execution.app_page_skill_inject import parse_app_page_payload

    page, _ = parse_app_page_payload(new_raw)
    assert page["stages"][0]["skill"] == "video_source_ingest"


def test_skill_routing_context_block_includes_ui_bindings():
    block = skill_routing_context_block({"raw_output": AGENT_APP_RAW})
    assert "skill_routing" in block
    assert "ui_bindings" in block
    assert "video_source_ingest" in block
    assert "file_upload" in block
    assert "禁止" in block


def test_speech_pipeline_context_block_asr_and_features_only():
    asr = speech_pipeline_context_block(
        {"decisions": {"speech_pipeline": "asr"}, "title": "x"}
    )
    assert "speech_pipeline" in asr
    assert "asr" in asr
    assert "transcript" in asr
    assert "必须" in asr

    feats = speech_pipeline_context_block(
        {"raw_output": json.dumps({"decisions": {"speech_pipeline": "audio_features_only"}})}
    )
    assert "audio_features_only" in feats
    assert "禁止" in feats

    assert speech_pipeline_context_block({}) == ""
    assert speech_pipeline_context_block(None) == ""
