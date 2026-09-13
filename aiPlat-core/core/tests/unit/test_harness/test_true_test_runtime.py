"""Unit tests for factory true-test runtime (platform_check / classify / precheck)."""

from __future__ import annotations

import json

import pytest

from core.harness.execution.true_test_runtime import (
    check_file_rules,
    check_wizard_stage_io,
    classify_execution,
    deterministic_precheck_from_params,
    evaluate_result_asserts,
    is_blocked_url,
    run_page_smoke,
    run_platform_check,
    run_true_test_case,
)


def test_ssrf_blocks_private_and_file():
    assert is_blocked_url("http://192.168.1.10/a.mp4")[0] is True
    assert is_blocked_url("file:///etc/passwd")[0] is True
    assert is_blocked_url("https://example.com/v.mp4")[0] is False


def test_file_rules_from_case_not_product():
    ok, _ = check_file_rules(
        file_name="x.exe",
        file_size=10,
        allowed_extensions=["mp4", "mov"],
        max_bytes=100,
    )
    assert ok is False
    ok2, _ = check_file_rules(
        file_name="a.mp4",
        file_size=50,
        allowed_extensions=["mp4"],
        max_bytes=100,
    )
    assert ok2 is True
    ok3, _ = check_file_rules(file_name="big.mp4", file_size=200, max_bytes=100)
    assert ok3 is False


def test_classify_execution_priority():
    assert classify_execution({"execution": "platform_check"}) == "platform_check"
    assert (
        classify_execution({"invoke": {"skill": "s", "params": {}}, "question": "q"})
        == "skill_invoke"
    )
    assert classify_execution({"asserts": [{"type": "platform.ssrf_block"}]}) == "platform_check"
    assert classify_execution({"question": "hi", "min_expectation": "ok"}) == "conversation"


def test_run_platform_check_ssrf():
    out = run_platform_check(
        {
            "asserts": [
                {
                    "type": "platform.ssrf_block",
                    "url": "http://127.0.0.1/x",
                    "expect_blocked": True,
                }
            ]
        }
    )
    assert out["ok"] is True
    assert out["result"] == "PASS"


def test_deterministic_precheck_url():
    pre = deterministic_precheck_from_params({"url": "http://10.0.0.1/a"})
    assert pre is not None
    assert pre["status"] == "failed"
    assert "ssrf" in pre["error_message"]
    assert deterministic_precheck_from_params({"url": "https://example.com/a"}) is None


@pytest.mark.asyncio
async def test_skill_invoke_precheck_short_circuits_llm():
    case = {
        "id": "TQ-X",
        "execution": "skill_invoke",
        "invoke": {
            "skill": "any_download",
            "params": {"url": "http://192.168.0.5/v.mp4", "task_id": "t1"},
        },
        "asserts": [
            {"type": "result.field_equals", "path": "status", "equals": "failed"},
        ],
    }
    out = await run_true_test_case(case, agent_app="", frontend_pages=None)
    assert out["mode"] == "skill_invoke_precheck"
    assert out["result"] == "PASS"
    assert out["invoke"]["result"]["status"] == "failed"


def test_evaluate_result_asserts():
    ok, fails, _ = evaluate_result_asserts(
        {"status": "pending"},
        [{"type": "result.status_in", "in": ["pending", "failed"]}],
    )
    assert ok is True
    ok2, fails2, _ = evaluate_result_asserts(
        {"raw": "hello"},
        [{"type": "result.contains", "text": "missing"}],
        reply_text="hello",
    )
    assert ok2 is False
    assert fails2


