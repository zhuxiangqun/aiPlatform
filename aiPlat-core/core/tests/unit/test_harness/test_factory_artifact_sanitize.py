"""Tests for factory_artifact_sanitize helpers."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from core.harness.execution.factory_artifact_sanitize import (
    apply_stage_output_sanitizers,
    ensure_dual_ingest_stages,
    ensure_manifest_dual_ui_bindings,
    ensure_manifest_ui_binding_pair,
    ensure_platform_media_skill_contracts,
    ensure_result_dashboard_skill,
    ensure_wizard_stage_io,
    extract_real_http_routes,
    ensure_agent_app_skill_consistency,
    load_canonical_media_skill_md,
    normalize_media_skill_names,
    repair_frontend_pages_with_prd,
    sanitize_architecture_artifact,
    sanitize_test_cases_artifact,
    strip_reasoning_preamble,
)


def test_strip_reasoning_preamble_to_file():
    raw = (
        "### 步骤1：分析\n方案 A\n\n"
        "## FILE: ~/.aiplat/apps/x/agent_manifest.json\n"
        '{"app_name":"x"}\n'
    )
    out = strip_reasoning_preamble(raw)
    assert out.lstrip().startswith("## FILE:")
    assert "步骤1" not in out.split("## FILE:")[0]


def test_strip_reasoning_preamble_to_json():
    raw = "步骤1：分析关键约束\n方案比较\n\n{\"title\": \"ok\"}"
    out = strip_reasoning_preamble(raw)
    assert out.lstrip().startswith("{")


def test_ensure_dual_ingest_adds_data_form_from_ui_bindings_only():
    page = {
        "app_name": "demo",
        "stages": [
            {
                "id": "ingest",
                "component": "file_upload",
                "skill": "video_ingest",
                "next": "progress",
            },
            {"id": "progress", "component": "progress_poller", "skill": "check_progress"},
        ],
    }
    # No PRD sniffing — dual only when ui_bindings already declares both components
    out, meta = ensure_dual_ingest_stages(
        page,
        prd_src={"description": "ignored domain text"},
        ui_bindings={"file_upload": "video_ingest", "data_form": "video_ingest"},
    )
    assert meta.get("added_data_form") is True
    comps = [s.get("component") for s in out["stages"]]
    assert "data_form" in comps
    assert comps.count("file_upload") == 1


def test_ensure_dual_ingest_skips_without_both_bindings():
    page = {
        "stages": [
            {"id": "ingest", "component": "file_upload", "skill": "x", "next": "done"},
        ]
    }
    out, meta = ensure_dual_ingest_stages(
        page,
        ui_bindings={"file_upload": "x"},
    )
    assert meta.get("added_data_form") is not True
    assert len(out["stages"]) == 1


def test_ensure_wizard_stage_io_wires_progress_and_show_when():
    """Broken factory output: progress reuses ingest skill; missing video_path/show_when."""
    page = {
        "app_name": "demo",
        "mode": "wizard",
        "stages": [
            {
                "id": "source",
                "component": "data_form",
                "skill": "video_downloader",
                "config": {
                    "fields": [
                        {
                            "name": "source_type",
                            "type": "select",
                            "options": [
                                {"value": "url", "label": "URL"},
                                {"value": "upload", "label": "Upload"},
                            ],
                        },
                        {"name": "video_url", "type": "url"},
                    ]
                },
                "next": "upload",
            },
            {
                "id": "upload",
                "component": "file_upload",
                "skill": "video_downloader",
                "next": "progress",
            },
            {
                "id": "progress",
                "component": "progress_poller",
                "skill": "video_downloader",
                "config": {"input": {"task_id": "{{upload.task_id}}"}},
                "next": "results",
            },
            {
                "id": "results",
                "component": "result_dashboard",
                "skill": "video_downloader",
                "config": {},
            },
        ],
    }
    bindings = {
        "file_upload": "video_downloader",
        "data_form": "video_downloader",
        "progress_poller": "video_downloader",
        "result_dashboard": "report_json_export",
    }
    out, meta = ensure_wizard_stage_io(page, ui_bindings=bindings)
    assert meta.get("show_when", 0) >= 1
    assert meta.get("progress_skill_remap") is True
    assert meta.get("progress_input") is True
    assert meta.get("results_input") is True

    by_id = {s["id"]: s for s in out["stages"]}
    url_field = next(f for f in by_id["source"]["config"]["fields"] if f["name"] == "video_url")
    assert url_field.get("show_when") == {"source_type": "url"}
    assert by_id["progress"]["skill"] == "report_json_export"
    assert "{{upload.video_path}}" in str(by_id["progress"]["config"]["input"])
    assert by_id["results"]["skill"] == "report_json_export"
    assert by_id["results"]["config"]["input"]["task_id"] == "{{progress.task_id}}"
    assert "{{progress." in str(by_id["results"]["config"]["input"])


def test_canonicalize_app_page_media_skills_rewrites_aliases():
    from core.harness.execution.factory_artifact_sanitize import (
        canonicalize_app_page_media_skills,
        repair_frontend_pages_with_prd,
    )
    from core.harness.execution.true_test_runtime import check_wizard_stage_io

    page = {
        "stages": [
            {
                "id": "progress",
                "component": "progress_poller",
                "skill": "report_assembly",
                "config": {
                    "input": {
                        "task_id": "{{upload.task_id}}",
                        "video_path": "{{upload.video_path}}",
                    }
                },
            },
            {
                "id": "results",
                "component": "result_dashboard",
                "skill": "report_assembly",
                "config": {
                    "input": {
                        "task_id": "{{progress.task_id}}",
                        "video_path": "{{progress.video_path}}",
                    },
                    "sections": [
                        {"key": "summary", "label": "摘要", "type": "markdown"}
                    ],
                },
            },
        ]
    }
    ok, fails, _ = check_wizard_stage_io(page)
    assert any("skill_alias_not_canonical:report_assembly" in f for f in fails)

    out, meta = canonicalize_app_page_media_skills(page)
    assert meta["remapped"].get("report_assembly") == "report_json_export"
    assert out["stages"][0]["skill"] == "report_json_export"
    assert out["stages"][1]["skill"] == "report_json_export"

    # Full repair_app_page path also canonicalizes
    raw = json.dumps(
        {
            "app_name": "demo",
            "stages": [
                {
                    "id": "results",
                    "component": "result_dashboard",
                    "skill": "report_assembly",
                    "config": {
                        "sections": [
                            {"key": "summary", "label": "摘要", "type": "markdown"}
                        ]
                    },
                }
            ],
        },
        ensure_ascii=False,
    )
    fixed, rmeta = repair_frontend_pages_with_prd(
        raw,
        {
            "skill_routing": {
                "report_assembly": "orch",
                "report_json_export": "orch",
            },
            "ui_bindings": {"result_dashboard": "report_assembly"},
        },
    )
    page2 = json.loads(fixed)
    assert page2["stages"][0]["skill"] == "report_json_export"
    # wizard_io may already promote aliases before media_skill_canonical runs;
    # normalize_media_skill_names must still rewrite agent_app aliases.
    aa_raw = (
        "## FILE: ~/.aiplat/apps/demo/agent_manifest.json\n"
        + json.dumps(
            {
                "app_name": "demo",
                "skill_routing": {"report_assembly": "orch"},
                "ui_bindings": {"result_dashboard": "report_assembly"},
                "agents": [{"name": "orch", "skills": ["report_assembly"]}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    aa_fixed, aa_meta = normalize_media_skill_names(aa_raw)
    assert aa_meta.get("remapped", {}).get("report_assembly") == "report_json_export"
    man_m = re.search(r"\{[\s\S]*\}", aa_fixed)
    assert man_m
    man = json.loads(man_m.group(0))
    assert "report_json_export" in (man.get("skill_routing") or {})
    assert "report_assembly" not in (man.get("skill_routing") or {})
    assert (man.get("ui_bindings") or {}).get("result_dashboard") == "report_json_export"
    assert "report_json_export" in ((man.get("agents") or [{}])[0].get("skills") or [])

    from core.harness.execution.factory_artifact_sanitize import (
        ensure_result_dashboard_sections,
    )

    page = {
        "stages": [
            {
                "id": "results",
                "component": "result_dashboard",
                "config": {
                    "sections": [
                        {"key": "keyframes", "label": "帧", "type": "gallery"},
                        {"key": "speech", "label": "语音", "type": "json"},
                        {"key": "summary", "label": "摘要", "type": "md"},
                    ]
                },
            }
        ]
    }
    out, meta = ensure_result_dashboard_sections(page)
    assert meta.get("remapped", 0) >= 3
    secs = out["stages"][0]["config"]["sections"]
    by_key = {s["key"]: s["type"] for s in secs}
    assert by_key["keyframes"] == "image_timeline"
    assert by_key["speech"] == "key_value"
    assert by_key["summary"] == "markdown"

    empty = {
        "stages": [{"id": "results", "component": "result_dashboard", "config": {}}]
    }
    out2, meta2 = ensure_result_dashboard_sections(empty)
    assert meta2.get("filled_defaults", 0) >= 1
    assert len(out2["stages"][0]["config"]["sections"]) >= 2

    asr_page = {
        "stages": [
            {
                "id": "results",
                "component": "result_dashboard",
                "config": {
                    "sections": [
                        {"key": "speech", "label": "语音声学特征", "type": "key_value"},
                        {"key": "vad", "label": "VAD", "type": "timeline"},
                    ]
                },
            }
        ]
    }
    asr_out, asr_meta = ensure_result_dashboard_sections(asr_page, speech_pipeline="asr")
    assert asr_meta.get("added_transcript") is True
    assert any(s.get("key") == "transcript" for s in asr_out["stages"][0]["config"]["sections"])

    feats = {
        "stages": [
            {
                "id": "results",
                "component": "result_dashboard",
                "config": {
                    "sections": [
                        {"key": "speech", "label": "语音声学特征", "type": "key_value"},
                        {"key": "transcript", "label": "语音转写", "type": "subtitle_timeline"},
                    ]
                },
            }
        ]
    }
    feats_out, feats_meta = ensure_result_dashboard_sections(
        feats, speech_pipeline="audio_features_only"
    )
    assert feats_meta.get("removed_transcript") is True
    assert all(
        s.get("key") != "transcript" for s in feats_out["stages"][0]["config"]["sections"]
    )


def test_repair_frontend_pages_with_prd_runs_wizard_io():
    raw = json.dumps(
        {
            "app_name": "demo",
            "stages": [
                {"id": "upload", "component": "file_upload", "skill": "", "next": "progress"},
                {
                    "id": "progress",
                    "component": "progress_poller",
                    "skill": "video_downloader",
                    "config": {},
                    "next": "results",
                },
                {"id": "results", "component": "result_dashboard", "skill": "", "config": {}},
            ],
        },
        ensure_ascii=False,
    )
    agent_app = {
        "skill_routing": {
            "video_downloader": "orch",
            "report_json_export": "orch",
        },
        "ui_bindings": {
            "file_upload": "video_downloader",
            "data_form": "video_downloader",
            "progress_poller": "video_downloader",
            "result_dashboard": "report_json_export",
        },
    }
    fixed, meta = repair_frontend_pages_with_prd(raw, agent_app)
    page = json.loads(fixed)
    wiz = meta.get("wizard_io") or {}
    assert wiz.get("progress_skill_remap") is True
    progress = next(s for s in page["stages"] if s["id"] == "progress")
    assert progress["skill"] == "report_json_export"
    assert "video_path" in (progress.get("config") or {}).get("input", {})
    # repair_app_page path must also close result_dashboard section types
    sec = meta.get("result_sections") or {}
    assert sec.get("filled_defaults", 0) >= 1 or sec.get("remapped", 0) >= 0
    results = next(s for s in page["stages"] if s["id"] == "results")
    sections = (results.get("config") or {}).get("sections") or []
    assert sections, "repair must fill result_dashboard.sections"
    from core.harness.execution.true_test_runtime import RESULT_DASHBOARD_SECTION_TYPES

    for s in sections:
        assert s.get("type") in RESULT_DASHBOARD_SECTION_TYPES


def test_repair_remaps_invented_section_types_end_to_end():
    """Factory gate: invented section types must not survive repair_app_page."""
    raw = json.dumps(
        {
            "app_name": "demo",
            "stages": [
                {
                    "id": "results",
                    "component": "result_dashboard",
                    "skill": "report_json_export",
                    "config": {
                        "sections": [
                            {"key": "keyframes", "label": "帧", "type": "fancy_card"},
                            {"key": "summary", "label": "摘要", "type": "md"},
                        ]
                    },
                }
            ],
        },
        ensure_ascii=False,
    )
    agent_app = {
        "skill_routing": {"report_json_export": "orch"},
        "ui_bindings": {"result_dashboard": "report_json_export"},
    }
    fixed, meta = repair_frontend_pages_with_prd(raw, agent_app)
    page = json.loads(fixed)
    assert (meta.get("result_sections") or {}).get("remapped", 0) >= 1
    types = {s["type"] for s in page["stages"][0]["config"]["sections"]}
    assert "fancy_card" not in types
    assert "image_timeline" in types or "key_value" in types
    assert "markdown" in types


def test_sanitize_architecture_rejects_code_mode_under_agent():
    raw = json.dumps(
        {
            "title": "demo",
            "overview": "web tool",
            "components": [{"name": "api"}],
            "api_design": [{"method": "POST", "path": "/api/upload"}],
        },
        ensure_ascii=False,
    )
    out, meta = sanitize_architecture_artifact(raw, architecture_mode="agent")
    obj = json.loads(out)
    assert meta.get("rejected_code_architecture") is True
    assert obj.get("agents") == []
    assert "components" not in obj
    assert obj.get("architecture_mode") == "agent"


def test_sanitize_test_cases_coerces_pytest_under_agent():
    raw = """## FILE: tests/test_ingest.py
