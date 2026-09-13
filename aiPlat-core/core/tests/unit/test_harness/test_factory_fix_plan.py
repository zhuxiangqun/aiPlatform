"""Unit tests for deterministic Factory fix planning."""

from __future__ import annotations

from core.harness.execution.factory_fix_plan import (
    derive_failed_stages_from_report,
    filter_fix_plan_freeze_test_cases,
    plan_fix_from_report,
)


TEAM = [
    {"agent_id": "pm_agent", "output_artifact": "prd"},
    {"agent_id": "architect_agent", "output_artifact": "architecture"},
    {"agent_id": "programmer_agent", "output_artifact": "code"},
    {"agent_id": "agent_engineer", "output_artifact": "agent_app"},
    {"agent_id": "frontend_developer", "output_artifact": "frontend_pages"},
    {"agent_id": "qa_agent", "output_artifact": "test_cases"},
    {"agent_id": "test_executor", "output_artifact": "test_report", "skill_name": "test_executor"},
]


def test_filter_fix_plan_freezes_qa_by_default():
    plan = ["agent_engineer", "frontend_developer", "qa_agent", "test_executor"]
    frozen = filter_fix_plan_freeze_test_cases(plan, TEAM)
    assert "qa_agent" not in frozen
    assert "agent_engineer" in frozen
    assert "test_executor" in frozen
    assert filter_fix_plan_freeze_test_cases(
        plan, TEAM, regenerate_test_cases=True
    ) == plan


def test_plan_fix_preserves_test_cases_by_default():
    report = {
        "bug_summary": {
            "total_bugs": 1,
            "bugs": [
                {
                    "id": "BUG-001",
                    "test_id": "TQ-1",
                    "execution": "page_smoke",
                    "suggested_fix": "按 asserts/execution=page_smoke 修复；failures=['ui_bindings_mismatch']",
                }
            ],
        }
    }
    plan = plan_fix_from_report("run1", report, TEAM)
    assert plan.get("status") == "ok"
    assert plan.get("mode") != "deterministic_media_remap"
    assert "qa_agent" not in (plan.get("fix_plan") or [])
    assert "test_cases" in (plan.get("preserve_artifacts") or [])
    assert plan.get("regenerate_test_cases") is False

    plan2 = plan_fix_from_report(
        "run1", report, TEAM, regenerate_test_cases=True
    )
    assert plan2.get("regenerate_test_cases") is True
    assert plan2.get("preserve_artifacts") == []


def test_derive_page_smoke_maps_frontend_and_agent_app():
    report = {
        "bug_summary": {
            "total_bugs": 1,
            "bugs": [
                {
                    "id": "BUG-001",
                    "test_id": "TQ-017",
                    "suggested_fix": "按 asserts/execution=page_smoke 修复；failures=['ui_bindings_mismatch']",
                }
            ],
        }
    }
    got = derive_failed_stages_from_report(report, TEAM)
    assert "frontend_developer" in got
    assert "agent_engineer" in got


def test_derive_skill_invoke_maps_agent_app():
    report = {
        "bug_summary": {
            "total_bugs": 2,
            "bugs": [
                {
                    "suggested_fix": "按 asserts/execution=skill_invoke 修复对应 Skill；failures=['missing:x']",
                },
                {
                    "execution": "conversation",
                    "suggested_fix": "未返回统一报告",
                },
            ],
        }
    }
    got = derive_failed_stages_from_report(report, TEAM)
    assert got == ["agent_engineer"]


def test_derive_pytest_maps_code():
    report = {
        "test_mode": "pytest",
        "bug_summary": {"total_bugs": 3, "failed_tests": ["t1"], "suggested_fix": "fix imports"},
    }
    assert derive_failed_stages_from_report(report, TEAM) == ["programmer_agent"]


def test_derive_platform_check_skipped():
    report = {
        "bug_summary": {
            "bugs": [
                {"execution": "platform_check", "suggested_fix": "SSRF"},
            ]
        }
    }
    assert derive_failed_stages_from_report(report, TEAM) == []


def test_plan_fix_no_bugs():
    out = plan_fix_from_report("run_x", {"bug_summary": {"total_bugs": 0, "bugs": []}}, TEAM)
    assert out["status"] == "no_bugs"