def test_field_equals_soft_count_and_latency():
    from core.harness.execution.true_test_runtime import enrich_media_invoke_from_asserts

    ok, _, ev = evaluate_result_asserts(
        {"keyframe_count": 8},
        [{"type": "result.field_equals", "field": "keyframes_count", "value": 6}],
    )
    assert ok is True
    assert any("field_eq" in x for x in ev)

    ok2, fails2, _ = evaluate_result_asserts(
        {"keyframe_count": 3},
        [{"type": "result.field_equals", "field": "keyframes_count", "value": 6}],
    )
    assert ok2 is False
    assert fails2

    ok3, _, _ = evaluate_result_asserts(
        {"load_time_ms": 120},
        [{"type": "result.field_equals", "field": "load_time_ms", "value": 2000}],
    )
    assert ok3 is True

    ok4, fails4, _ = evaluate_result_asserts(
        {"load_time_ms": 5000},
        [{"type": "result.field_equals", "field": "load_time_ms", "value": 2000}],
    )
    assert ok4 is False
    assert fails4

    enriched = enrich_media_invoke_from_asserts(
        {"video_path": "/tmp/media/with_audio.mp4"},
        [
            {"type": "result.field_equals", "field": "keyframes_count", "value": 6},
            {"type": "result.contains", "text": "-->"},
        ],
        skill="subtitle_extractor",
    )
    assert enriched.get("claimed_duration") == 60.0
    assert "with_subtitle" in str(enriched.get("video_path") or "")


def test_frame_analyzer_caption_only_and_keyframes_count_alias():
    from core.harness.media_skill_handlers import execute_media_skill

    r = execute_media_skill(
        "frame_analyzer",
        {
            "app_name": "media",
            "keyframes": [
                {"timestamp": 0, "image_path": "/tmp/frames/a.jpg"},
                {"timestamp": 10, "image_path": "/tmp/frames/b.jpg"},
            ],
            "task_id": "task-001",
        },
    )
    assert "description" in json.dumps(r, ensure_ascii=False)
    assert r.get("keyframes_count") == 2
    assert r.get("description")


def test_report_export_emits_load_time_ms():
    from core.harness.media_skill_handlers import execute_media_skill

    r = execute_media_skill(
        "report_json_export",
        {"app_name": "media", "task_id": "task-001", "performance_check": True},
    )
    assert isinstance(r.get("load_time_ms"), int)
    assert r["load_time_ms"] > 0
    ok, _, _ = evaluate_result_asserts(
        r,
        [{"type": "result.field_equals", "field": "load_time_ms", "value": 2000}],
    )
    assert ok is True


def test_export_format_contains_accepts_export_json_synonym():
    ok, fails, ev = evaluate_result_asserts(
        {"task_id": "t1", "export_json": True},
        [{"type": "result.contains", "text": "export_format"}],
    )
    assert ok is True
    assert not fails
    assert any("export_json" in x or "export_format" in x for x in ev)


def test_captions_contains_accepts_descriptions_synonym_and_handler_field():
    from core.harness.media_skill_handlers import execute_media_skill

    ok, fails, ev = evaluate_result_asserts(
        {"descriptions": ["scene=a subject=b action=c"]},
        [{"type": "result.contains", "text": "captions"}],
    )
    assert ok is True and not fails
    assert any("descriptions" in x or "captions" in x for x in ev)

    r = execute_media_skill(
        "frame_analyzer",
        {"app_name": "media", "video_path": "/tmp/videos/t-001.mp4"},
    )
    assert r.get("captions")
    ok2, fails2, _ = evaluate_result_asserts(
        r, [{"type": "result.contains", "text": "captions"}]
    )
    assert ok2 is True and not fails2


def test_sanitize_preserves_true_test_mode():
    from core.harness.execution.factory_artifact_sanitize import sanitize_test_cases_artifact

    raw = json.dumps(
        {
            "mode": "agent_true_test",
            "test_questions": [
                {
                    "id": "TQ-1",
                    "execution": "platform_check",
                    "asserts": [{"type": "platform.ssrf_block", "url": "file://x"}],
                }
            ],
        },
        ensure_ascii=False,
    )
    out, meta = sanitize_test_cases_artifact(
        raw, architecture_mode="agent", test_execution_mode="agent_true_test"
    )
    obj = json.loads(out)
    assert obj["mode"] == "agent_true_test"
    assert obj["test_questions"][0]["execution"] == "platform_check"
    assert meta["mode"] == "agent_true_test"