```python
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
def test_upload():
    assert client.post("/api/video/upload").status_code == 200
```
"""
    prd = {
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "source_ingest",
                "acceptance_criteria": ["upload returns task_id", "reject private IP"],
            }
        ]
    }
    out, meta = sanitize_test_cases_artifact(
        raw,
        architecture_mode="agent",
        prd_src=prd,
        agent_app_src={"skill_routing": {"video_ingest": "orchestrator_agent"}},
        code_blobs=[],
    )
    obj = json.loads(out)
    assert meta.get("coerced_from_pytest") is True
    assert obj["mode"] == "agent_true_test"
    assert len(obj["test_questions"]) >= 1
    assert obj["test_questions"][0]["ac_ref"] == "FR-001"


def test_extract_real_http_routes_ignores_agent_md():
    blob = """## FILE: ~/.aiplat/apps/x/agents/a/AGENT.md
---
name: a
---
# hello
## FILE: app/main.py
@app.post("/api/upload")
def upload(): ...
"""
    routes = extract_real_http_routes(blob)
    assert "/api/upload" in routes


def test_ensure_manifest_ui_binding_pair_completes_missing_side():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "skill_routing": {"video_ingest": "orchestrator_agent"},
  "ui_bindings": {"file_upload": "video_ingest"}
}
"""
    out, meta = ensure_manifest_ui_binding_pair(
        raw, pair=("file_upload", "data_form")
    )
    assert meta.get("patched_ui_bindings") is True
    assert '"data_form": "video_ingest"' in out or '"data_form":"video_ingest"' in out.replace(
        " ", ""
    )