def test_derive_no_platform_handler_maps_agent_app():
    report = {
        "meta": {
            "diagnostics": [
                {
                    "code": "no_platform_handler",
                    "skill": "video_fetch",
                    "suggested_platform_skill": "video_downloader",
                    "suggested_fix": "rename",
                }
            ]
        },
        "bug_summary": {
            "total_bugs": 1,
            "bugs": [
                {
                    "diagnostic": "no_platform_handler",
                    "title": "平台无 handler: video_fetch",
                    "actual": "no_platform_handler:video_fetch; suggested_platform_skill:video_downloader",
                    "suggested_fix": "将 Skill `video_fetch` 重命名为 `video_downloader`",
                }
            ],
        },
    }
    got = derive_failed_stages_from_report(report, TEAM)
    assert got == ["agent_engineer"]


def test_plan_no_platform_handler_uses_deterministic_remap():
    from core.harness.execution.factory_fix_plan import (
        apply_no_platform_handler_fixes,
        bugs_are_no_platform_handler_only,
        extract_media_skill_remaps_from_report,
    )

    report = {
        "bug_summary": {
            "total_bugs": 2,
            "bugs": [
                {
                    "diagnostic": "no_platform_handler",
                    "title": "平台无 handler: keyframe_extraction",
                    "actual": "no_platform_handler:keyframe_extraction; suggested_platform_skill:frame_analyzer",
                    "suggested_fix": "将 Skill `keyframe_extraction` 重命名为 `frame_analyzer`",
                },
                {
                    "diagnostic": "no_platform_handler",
                    "title": "平台无 handler: report_assembly",
                    "actual": "no_platform_handler:report_assembly; suggested_platform_skill:report_json_export",
                },
            ],
        }
    }
    assert bugs_are_no_platform_handler_only(report) is True
    remaps = extract_media_skill_remaps_from_report(report)
    assert remaps["keyframe_extraction"] == "frame_analyzer"
    assert remaps["report_assembly"] == "report_json_export"

    plan = plan_fix_from_report("run_x", report, TEAM)
    assert plan["mode"] == "deterministic_media_remap"
    assert plan["fix_plan"] == ["test_executor"]

    tc = {
        "mode": "agent_true_test",
        "test_questions": [
            {"id": "TQ-1", "invoke": {"skill": "keyframe_extraction", "params": {}}},
            {"id": "TQ-2", "target_skill": "report_assembly"},
        ],
    }
    out = apply_no_platform_handler_fixes(
        agent_app_raw="## FILE: x/agent_manifest.json\n{\"skill_routing\":{\"keyframe_extraction\":\"o\"}}\n",
        test_cases=tc,
        test_report=report,
        remaps=remaps,
    )
    assert out["meta"]["test_cases_changed"] >= 1
    assert out["test_cases"]["test_questions"][0]["invoke"]["skill"] == "frame_analyzer"


def test_plan_skill_invoke_media_fail_uses_deterministic_remap():
    from core.harness.execution.factory_fix_plan import bugs_are_media_handler_fixable

    report = {
        "bug_summary": {
            "total_bugs": 2,
            "bugs": [
                {
                    "title": "测真未通过: TQ-005",
                    "suggested_fix": "按 asserts/execution=skill_invoke 修复；failures=['missing:video_path']",
                },
                {
                    "title": "测真未通过: TQ-007",
                    "suggested_fix": "failures=['missing:keyframes', 'missing:scene_changes']",
                },
            ],
        }
    }
    assert bugs_are_media_handler_fixable(report) is True
    plan = plan_fix_from_report("run_y", report, TEAM)
    assert plan["mode"] == "deterministic_media_remap"
    assert plan["fix_plan"] == ["test_executor"]


def test_normalize_source_url_and_upload_file_path_aliases():
    from core.harness.execution.factory_fix_plan import normalize_true_test_media_params

    raw = {
        "test_questions": [
            {
                "id": "TQ-A",
                "invoke": {
                    "skill": "video_download",
                    "params": {"source_url": "https://example.com/video.mp4"},
                },
            },
            {
                "id": "TQ-B",
                "invoke": {
                    "skill": "video_download",
                    "params": {"upload_file_path": "/tmp/uploads/user_video.mp4"},
                },
            },
        ]
    }
    out, n = normalize_true_test_media_params(raw)
    assert n >= 1
    p0 = out["test_questions"][0]["invoke"]["params"]
    p1 = out["test_questions"][1]["invoke"]["params"]
    assert p0.get("url") or p0.get("file_path") or p0.get("video_path")
    assert p1.get("file_path") or p1.get("video_path")