def test_suggest_platform_media_skill_catalog():
    from core.harness.media_skill_handlers import (
        list_platform_media_skill_names,
        resolve_media_handler_name,
        resolve_platform_media_skill,
        suggest_platform_media_skill,
    )

    cat = list_platform_media_skill_names()
    assert "video_downloader" in cat["canonical"]
    assert resolve_platform_media_skill("keyframe_extract") == "frame_analyzer"
    assert resolve_platform_media_skill("keyframe_extraction") == "frame_analyzer"
    assert resolve_media_handler_name("keyframe_extraction") == "frame_analyzer"
    assert resolve_media_handler_name("subtitle_track_extraction") == "subtitle_extractor"
    assert suggest_platform_media_skill("video_fetch") == "video_downloader"
    assert suggest_platform_media_skill("auth_login") is None
    assert resolve_media_handler_name("video_qa") is None
    assert suggest_platform_media_skill("video_qa") is None
    assert resolve_media_handler_name("content_qa") is None
    assert resolve_media_handler_name("analyze_frames") == "frame_analyzer"
    assert resolve_media_handler_name("extract_highlights") == "frame_analyzer"
    assert resolve_media_handler_name("build_timeline") == "report_json_export"
    assert resolve_media_handler_name("video_import") == "video_downloader"
    assert resolve_media_handler_name("video_transcription") == "speech_analyzer"
    assert resolve_media_handler_name("timeline_query") == "report_json_export"


def test_build_true_test_report_emits_no_platform_handler_bugs():
    from core.engine.skills.test_executor.handler import _build_true_test_report

    report = _build_true_test_report(
        [
            {
                "id": "TQ-1",
                "result": "SKIP",
                "evidence": "no_platform_handler:video_fetch; suggested_platform_skill:video_downloader; prompt_skill_skip",
                "diagnostics": [
                    "no_platform_handler:video_fetch",
                    "suggested_platform_skill:video_downloader",
                ],
                "question": "invoke video_fetch",
            }
        ],
        project="demo",
        today="2026-09-08",
    )
    assert report["meta"]["diagnostics"]
    assert report["meta"]["diagnostics"][0]["code"] == "no_platform_handler"
    assert report["recommendation"] == "NEEDS_FIX"
    assert any(b.get("diagnostic") == "no_platform_handler" for b in report["bug_summary"]["bugs"])


def test_build_true_test_report_ignores_prompt_only_video_qa():
    from core.engine.skills.test_executor.handler import _build_true_test_report

    report = _build_true_test_report(
        [
            {
                "id": "TQ-017",
                "result": "SKIP",
                "evidence": "no_platform_handler:video_qa; prompt_skill_skip_structured_asserts:video_qa; missing:answer",
                "diagnostics": ["no_platform_handler:video_qa"],
                "question": "ask about video",
            },
            {
                "id": "TQ-018",
                "result": "PASS",
                "evidence": "prompt_only_skill_soft_pass:video_qa; missing:answer",
                "question": "ask again",
            },
        ],
        project="demo",
        today="2026-09-10",
    )
    assert report["meta"]["diagnostics"] == []
    assert report["bug_summary"]["total_bugs"] == 0
    assert report["recommendation"] == "APPROVED"

def test_video_download_accepts_source_url_and_upload_file_path():
    from core.harness.media_skill_handlers import execute_media_skill

    r1 = execute_media_skill(
        "video_download",
        {"app_name": "videosense", "source_url": "https://example.com/video.mp4"},
    )
    assert r1.get("status") in ("ready", "pending", "completed")
    assert r1.get("video_path")
    assert r1.get("metadata") or r1.get("video_metadata")

    r2 = execute_media_skill(
        "video_download",
        {"app_name": "videosense", "upload_file_path": "/tmp/uploads/user_video.mp4"},
    )
    assert r2.get("status") in ("ready", "pending", "completed")
    assert r2.get("video_path")