def test_ensure_manifest_dual_ui_bindings_legacy_no_prd_sniff():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "ui_bindings": {"file_upload": "video_ingest"}
}
"""
    # Legacy API still works; PRD text is ignored
    out, meta = ensure_manifest_dual_ui_bindings(
        raw, prd_src={"description": "视频链接或本地上传"}
    )
    assert meta.get("patched_ui_bindings") is True
    assert "data_form" in out


def test_ensure_result_dashboard_skill_adds_report_skill():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [{"name": "orch", "role": "orchestrator", "skills": ["ingest"]}],
  "skill_routing": {"ingest": "orch"},
  "ui_bindings": {
    "file_upload": "ingest",
    "result_dashboard": "orch"
  }
}
## FILE: ~/.aiplat/apps/demo/skills/ingest/SKILL.md
---
name: ingest
---
# ingest
"""
    out, meta = ensure_result_dashboard_skill(raw)
    assert meta.get("added_skill") is True
    assert meta.get("bound") is True
    assert "report_json_export" in out
    assert '"result_dashboard": "report_json_export"' in out.replace(" ", "") or (
        '"result_dashboard":"report_json_export"' in out.replace(" ", "")
    )
    assert "skills/report_json_export/SKILL.md" in out


def test_apply_ensure_result_dashboard_via_quality_gate():
    stage = SimpleNamespace(
        architecture_mode="agent",
        test_execution_mode="",
        input_artifacts=[],
        quality_gate={"ensure_result_dashboard_skill": True},
    )
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{"app_name":"demo","agents":[{"name":"o","role":"orchestrator","skills":["a"]}],"skill_routing":{"a":"o"},"ui_bindings":{"file_upload":"a"}}
"""
    out, art, meta = apply_stage_output_sanitizers(
        stage=stage, state={}, result=raw, elapsed_sec=0.5
    )
    assert "result_dashboard_skill" in meta
    assert "report_json_export" in out


def test_normalize_media_skill_names_remaps_invented():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [{"name": "o", "role": "orchestrator", "skills": ["video_fetch", "auth_login"]}],
  "skill_routing": {"video_fetch": "o", "auth_login": "o"},
  "ui_bindings": {"file_upload": "video_fetch", "data_form": "video_fetch"}
}
## FILE: ~/.aiplat/apps/demo/skills/video_fetch/SKILL.md
---
name: video_fetch
---
# video_fetch
"""
    out, meta = normalize_media_skill_names(raw)
    assert meta.get("remapped", {}).get("video_fetch") == "video_downloader"
    assert "video_downloader" in out
    assert "skills/video_downloader/SKILL.md" in out
    assert "auth_login" in out  # unrelated skill untouched
    assert "name: video_downloader" in out