def test_apply_media_fix_preserves_question_text():
    from core.harness.execution.factory_fix_plan import apply_no_platform_handler_fixes

    q_text = "用户输入公网 HTTPS 视频直链，系统应成功下载并返回本地文件路径"
    tc = {
        "test_questions": [
            {
                "id": "TQ-005",
                "question": q_text,
                "invoke": {
                    "skill": "video_download",
                    "params": {"source_url": "https://example.com/video.mp4"},
                },
            }
        ]
    }
    out = apply_no_platform_handler_fixes(
        agent_app_raw="## FILE: a/AGENT.md\nname: a\n",
        test_cases=tc,
        test_report={"bug_summary": {"bugs": []}},
        remaps={},
    )
    assert out["test_cases"]["test_questions"][0]["question"] == q_text
    assert out["test_cases"]["test_questions"][0]["id"] == "TQ-005"

def test_align_export_format_assert_for_one_click():
    from core.harness.execution.factory_fix_plan import (
        align_result_assert_needles,
        apply_no_platform_handler_fixes,
        bugs_are_media_handler_fixable,
        plan_fix_from_report,
    )

    report = {
        "bug_summary": {
            "total_bugs": 1,
            "bugs": [
                {
                    "title": "测真未通过: TQ-023",
                    "suggested_fix": "按 asserts/execution=skill_invoke 修复；failures=['missing:export_format']",
                }
            ],
        }
    }
    assert bugs_are_media_handler_fixable(report) is True
    plan = plan_fix_from_report("run_z", report, TEAM)
    assert plan["mode"] == "deterministic_media_remap"

    tc = {
        "test_questions": [
            {
                "id": "TQ-023",
                "asserts": [
                    {"type": "result.contains", "text": "task_id"},
                    {"type": "result.contains", "text": "export_format"},
                ],
                "invoke": {"skill": "report_json_export", "params": {"task_id": "t1"}},
            }
        ]
    }
    aligned, n = align_result_assert_needles(tc, report)
    assert n == 1
    assert aligned["test_questions"][0]["asserts"][1]["text"] == "export_json"

    out = apply_no_platform_handler_fixes(
        agent_app_raw="",
        test_cases=tc,
        test_report=report,
        remaps={},
    )
    assert out["meta"].get("asserts_aligned", 0) >= 1
    assert out["test_cases"]["test_questions"][0]["asserts"][1]["text"] == "export_json"


def test_report_handler_emits_export_format(tmp_path, monkeypatch):
    from core.harness import media_ops
    from core.harness.media_skill_handlers import handle_report_json_export

    monkeypatch.setattr(media_ops, "storage_root", lambda app: tmp_path / str(app))
    monkeypatch.setattr(
        "core.harness.media_skill_handlers.storage_root",
        lambda app: tmp_path / str(app),
    )
    # Avoid ffmpeg fixture writes under ~/.aiplat
    monkeypatch.setattr(
        "core.harness.media_skill_handlers.handle_frame_analyzer",
        lambda p: {
            "keyframes": [{"timestamp": 0.0}],
            "scene_changes": [1.0],
            "video_metadata": {"duration": 1, "resolution": "1x1", "fps": 1},
            "status": "ok",
        },
    )
    monkeypatch.setattr(
        "core.harness.media_skill_handlers.handle_subtitle_extractor",
        lambda p: {"has_subtitle": False, "status": "ok"},
    )
    monkeypatch.setattr(
        "core.harness.media_skill_handlers.handle_speech_analyzer",
        lambda p: {"has_audio": False, "status": "ok"},
    )

    r = handle_report_json_export({"app_name": "videosense", "task_id": "task-001"})
    assert r.get("export_format") == "json"
    assert r.get("export_json") is True
    blob = __import__("json").dumps(r, ensure_ascii=False)
    assert "export_format" in blob