def test_task_decomposition_alias_and_ingress_asserts():
    from core.harness.media_skill_handlers import (
        execute_media_skill,
        resolve_media_handler_name,
    )

    assert resolve_media_handler_name("task_decomposition") == "video_downloader"

    clarify = execute_media_skill(
        "task_decomposition",
        {"app_name": "videosense", "user_intent": "帮我分析视频内容"},
    )
    assert clarify.get("status") == "clarify"
    assert "请提供视频链接或上传视频文件" in json.dumps(clarify, ensure_ascii=False)

    ftp = execute_media_skill(
        "video_downloader",
        {"app_name": "videosense", "video_url": "ftp://example.com/video.mp4"},
    )
    assert ftp.get("status") == "failed"
    assert "仅支持 HTTP/HTTPS" in str(ftp.get("error_message") or "")

    txt = execute_media_skill(
        "video_downloader",
        {"app_name": "videosense", "local_path": "/tmp/uploads/notes.txt"},
    )
    assert txt.get("status") == "failed"
    assert "不支持的文件格式" in str(txt.get("error_message") or "")

    ok = execute_media_skill(
        "task_decomposition",
        {
            "app_name": "videosense",
            "user_intent": "分析",
            "local_path": "/tmp/uploads/sample.mp4",
        },
    )
    assert ok.get("task_id")
    assert ok.get("status") in ("pending", "completed", "ready")
    blob = json.dumps(ok, ensure_ascii=False)
    assert ok.get("status") in blob


def test_frame_analyzer_density_and_corrupt_error():
    from core.harness.media_skill_handlers import execute_media_skill
    from core.harness.execution.true_test_runtime import evaluate_result_asserts

    dens = execute_media_skill(
        "frame_analyzer",
        {
            "app_name": "videosense",
            "video_path": "/tmp/videos/t-v-002_100s.mp4",
        },
    )
    assert dens.get("keyframe_density_ok") is True
    assert int(dens.get("keyframe_count") or 0) >= 10

    bad = execute_media_skill(
        "frame_analyzer",
        {"app_name": "videosense", "video_path": "/media/corrupt.mp4"},
    )
    assert bad.get("status") == "failed"
    ok, fails, _ = evaluate_result_asserts(
        bad, [{"type": "contains", "text": "error"}]
    )
    assert ok is True
    assert not fails


def _broken_wizard_page() -> dict:
    return {
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
                "skill": "report_json_export",
                "config": {"input": {"task_id": "{{progress.task_id}}"}},
            },
        ],
    }


def _good_wizard_page() -> dict:
    page = _broken_wizard_page()
    by_id = {s["id"]: s for s in page["stages"]}
    by_id["source"]["config"]["fields"][1]["show_when"] = {"source_type": "url"}
    by_id["progress"]["skill"] = "report_json_export"
    by_id["progress"]["config"]["input"] = {
        "task_id": "{{upload.task_id}}",
        "video_path": "{{upload.video_path}}",
    }
    by_id["results"]["config"]["input"] = {
        "task_id": "{{progress.task_id}}",
        "video_path": "{{progress.video_path}}",
    }
    by_id["results"]["config"]["sections"] = [
        {"key": "metadata", "label": "元数据", "type": "key_value"},
        {"key": "keyframes", "label": "关键帧", "type": "image_timeline"},
        {"key": "summary", "label": "摘要", "type": "markdown"},
    ]
    return page


def test_check_result_dashboard_sections_rejects_unsupported_types():
    from core.harness.execution.true_test_runtime import check_result_dashboard_sections

    bad = {
        "id": "results",
        "component": "result_dashboard",
        "config": {
            "sections": [
                {"key": "frames", "label": "帧", "type": "fancy_card"},
                {"key": "meta", "label": "元", "type": "key_value"},
            ]
        },
    }
    ok, fails, _ = check_result_dashboard_sections(bad)
    assert ok is False
    assert any("result_section_type_unsupported:fancy_card" in f for f in fails)

    good = {
        "id": "results",
        "component": "result_dashboard",
        "config": {
            "sections": [
                {"key": "keyframes", "label": "帧", "type": "image_timeline"},
                {"key": "summary", "label": "摘要", "type": "markdown"},
            ]
        },
    }
    ok2, fails2, ev = check_result_dashboard_sections(good)
    assert ok2 is True
    assert fails2 == []
    assert "result_sections:ok" in ev