def test_normalize_promotes_catalog_alias():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{"app_name":"demo","agents":[{"name":"o","skills":["keyframe_extract"]}],"skill_routing":{"keyframe_extract":"o"},"ui_bindings":{"file_upload":"keyframe_extract"}}
## FILE: ~/.aiplat/apps/demo/skills/keyframe_extract/SKILL.md
---
name: keyframe_extract
---
"""
    out, meta = normalize_media_skill_names(raw)
    assert meta.get("remapped", {}).get("keyframe_extract") == "frame_analyzer"
    assert "frame_analyzer" in out
    assert "skills/frame_analyzer/SKILL.md" in out


def test_apply_normalize_media_via_quality_gate():
    stage = SimpleNamespace(
        architecture_mode="agent",
        test_execution_mode="",
        input_artifacts=[],
        quality_gate={"normalize_media_skill_names": True},
    )
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{"app_name":"demo","agents":[{"name":"o","skills":["frame_pick"]}],"skill_routing":{"frame_pick":"o"},"ui_bindings":{"file_upload":"frame_pick"}}
"""
    out, art, meta = apply_stage_output_sanitizers(
        stage=stage, state={}, result=raw, elapsed_sec=0.1
    )
    assert "normalize_media_skill_names" in meta
    assert "frame_analyzer" in out


def test_apply_stage_output_sanitizers_respects_quality_gate():
    stage = SimpleNamespace(
        architecture_mode="agent",
        test_execution_mode="",
        input_artifacts=["prd"],
        quality_gate={"sanitize_architecture": True},
    )
    raw = json.dumps({"title": "t", "components": [{"name": "api"}]})
    out, art, meta = apply_stage_output_sanitizers(
        stage=stage, state={}, result=raw, elapsed_sec=1.0
    )
    assert "architecture" in meta
    assert json.loads(out).get("architecture_mode") == "agent"


def test_apply_stage_output_sanitizers_noop_without_gate():
    stage = SimpleNamespace(
        architecture_mode="",
        test_execution_mode="",
        input_artifacts=[],
        quality_gate={"min_output_length": 100},
    )
    raw = '{"title": "plain"}'
    out, art, meta = apply_stage_output_sanitizers(
        stage=stage, state={}, result=raw, elapsed_sec=1.0
    )
    assert meta == {}
    assert art["raw_output"] == raw


def test_enrich_media_true_test_adds_invoke_to_fr_stubs():
    from core.harness.execution.factory_artifact_sanitize import (
        enrich_media_true_test_questions,
        sanitize_test_cases_artifact,
    )

    qs = [
        {
            "id": "FR-001-AC1",
            "question": "Verify: 支持输入 HTTP/HTTPS 视频直链 URL，系统能成功下载视频",
            "min_expectation": "下载成功",
            "target_skill": "",
        },
        {
            "id": "FR-001-AC3",
            "question": "Verify: URL 下载时拒绝内网 IP 及 file:// 协议",
            "min_expectation": "拒绝内网",
            "target_skill": "",
        },
        {
            "id": "FR-002-AC1",
            "question": "Verify: 能提取视频关键帧（至少每 10 秒 1 帧）",
            "min_expectation": "关键帧密度",
            "target_skill": "",
        },
    ]
    routing = {"skill_routing": {"video_ingest": "o", "frame_analyzer": "v"}}
    out, meta = enrich_media_true_test_questions(qs, routing_src=routing)
    assert meta.get("enriched") >= 3
    assert out[0]["execution"] == "skill_invoke"
    assert out[0]["invoke"]["skill"] == "video_ingest"
    assert out[1]["execution"] == "platform_check"
    assert out[2]["invoke"]["skill"] == "frame_analyzer"
    assert any(
        a.get("field") == "keyframe_density_ok" for a in out[2].get("asserts") or []
    )

    raw = json.dumps({"mode": "agent_true_test", "test_questions": qs}, ensure_ascii=False)
    fixed, smeta = sanitize_test_cases_artifact(
        raw,
        architecture_mode="agent",
        test_execution_mode="agent_true_test",
        routing_src=routing,
    )
    obj = json.loads(fixed)
    assert smeta.get("media_invoke_enrich", {}).get("enriched") >= 3
    assert obj["test_questions"][0].get("invoke")


def test_ensure_true_test_suite_quality_caps_ssrf_and_injects_asr():
    from core.harness.execution.factory_artifact_sanitize import (
        ensure_true_test_suite_quality,
        sanitize_test_cases_artifact,
    )

    qs = [
        {
            "id": "TQ-001",
            "category": "异常流程",
            "execution": "platform_check",
            "asserts": [{"type": "platform.ssrf_block", "url": "http://192.168.1.10/a.mp4"}],
        },
        {
            "id": "TQ-002",
            "category": "exception",
            "execution": "platform_check",
            "asserts": [{"type": "platform.ssrf_block", "url": "file:///tmp/x"}],
        },
        {
            "id": "TQ-003",
            "category": "异常流程",
            "execution": "platform_check",
            "asserts": [{"type": "platform.ssrf_block", "url": "http://10.0.0.1/a.mp4"}],
        },
        {
            "id": "TQ-004",
            "category": "正常流程",
            "execution": "skill_invoke",
            "question": "上传本地视频",
            "target_skill": "video_downloader",
            "invoke": {"skill": "video_downloader", "params": {}},
            "asserts": [{"type": "result.contains", "text": "task_id"}],
        },
    ]
    out, meta = ensure_true_test_suite_quality(
        qs,
        speech_pipeline="asr",
        routing_src={
            "skill_routing": {
                "speech_analyzer": "s",
                "report_json_export": "r",
                "video_downloader": "d",
            }
        },
    )
    assert meta.get("trimmed_ssrf") == 1
    assert meta.get("normalized_category") >= 1
    assert sum(1 for q in out if q.get("category") == "exception") == 2
    assert any(q.get("category") == "happy_path" for q in out)
    assert "asr_speech_transcript" in (meta.get("injected") or [])
    assert "asr_report_transcript" in (meta.get("injected") or [])
    assert any(
        "transcript" in json.dumps(q.get("asserts"), ensure_ascii=False)
        for q in out
        if q.get("target_skill") == "speech_analyzer"
    )

    raw = json.dumps({"mode": "agent_true_test", "test_questions": qs}, ensure_ascii=False)
    fixed, smeta = sanitize_test_cases_artifact(
        raw,
        architecture_mode="agent",
        test_execution_mode="agent_true_test",
        prd_src={"decisions": {"speech_pipeline": "asr"}},
        routing_src={"skill_routing": {"speech_analyzer": "s", "report_json_export": "r"}},
    )
    obj = json.loads(fixed)
    assert smeta.get("suite_quality", {}).get("trimmed_ssrf") == 1
    txs = [
        q
        for q in obj["test_questions"]
        if "transcript" in json.dumps(q.get("asserts") or [], ensure_ascii=False)
    ]
    assert len(txs) >= 2