def test_check_wizard_stage_io_fails_preview_regressions():
    bindings = {
        "file_upload": "video_downloader",
        "data_form": "video_downloader",
        "progress_poller": "video_downloader",
        "result_dashboard": "report_json_export",
    }
    ok, fails, _ = check_wizard_stage_io(_broken_wizard_page(), ui_bindings=bindings)
    assert ok is False
    joined = " ".join(fails)
    assert "show_when" in joined
    assert "progress_skill_is_ingest" in joined
    assert "progress_missing_input:path" in joined
    assert "results_missing_input:path" in joined

    ok2, fails2, ev = check_wizard_stage_io(_good_wizard_page(), ui_bindings=bindings)
    assert ok2 is True
    assert fails2 == []
    assert "wizard_io:ok" in ev


@pytest.mark.asyncio
async def test_page_smoke_fails_broken_wizard_passes_repaired():
    agent_app = json.dumps(
        {
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
    )
    case = {
        "execution": "page_smoke",
        "invoke_skills": False,
        "asserts": [{"type": "stage.wizard_io_ok"}],
    }
    bad = await run_page_smoke(
        frontend_pages=json.dumps(_broken_wizard_page()),
        agent_app=agent_app,
        case=case,
        invoke_skills=False,
    )
    assert bad["ok"] is False
    assert bad["result"] == "FAIL"
    assert any("progress_skill_is_ingest" in f for f in bad["failures"])
    assert "assert:stage.wizard_io_ok:failed" in bad["failures"]

    good = await run_page_smoke(
        frontend_pages=json.dumps(_good_wizard_page()),
        agent_app=agent_app,
        case=case,
        invoke_skills=False,
    )
    assert good["ok"] is True
    assert good["result"] == "PASS"
    assert "assert:stage.wizard_io_ok:ok" in (good.get("evidence") or "")


@pytest.mark.asyncio
async def test_run_true_test_case_page_smoke_wizard_gate():
    agent_app = json.dumps(
        {
            "skill_routing": {"video_downloader": "o", "report_json_export": "o"},
            "ui_bindings": {
                "file_upload": "video_downloader",
                "result_dashboard": "report_json_export",
            },
        }
    )
    out = await run_true_test_case(
        {
            "id": "TQ-PAGE-WIZARD-IO",
            "execution": "page_smoke",
            "invoke_skills": False,
            "asserts": [{"type": "stage.wizard_io_ok"}],
        },
        agent_app=agent_app,
        frontend_pages=json.dumps(_broken_wizard_page()),
    )
    assert out["ok"] is False


def test_enrich_media_injects_wizard_io_page_smoke():
    from core.harness.execution.factory_artifact_sanitize import (
        enrich_media_true_test_questions,
        ensure_wizard_io_true_test_case,
    )

    qs = [
        {
            "id": "FR-001",
            "question": "Verify 视频下载 URL",
            "min_expectation": "ok",
        }
    ]
    routing = {
        "video_downloader": "orch",
        "frame_analyzer": "orch",
        "report_json_export": "orch",
    }
    out, meta = enrich_media_true_test_questions(qs, routing_src=routing)
    assert meta.get("injected_wizard_io") is True
    wizard = next(q for q in out if q.get("id") == "TQ-PAGE-WIZARD-IO")
    assert wizard["execution"] == "page_smoke"
    assert any(
        a.get("type") == "stage.wizard_io_ok" for a in wizard.get("asserts") or []
    )
    assert any(
        a.get("type") == "stage.result_sections_ok" for a in wizard.get("asserts") or []
    )

    # Non-media wizard (procurement-style bindings) also gets the gate
    out2, meta2 = ensure_wizard_io_true_test_case(
        [{"id": "T1", "question": "x", "execution": "skill_invoke"}],
        ui_bindings={
            "file_upload": "doc_ingest",
            "result_dashboard": "doc_report",
            "progress_poller": "doc_ingest",
        },
    )
    assert meta2.get("injected_wizard_io") is True
    assert any(q.get("id") == "TQ-PAGE-WIZARD-IO" for q in out2)