def test_ensure_true_test_suite_quality_features_only_no_transcript_inject():
    from core.harness.execution.factory_artifact_sanitize import ensure_true_test_suite_quality

    qs = [
        {
            "id": "TQ-001",
            "category": "happy_path",
            "execution": "skill_invoke",
            "target_skill": "speech_analyzer",
            "invoke": {"skill": "speech_analyzer", "params": {}},
            "asserts": [{"type": "result.contains", "text": "language"}],
        }
    ]
    out, meta = ensure_true_test_suite_quality(
        qs, speech_pipeline="audio_features_only", routing_src={}
    )
    assert not meta.get("injected")
    assert all(
        "transcript" not in json.dumps(q.get("asserts") or [], ensure_ascii=False)
        for q in out
    )


def test_ensure_agent_app_skill_consistency_renames_qa_and_dedupes():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [{"name": "o", "role": "orchestrator", "skills": ["video_downloader", "speech_analyzer"]}],
  "skill_routing": {"video_downloader": "o", "speech_analyzer": "o"},
  "ui_bindings": {"file_upload": "video_downloader"}
}
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
---
# 多模态问答
根据用户问题返回带 citation 的答案，并 引用时间戳。
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
---
short
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
---
longer speech analyzer body with acoustic labels and asr transcript fields
"""
    out, meta = ensure_agent_app_skill_consistency(raw)
    assert meta.get("renamed", {}).get("video_downloader→video_qa") is True
    assert "skills/video_qa/SKILL.md" in out
    assert "name: video_qa" in out
    assert out.count("skills/speech_analyzer/SKILL.md") == 1
    assert "longer speech analyzer" in out
    assert "video_qa" in out


def test_consistency_keeps_real_downloader_and_merges_speech():
    """QA misfile + real ingest coexist; ASR+acoustic speech_analyzer merge."""
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [{"name": "o", "skills": ["video_downloader", "speech_analyzer"]}],
  "skill_routing": {"video_downloader": "o", "speech_analyzer": "o"},
  "ui_bindings": {"file_upload": "video_downloader"}
}
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
description: 下载与 upload_file / SSRF 校验，仅支持 HTTP video_url
---
ingest
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
---
# 多模态问答
根据用户问题返回带 citation 的答案，并 引用时间戳。
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
description: 视频语音转写技能 ASR transcript
---
asr body
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
description: 视频语音声学分析技能 语种与说话人
---
acoustic body
"""
    out, meta = ensure_agent_app_skill_consistency(raw)
    assert meta.get("renamed", {}).get("video_downloader→video_qa") is True
    assert out.count("skills/video_downloader/SKILL.md") == 1
    assert out.count("skills/video_qa/SKILL.md") == 1
    assert out.count("skills/speech_analyzer/SKILL.md") == 1
    assert "video_qa" in out
    assert '"video_downloader"' in out  # real ingest kept in routing
    assert meta.get("merged_speech") or "语种" in out or "声学" in out
    # glued trailing after JSON must not block manifest parse
    assert "skill_routing" in out


def test_normalize_parses_manifest_with_glued_file_header():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [{"name": "o", "skills": ["video_ingest"]}],
  "skill_routing": {"video_ingest": "o", "video_qa": "o"},
  "ui_bindings": {"file_upload": "video_ingest"}
}
---## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
---
body
"""
    out, meta = normalize_media_skill_names(raw)
    assert meta.get("remapped", {}).get("video_ingest") == "video_downloader"
    assert '"video_downloader"' in out
    assert "video_ingest" not in out or "skills/video_ingest" not in out


def test_normalize_folds_analyze_frames_and_build_timeline():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [
    {"name": "vision_analysis_agent", "skills": ["analyze_frames", "extract_highlights"]},
    {"name": "transcription_agent", "skills": ["speech_analyzer"]},
    {"name": "speech_analysis_agent", "skills": ["speech_analyzer"]},
    {"name": "report_agent", "skills": ["report_json_export", "build_timeline", "video_qa"]}
  ],
  "skill_routing": {
    "analyze_frames": "vision_analysis_agent",
    "extract_highlights": "vision_analysis_agent",
    "speech_analyzer": "speech_analysis_agent",
    "build_timeline": "report_agent",
    "report_json_export": "report_agent",
    "video_qa": "report_agent"
  },
  "ui_bindings": {"result_dashboard": "report_json_export"}
}
## FILE: ~/.aiplat/apps/demo/skills/analyze_frames/SKILL.md
---
name: analyze_frames
---
frames
## FILE: ~/.aiplat/apps/demo/skills/extract_highlights/SKILL.md
---
name: extract_highlights
---
highlights
## FILE: ~/.aiplat/apps/demo/skills/build_timeline/SKILL.md
---
name: build_timeline
---
timeline
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
---
asr
## FILE: ~/.aiplat/apps/demo/skills/report_json_export/SKILL.md
---
name: report_json_export
---
report
"""
    out, nmeta = normalize_media_skill_names(raw)
    assert nmeta.get("remapped", {}).get("analyze_frames") == "frame_analyzer"
    assert nmeta.get("remapped", {}).get("extract_highlights") == "frame_analyzer"
    assert nmeta.get("remapped", {}).get("build_timeline") == "report_json_export"
    out2, cmeta = ensure_agent_app_skill_consistency(out)
    assert "analyze_frames" not in out2 or "skills/analyze_frames" not in out2
    assert out2.count("skills/frame_analyzer/SKILL.md") == 1
    assert out2.count("skills/report_json_export/SKILL.md") == 1
    man = re.search(
        r"(?ms)agent_manifest\.json\s*\n(\{.*?\n\})", out2
    )
    assert man
    obj = json.loads(man.group(1))
    assert "analyze_frames" not in obj["skill_routing"]
    assert obj["skill_routing"].get("frame_analyzer") == "vision_analysis_agent"
    assert obj["skill_routing"].get("speech_analyzer") == "speech_analysis_agent"
    # ownership: transcription_agent should not keep speech_analyzer
    by_name = {a["name"]: a.get("skills") for a in obj["agents"]}
    assert "speech_analyzer" not in (by_name.get("transcription_agent") or [])
    assert "speech_analyzer" in (by_name.get("speech_analysis_agent") or [])


def test_normalize_video_import_and_agent_md_invent_names():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [
    {"name": "orch", "role": "orchestrator", "skills": ["video_import", "report_json_export", "timeline_query"]},
    {"name": "mm", "role": "worker", "skills": ["speech_analyzer", "frame_analyzer"]}
  ],
  "skill_routing": {
    "video_import": "orch",
    "speech_analyzer": "mm",
    "frame_analyzer": "mm",
    "report_json_export": "orch",
    "timeline_query": "orch"
  },
  "ui_bindings": {
    "file_upload": "video_import",
    "progress_poller": "video_downloader",
    "result_dashboard": "report_json_export"
  }
}
## FILE: ~/.aiplat/apps/demo/agents/mm/AGENT.md
---
name: mm
required_skills:
  - video_transcription
  - frame_analyzer
  - speech_analyzer
---
调用 `video_transcription` 与 `speech_analyzer`。
## FILE: ~/.aiplat/apps/demo/skills/video_import/SKILL.md
---
name: video_import
---
ssrf
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
---
download
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
---
asr+acoustic
## FILE: ~/.aiplat/apps/demo/skills/frame_analyzer/SKILL.md
---
name: frame_analyzer
---
frames
## FILE: ~/.aiplat/apps/demo/skills/report_json_export/SKILL.md
---
name: report_json_export
---
report
"""
    out, nmeta = normalize_media_skill_names(raw)
    assert nmeta.get("remapped", {}).get("video_import") == "video_downloader"
    assert nmeta.get("remapped", {}).get("timeline_query") == "report_json_export"
    assert nmeta.get("remapped", {}).get("video_transcription") == "speech_analyzer"
    assert "video_transcription" not in out or "`speech_analyzer`" in out
    out2, cmeta = ensure_agent_app_skill_consistency(out)
    man = re.search(r"(?ms)agent_manifest\.json\s*\n(\{.*?\n\})", out2)
    assert man
    obj = json.loads(man.group(1))
    assert "video_import" not in obj["skill_routing"]
    assert obj["skill_routing"].get("video_downloader") == "orch"
    assert obj["ui_bindings"].get("file_upload") == "video_downloader"
    assert obj["ui_bindings"].get("progress_poller") == "report_json_export"
    assert "skills/video_import/" not in out2


def test_ensure_platform_media_skill_contracts_rewrites_import_only_downloader():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{"app_name":"demo","agents":[{"name":"o","skills":["video_downloader"]}],"skill_routing":{"video_downloader":"o"},"ui_bindings":{}}
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
description: 校验合法性并创建分析任务，返回 task_id 与 PENDING 状态。写入审计日志。
---
# 视频导入
核心处理：生成 task_id，status=PENDING，不创建任务以外的下载。
output_schema:
  task_id:
    type: string
  status:
    type: string
## FILE: ~/.aiplat/apps/demo/skills/report_json_export/SKILL.md
---
name: report_json_export
description: 按 task_id 查询视频理解任务的当前阶段。当用户询问任务进度或处理到哪一步时触发。
---
output_schema:
  task_id:
    type: string
  current_stage:
    type: string
  block_status:
    type: object
"""
    out, meta = ensure_platform_media_skill_contracts(raw)
    assert "video_downloader" in (meta.get("rewritten") or [])
    assert "report_json_export" in (meta.get("rewritten") or [])
    assert "media_ref" in out
    assert "segments" in out
    assert "duration_seconds" in out
    assert "timeline" in out
    assert "report_path" in out
    assert "download_status" in out
    assert "task_status" in out
    assert "仅进度" not in out or "汇聚" in out


def test_apply_consistency_runs_with_normalize_gate():
    stage = SimpleNamespace(
        architecture_mode="agent",
        test_execution_mode="",
        input_artifacts=[],
        quality_gate={"normalize_media_skill_names": True},
    )
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{"app_name":"demo","agents":[{"name":"o","skills":["video_downloader"]}],"skill_routing":{"video_downloader":"o"},"ui_bindings":{"file_upload":"video_downloader"}}
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: wrong_name
---
# 多模态问答
citation + 引用时间戳 回答
"""
    out, art, meta = apply_stage_output_sanitizers(
        stage=stage, state={}, result=raw, elapsed_sec=0.1
    )
    assert "ensure_agent_app_skill_consistency" in meta
    assert "video_qa" in out
    assert "name: video_qa" in out


def test_drop_task_lifecycle_and_rewrite_required_task_id_contracts():
    raw = """## FILE: ~/.aiplat/apps/demo/agent_manifest.json
{
  "app_name": "demo",
  "agents": [
    {"name": "orch", "role": "orchestrator", "skills": ["task_lifecycle"]},
    {"name": "dl", "role": "worker", "skills": ["video_downloader"]},
    {"name": "sp", "role": "worker", "skills": ["speech_analyzer"]},
    {"name": "rep", "role": "worker", "skills": ["report_json_export"]}
  ],
  "skill_routing": {
    "task_lifecycle": "orch",
    "video_downloader": "dl",
    "speech_analyzer": "sp",
    "report_json_export": "rep"
  },
  "ui_bindings": {
    "file_upload": "video_downloader",
    "progress_poller": "task_lifecycle",
    "result_dashboard": "report_json_export"
  }
}
## FILE: ~/.aiplat/apps/demo/skills/task_lifecycle/SKILL.md
---
name: task_lifecycle
---
create/query tasks
## FILE: ~/.aiplat/apps/demo/skills/video_downloader/SKILL.md
---
name: video_downloader
---
input_schema:
  task_id:
    type: string
    required: true
  source_type:
    type: string
    required: true
output_schema:
  media_ref:
    type: string
  duration_seconds:
    type: number
  segments:
    type: array
  download_status:
    type: string
## FILE: ~/.aiplat/apps/demo/skills/speech_analyzer/SKILL.md
---
name: speech_analyzer
---
input_schema:
  task_id:
    type: string
    required: true
  duration_seconds:
    type: number
    required: true
  tenant_id:
    type: string
    required: true
  media_ref:
    type: string
    required: true
output_schema:
  transcript:
    type: string
## FILE: ~/.aiplat/apps/demo/skills/report_json_export/SKILL.md
---
name: report_json_export
---
input_schema:
  task_id:
    type: string
    required: true
  tenant_id:
    type: string
    required: true
output_schema:
  report:
    type: object
  timeline:
    type: array
  report_path:
    type: string
"""
    out, cmeta = ensure_agent_app_skill_consistency(raw)
    assert "task_lifecycle" in (cmeta.get("dropped_lifecycle_skills") or [])
    assert "skills/task_lifecycle/" not in out
    out2, pmeta = ensure_platform_media_skill_contracts(out)
    assert "video_downloader" in (pmeta.get("rewritten") or [])
    assert "speech_analyzer" in (pmeta.get("rewritten") or [])
    assert "report_json_export" in (pmeta.get("rewritten") or [])
    # rewritten contracts: task_id not required on ingress
    assert re.search(
        r"(?ms)name: video_downloader.*?input_schema:.*?task_id:.*?required:\s*false",
        out2,
    )
    assert re.search(
        r"(?ms)name: speech_analyzer.*?input_schema:.*?duration_seconds:.*?required:\s*false",
        out2,
    )
    man = re.search(r"(?ms)agent_manifest\.json\s*\n(\{.*?\n\})", out2)
    assert man
    obj = json.loads(man.group(1))
    assert "task_lifecycle" not in (obj.get("skill_routing") or {})
    assert obj.get("ui_bindings", {}).get("progress_poller") == "report_json_export"



def test_load_canonical_media_skill_md_from_seeds():
    """F5b: canonical SKILL bodies load from workspace_seeds/factory_sanitize."""
    for name in (
        "frame_analyzer",
        "speech_analyzer",
        "video_downloader",
        "report_json_export",
    ):
        body = load_canonical_media_skill_md(name, "demo_app")
        assert f"name: {name}" in body
        assert "demo_app" in body
        assert "{{app_name}}" not in body
        assert "execution_type:" in body
        assert "input_schema:" in body
        assert "output_schema:" in body


def test_load_canonical_media_skill_md_unknown_raises():
    import pytest

    with pytest.raises(ValueError, match="unknown canonical"):
        load_canonical_media_skill_md("not_a_skill", "x")


def test_canonical_video_downloader_has_segments_contract():
    body = load_canonical_media_skill_md("video_downloader", "media_x")
    assert "media_ref" in body
    assert "segments" in body
    assert "download_status" in body
    assert "~/.aiplat/apps/media_x/tasks" in body
