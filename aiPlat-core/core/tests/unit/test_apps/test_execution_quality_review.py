"""Rule-based post-execution quality review (runtime ok ≠ content ok)."""

from __future__ import annotations

import re
from pathlib import Path

from types import SimpleNamespace

import pytest

from core.management.execution_quality_review import (
    FAIL_CONSTRAINT_BANNER,
    apply_quality_sop_for_skill_id,
    apply_quality_sop_to_skill_md,
    build_fail_constraint_overlay,
    candidate_skill_md_paths,
    pick_embedded_quality_review,
    probe_quality_sop_markers,
    quality_review_blocks_success,
    resolve_pipeline_stage_review_binding,
    resolve_review_io_from_store,
    review_execution_output,
    review_pipeline_stage,
)


def test_canned_sop_failure_is_not_health_a():
    r = review_execution_output(
        kind="skill",
        asset_id="upload_like",
        asset_name="上传",
        input_payload={"file": "demo.mp4"},
        output="错误：文件格式不支持。请检查文件扩展名。",
        status="completed",
    )
    assert r["verdict"] == "fail"
    assert (r.get("summary") or {}).get("health") != "A"
    assert any(i.get("code") == "canned_sop_failure" for i in (r.get("issues") or []))
    assert quality_review_blocks_success(r)


def test_pipeline_stage_binding_skips_control_nodes():
    assert resolve_pipeline_stage_review_binding(SimpleNamespace(node_type="start", id="s0")) is None
    assert resolve_pipeline_stage_review_binding(SimpleNamespace(node_type="condition", id="c1")) is None


def test_pipeline_stage_review_prd_only_on_prd_shaped_output():
    stage = SimpleNamespace(
        id="n_prd",
        node_type="agent",
        agent_id="pm_agent",
        agent_name="产品经理",
        skill_name="",
        required_skills=["requirement_analysis"],
        node_config={},
        output_artifact="agent_output",
    )
    weak = {
        "functional_requirements": [{"acceptance_criteria": ["可以查看"]}],
        "constraints": ["合规检查"],
        "open_questions": [],
    }
    r = review_pipeline_stage(stage=stage, artifact=weak, input_payload="照片不能传到公网", status="completed")
    assert r is not None
    assert r["verdict"] == "fail"
    assert r.get("stage_id") == "n_prd"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "missing_hard_constraint" in codes

    plain_stage = SimpleNamespace(
        id="n_llm",
        node_type="llm",
        agent_id="llm",
        agent_name="摘要",
        skill_name="",
        required_skills=[],
        node_config={},
        output_artifact="llm_output",
    )
    ok = review_pipeline_stage(
        stage=plain_stage,
        artifact={"summary": "本周报障 12 条，平均闭环 3 小时"},
        status="completed",
    )
    assert ok is not None
    assert ok["verdict"] == "pass"
    assert not (ok.get("issues") or [])


def test_hard_constraint_accepts_photo_not_exfiltrate_synonym():
    """SOP teaches「照片不外传」; review must treat it as keeping 不上公网 constraint."""
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={"user_requirement": "照片不能传到公网，钉钉API未开放，预算未定"},
        output={
            "functional_requirements": [
                {"id": "FR1", "description": "上报", "acceptance_criteria": ["工单状态变为已派修"]}
            ],
            "constraints": {"security": ["照片不外传"], "performance": ["待压测"]},
            "open_questions": ["钉钉 API 何时开放？", "预算与编制？"],
            "decisions": [],
        },
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "missing_hard_constraint" not in codes


def test_prd_weak_output_surfaces_issues_and_sop_guide():
    inp = {
        "user_requirement": (
            "车间巡检拍照上传，照片不能传到公网，钉钉API未开放，"
            "希望领导能看汇总，预算和编制未定"
        )
    }
    out = {
        "title": "巡检系统PRD",
        "functional_requirements": [
            {"id": "FR1", "description": "上传照片", "acceptance_criteria": ["可以查看", "上传成功"]}
        ],
        "constraints": ["合规检查"],
        "open_questions": [],
        "non_functional": {"performance": "支持100条/秒，本地服务器，P95 < 1秒"},
        "status": "PRD_READY",
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    assert r["runtime_ok"] is True
    assert r["verdict"] == "fail"
    assert r["ok"] is False
    codes = {i["code"] for i in r["issues"]}
    assert "missing_hard_constraint" in codes
    assert "soft_acceptance_criteria" in codes
    assert "empty_open_questions_on_draft" in codes
    assert r["fix_guide"]["primary_where"] == "edit_skill_sop"
    assert "SOP" in (r["fix_guide"]["primary_label"] or "")
    assert any(i.get("where_label") for i in r["issues"])


def test_draft_round_skips_open_questions_present_and_encryption_when_oq_tracks():
    """Customer-oral draft: open_questions + encryption OQ must not hard-fail like PRD_READY."""
    inp = {
        "user_requirement": (
            "【客户口述｜请做可验收草稿，不要 PRD_READY】\n"
            "照片不能传到公网；钉钉 API 未开放；预算未定；"
            "未口述的加密方案不得写成已确认。"
        )
    }
    out = {
        "title": "现场巡检报障",
        "functional_requirements": [
            {
                "id": "FR1",
                "description": "拍照上报",
                "acceptance_criteria": [
                    {"id": "AC1.1", "description": "提交后工单状态为待审批"}
                ],
            },
            {
                "id": "FR2",
                "description": "班组长审批派修",
                "acceptance_criteria": [
                    {"id": "AC2.1", "description": "审批通过后工单状态为已派修"}
                ],
            },
            {
                "id": "FR3",
                "description": "管理层看板",
                "acceptance_criteria": [
                    {"id": "AC3.1", "description": "看板展示本周报障量与平均闭环时长（小时）"}
                ],
            },
        ],
        "constraints": {
            "performance": "6 周内试点 1 个车间（量级待压测）",
            "security": "照片不上公网 / 不外传",
        },
        "decisions": [
            {"id": "D1", "description": "不做 OCR / 语音转写", "rationale": "客户明确不做"}
        ],
        "open_questions": [
            "钉钉 API 未开放，集成方案待确认",
            "加密存储/密钥托管方案待确认（未口述）",
            "预算与编制未定",
        ],
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "open_questions_present" not in codes
    assert not any("encryption_key_mgmt" in c for c in codes)
    assert "missing_hard_constraint" not in codes
    # Soft AC absent → draft with solid AC should not hard-fail on PRD gate leftovers
    assert r["verdict"] in ("pass", "warn")


def test_missing_input_infers_draft_from_open_questions():
    """When input truly missing, infer draft from OQ shape — and warn about the gap."""
    out = {
        "title": "现场巡检报障",
        "functional_requirements": [
            {"id": "FR1", "acceptance_criteria": ["提交后工单 status=pending_approval"]},
            {"id": "FR2", "acceptance_criteria": ["审批后 status=assigned 且 repair_task_id 非空"]},
            {"id": "FR3", "acceptance_criteria": ["看板返回 ticket_count 与 avg_close_hours 数值字段"]},
        ],
        "constraints": {"performance": ["待压测"], "security": ["照片不外传"]},
        "open_questions": ["钉钉 API 是否开放？", "预算与编制？"],
        "decisions": {"dingtalk_integration": "pending_api"},
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={},
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "open_questions_present" not in codes
    assert "insufficient_functional_requirements" not in codes
    assert "invented_nfr" not in codes  # empty input must not invent-flag all output phrases
    assert "review_input_missing" in codes
    assert r["verdict"] in ("pass", "warn")


def test_soft_ac_hits_view_via_system_phrase():
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={
            "user_requirement": "【客户口述｜请做可验收草稿，不要 PRD_READY】照片不上公网；钉钉 API 未开放"
        },
        output={
            "functional_requirements": [
                {"acceptance_criteria": ["管理层能通过系统查看本周报障量"]}
            ],
            "constraints": {"performance": ["待压测"], "security": ["照片不上公网"]},
            "open_questions": ["钉钉 API 待确认"],
            "decisions": {},
        },
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "soft_acceptance_criteria" in codes
    assert "open_questions_present" not in codes


def test_finalize_round_allows_empty_open_questions():
    """Explicit 定稿 may keep「API 仍未开放」in decisions and close OQ."""
    inp = {
        "user_requirement": (
            "【定稿｜上一轮草稿基础上关闭待确认】\n"
            "已确认：\n"
            "- 钉钉：试点期不做深度集成；API 仍未开放\n"
            "- 预算/编制：试点由现有班组兼任；预算待下一阶段\n"
            "- OCR、语音转写：明确不做（勿再列入 open_questions）\n"
            "请输出定稿 PRD：open_questions=[]，可加 <!-- PRD_READY -->。"
        )
    }
    out = {
        "title": "现场巡检报障小应用",
        "functional_requirements": [
            {
                "id": "FR-001",
                "acceptance_criteria": ["提交后工单 status=pending_approval"],
            },
            {
                "id": "FR-002",
                "acceptance_criteria": ["审批后 status=assigned 且 repair_task_id 非空"],
            },
            {
                "id": "FR-003",
                "acceptance_criteria": ["看板返回 ticket_count 与 avg_close_hours 数值字段"],
            },
        ],
        "constraints": {
            "performance": ["6 周内试点 1 个车间（量级待压测）"],
            "security": ["不上公网/照片不外传"],
        },
        "open_questions": [],
        "decisions": {
            "dingtalk_integration": "pending_api",
            "ocr": "out_of_scope",
            "speech": "out_of_scope",
        },
        "status": "PRD_READY",
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "empty_open_questions_on_draft" not in codes
    assert "premature_prd_ready" not in codes
    assert "media_url_scope_open" not in codes
    assert r["verdict"] in ("pass", "warn")


def test_out_of_scope_as_feature_caught_on_thin_finalize():
    """Thin 定稿 input that still says 明确不做 must fail if FR implements speech."""
    inp = {
        "user_requirement": (
            "【定稿｜关闭待确认】\n"
            "- OCR、语音转写：明确不做\n"
            "请输出定稿 PRD：open_questions=[]，可加 <!-- PRD_READY -->。"
        )
    }
    out = {
        "title": "项目名称",
        "functional_requirements": [
            {
                "id": "FR-001",
                "description": "钉钉账号集成生成 repair_task_id",
                "acceptance_criteria": ["工单 status=assigned 后生成 repair_task_id"],
            },
            {
                "id": "FR-002",
                "description": "通过语音转写功能生成文字内容",
                "acceptance_criteria": ["用户输入语音后，系统能够生成相应的文字内容"],
            },
        ],
        "constraints": {
            "performance": ["口述目标转述（待压测确认）"],
            "security": ["不上公网/照片不外传"],
        },
        "open_questions": [],
        "decisions": {
            "dingtalk_integration": "pending_api",
            "speech_pipeline": "audio_features_only",
        },
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "out_of_scope_as_feature" in codes
    assert "insufficient_functional_requirements" in codes
    assert "empty_open_questions_on_draft" not in codes
    assert "media_url_scope_open" not in codes
    assert r["verdict"] == "fail"


def test_architect_public_cloud_photo_storage_fails():
    """Architect draft using 阿里云存储 under 不上公网 must not pass quality review."""
    inp = {
        "message": (
            "任务背景：根据PRD完成系统架构设计\n"
            "约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n"
            "请输出：1.上下文与假设；2.逻辑架构；3.数据流；4.API契约；5.安全与合规；6.分期与风险。"
        )
    }
    out = {
        "components": [
            {
                "name": "照片存储服务",
                "responsibility": "存储现场巡检照片",
                "tech": "阿里云存储",
                "depends_on": [],
            },
            {
                "name": "看板服务",
                "tech": "Vue.js",
                "depends_on": [],
            },
        ],
        "api_contracts": [
            {"path": "/api/photos/upload", "method": "POST", "description": "上传"},
        ],
        "tech_stack": {"backend": "Node.js"},
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="系统架构师",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "public_cloud_photo_storage" in codes
    assert "architecture_sections_thin" in codes
    assert r["verdict"] == "fail"


def test_architect_private_storage_passes_cloud_gate():
    inp = {
        "message": "照片不可上公网。输出架构：上下文与假设；数据流；安全与合规；6周分期与风险；API契约含请求响应。"
    }
    out = {
        "context": "现场巡检报障；假设：钉钉 API 未开放，试点期不深集成（待确认）。",
        "data_flow": "上报→审批→派修→看板",
        "security": "照片仅落内网私有 MinIO，不上公网、不外传。",
        "risks": "6周分期：W1-2 上报审批，W3-4 派修看板，风险为钉钉对接延误。",
        "components": [
            {"name": "照片存储", "tech": "内网自建 MinIO", "responsibility": "私有化对象存储"}
        ],
        "api_contracts": [
            {
                "path": "/api/tickets",
                "method": "POST",
                "description": "创建报障",
                "request": {
                    "body": {
                        "photo_ref": "内网 MinIO object key",
                        "shop_id": "车间编码",
                        "desc": "故障描述文本",
                    }
                },
                "response": {
                    "status": 201,
                    "body": {"ticket_id": "tkt_xxx", "status": "pending_approval"},
                },
            }
        ],
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "public_cloud_photo_storage" not in codes
    assert r["verdict"] in ("pass", "warn")


def test_open_questions_alone_does_not_cover_context_section():
    """open_questions list ≠ 上下文与假设; must have context/assumptions/overview body."""
    inp = {
        "message": (
            "请输出：1.上下文与假设；2.逻辑架构；3.数据流；4.API契约；"
            "5.安全与合规；6.分期与风险。钉钉暂无 API 文档禁止编造。"
        )
    }
    out = {
        "title": "巡检报修 — 架构草稿",
        # no overview / context — only OQ must still fail
        "folder_structure": {"api": ["tickets.py"], "services": ["ticket_service.py"]},
        "data_flow": "上报→审批→派修→看板",
        "api_design": [
            {
                "path": "/api/tickets",
                "method": "POST",
                "description": "创建报障",
                "request": {"body": {"photo_ref": "string"}},
                "response": {"status": 201},
            }
        ],
        "security": "照片仅落内网，不上公网。",
        "6周试点的分期切片与风险": "W1-2 上报；W3-4 派修；风险为钉钉延误。",
        "open_questions": ["钉钉 API 文档何时提供？", "试点范围与编制如何确定？"],
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "architecture_sections_thin" in codes
    thin = next(i for i in r["issues"] if i["code"] == "architecture_sections_thin")
    assert "上下文与假设" in thin["message"]
    assert thin.get("where_label", "").startswith("编辑 Skill「architecture_design」")
    assert r["fix_guide"]["primary_label"].startswith("编辑 Skill「architecture_design」")
    assert r["verdict"] == "fail"


def test_overview_promoted_to_context_passes_section_gate():
    """Local LLM wrote 上下文 into overview — normalize so review does not false-fail."""
    from core.management.execution_quality_review import ensure_architecture_section_fields

    raw = {
        "title": "巡检",
        "overview": "现场巡检报障；假设钉钉 API 未开放；6周试点一个车间。",
        "data_flow": "上报→审批→派修→看板",
        "security_and_compliance": "照片仅落内网私有 MinIO，不上公网；人脸/工号脱敏后入库。",
        "rollout_and_risks": "W1-2 上报；风险钉钉延误。",
        "api_design": [
            {
                "path": "/api/tickets",
                "method": "POST",
                "description": "创建报障单，照片引用为内网对象键",
                "request": {
                    "body": {
                        "photo_ref": "内网 MinIO object key",
                        "shop_id": "车间编码",
                        "desc": "故障描述",
                    }
                },
                "response": {
                    "status": 201,
                    "body": {"ticket_id": "tkt_xxx", "status": "pending_approval"},
                },
            }
        ],
    }
    filled = ensure_architecture_section_fields(raw)
    assert filled["context"].startswith("现场巡检")
    assert filled["security"].startswith("照片仅落")

    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload={
            "message": "请输出上下文与假设、数据流、安全与合规、6周分期与风险、API契约。"
        },
        output=raw,
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "architecture_sections_thin" not in codes


def test_context_field_covers_context_section():
    """Non-empty context field satisfies 上下文与假设 even if open_questions also present."""
    inp = {
        "message": "请输出上下文与假设、数据流、安全与合规、6周分期与风险。"
    }
    out = {
        "context": "现场巡检报修；假设：钉钉 API 未开放，试点期不深集成。",
        "data_flow": "上报→审批→派修→看板",
        "security": "内网私有化，不上公网。",
        "rollout_and_risks": "W1-2 上报审批；W3-4 派修看板；风险：钉钉对接延误。",
        "open_questions": ["钉钉 API 何时开放？"],
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "architecture_sections_thin" not in codes


def test_false_a_empty_acceptance_criteria_caught():
    """AC mashed into FR title with empty acceptance_criteria must not grade A."""
    inp = {
        "user_requirement": (
            "【定稿】上报 AC=status=pending_approval；派修 AC=repair_task_id；"
            "看板 AC=ticket_count与avg_close_hours；open_questions=[]"
        )
    }
    out = {
        "title": "需求分析产物",
        "functional_requirements": [
            {"id": "FR1", "description": "上报报障时照片状态为pending_approval"},
            {"id": "FR2", "description": "派修报障时任务状态为assigned且repair_task_id非空"},
            {"id": "FR3", "description": "看板返回本周报障量和平均闭环时长"},
        ],
        "constraints": {
            "performance": ["试点1个车间"],
            "security": ["不上公网+照片不外传"],
        },
        "open_questions": [],
        "decisions": {
            "dingtalk_integration": "pending_api",
            "ocr": "不做",
            "speech_to_text": "不做",
        },
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "fr_without_ac" in codes
    assert "missing_required_ac_tokens" in codes
    assert r["verdict"] == "fail"


def test_false_a_constraint_fr_and_missing_report_caught():
    """A-looking PRD that used 不上公网 as FR and dropped 拍照上报."""
    inp = {
        "user_requirement": (
            "【定稿】一线工人手机拍照上报；班组长审批后派修；"
            "管理层看板看本周报障量与平均闭环时长；"
            "照片不能传到公网；钉钉 API 未开放 → pending_api；明确不做：OCR、语音转写。"
        )
    }
    out = {
        "title": "需求分析产物",
        "functional_requirements": [
            {
                "id": "FR-1",
                "description": "确保工单状态为 assigned",
                "acceptance_criteria": ["审批通过后工单 status=assigned 且 repair_task_id 非空"],
            },
            {
                "id": "FR-2",
                "description": "确保看板返回正确的统计信息",
                "acceptance_criteria": ["看板返回 ticket_count 与 avg_close_hours 数值字段"],
            },
            {
                "id": "FR-3",
                "description": "确保照片不上传到公网",
                "acceptance_criteria": ["照片不上传到公网"],
            },
        ],
        "constraints": {
            "performance": ["6 周内试点 1 个车间（待压测）"],
            "security": ["不上公网", "照片不外传"],
        },
        "open_questions": [],
        "decisions": {"dingtalk_integration": "pending_api"},
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "constraint_as_functional_requirement" in codes
    assert "missing_core_flow_fr" in codes
    assert r["verdict"] == "fail"


def test_latest_false_a_run_is_caught():
    """Atom-shaped FR + soft board-view AC + FR<3 + OCR reopened in OQ."""
    inp = {
        "user_requirement": (
            "【客户口述｜请做可验收草稿，不要 PRD_READY】\n"
            "照片不能传到公网；钉钉 API 未开放；明确不做：OCR 自动识别铭牌、语音转写工单。\n"
            "硬性自检：≥3 条 FR"
        )
    }
    out = {
        "title": "现场巡检报障小应用",
        "functional_requirements": [
            {
                "label": "巡检报障",
                "acceptance_criteria": [
                    {
                        "label": "一线工人拍照上报",
                        "description": "一线工人通过手机拍照上报设备异常，照片中可能包含产线布局，但不能传到公网。",
                    }
                ],
            },
            {
                "label": "管理层查看报障数据",
                "acceptance_criteria": [
                    {
                        "label": "查看本周报障量",
                        "description": "管理层可以通过看板查看本周报障量。",
                    }
                ],
            },
        ],
        "constraints": {
            "performance": ["巡检报障功能应在6周内完成试点1个车间"],
            "security": ["照片可能含产线布局，不能传到公网"],
        },
        "open_questions": [
            "钉钉 API 是否开放",
            "预算与编制情况",
            "是否需要进行 OCR 自动识别铭牌的功能",
        ],
        "decisions": [],
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "soft_acceptance_criteria" in codes
    assert "insufficient_functional_requirements" in codes
    assert "out_of_scope_reopened" in codes
    assert r["verdict"] == "fail"


def test_constraint_bucket_and_pending_ac_fail():
    """Last A-grade run still misplaced security into performance and used pending as AC."""
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={
            "user_requirement": (
                "【客户口述｜请做可验收草稿，不要 PRD_READY】\n"
                "照片不能传到公网；钉钉 API 未开放"
            )
        },
        output={
            "title": "现场巡检报障小应用",
            "functional_requirements": [
                {
                    "id": "FR-001",
                    "acceptance_criteria": [
                        "班组长账号审批通过后，工单 status 变为 assigned 且生成 repair_task_id"
                    ],
                },
                {
                    "id": "FR-003",
                    "acceptance_criteria": ["钉钉 API 未开放/集成待确认"],
                },
            ],
            "constraints": {
                "performance": ["照片可能含产线布局，不能传到公网"],
                "security": ["不上公网/照片不外传"],
            },
            "open_questions": ["钉钉 API 是否开放"],
            "decisions": {"dingtalk_integration": "pending_api"},
        },
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "constraint_bucket_mismatch" in codes
    assert "pending_as_acceptance_criteria" in codes
    assert r["verdict"] == "fail"
    assert r["ok"] is False


def test_well_bucketed_prd_still_passes():
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={
            "user_requirement": "【客户口述｜请做可验收草稿，不要 PRD_READY】照片不能传到公网；钉钉 API 未开放"
        },
        output={
            "functional_requirements": [
                {
                    "id": "FR-001",
                    "acceptance_criteria": ["提交后工单 status=pending_approval"],
                },
                {
                    "id": "FR-002",
                    "acceptance_criteria": ["审批后 status=assigned 且 repair_task_id 非空"],
                },
                {
                    "id": "FR-003",
                    "acceptance_criteria": ["看板返回 ticket_count 与 avg_close_hours 数值字段"],
                },
            ],
            "constraints": {
                "performance": ["6 周内试点 1 个车间（量级待压测）"],
                "security": ["不上公网/照片不外传"],
            },
            "open_questions": ["钉钉 API 是否开放"],
            "decisions": {"dingtalk_integration": "pending_api"},
        },
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "constraint_bucket_mismatch" not in codes
    assert "pending_as_acceptance_criteria" not in codes
    assert "insufficient_functional_requirements" not in codes
    assert r["verdict"] in ("pass", "warn")


def test_draft_round_flags_invented_encryption_and_soft_ac():
    inp = {
        "user_requirement": (
            "【客户口述｜请做可验收草稿，不要 PRD_READY】\n"
            "照片不能传到公网；钉钉 API 未开放；加密方案不得写成已确认。"
        )
    }
    out = {
        "functional_requirements": [
            {
                "id": "FR1",
                "acceptance_criteria": [{"description": "班组长可以查看并审批"}],
            }
        ],
        "constraints": {
            "performance": "支持至少100个设备异常报告",
            "security": "照片不能传到公网，数据应加密存储和传输",
        },
        "open_questions": ["钉钉 API 待确认", "加密具体方案待确认"],
        "decisions": [],
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload=inp,
        output=out,
        status="completed",
    )
    codes = {i["code"] for i in r["issues"]}
    assert "open_questions_present" not in codes
    assert "soft_acceptance_criteria" in codes
    assert "invented_nfr" in codes
    assert r["verdict"] == "fail"


def test_markdown_envelope_still_reviewed():
    out = {
        "markdown": (
            '```json\n{"functional_requirements":[{"acceptance_criteria":["可以查看"]}],'
            '"open_questions":[],"constraints":["合规"]}\n```'
        )
    }
    r = review_execution_output(
        kind="skill",
        asset_id="requirement_analysis",
        asset_name="需求分析",
        input_payload={"message": "照片不上公网，钉钉API未开放，预算未定"},
        output=out,
        status="completed",
    )
    assert r["verdict"] == "fail"
    assert len(r["issues"]) >= 1


def test_apply_quality_sop_idempotent(tmp_path: Path):
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: t\nversion: 1.0.0\n---\n\n# Body\n\n## 输出铁律\n- keep\n",
        encoding="utf-8",
    )
    r1 = apply_quality_sop_to_skill_md(
        md, issue_codes=["soft_acceptance_criteria", "empty_open_questions_on_draft"]
    )
    assert r1["status"] == "applied"
    assert set(r1["applied"]) == {"soft_acceptance_criteria", "empty_open_questions_on_draft"}
    text = md.read_text(encoding="utf-8")
    assert "eq_fix:soft_acceptance_criteria" in text
    r2 = apply_quality_sop_to_skill_md(md, issue_codes=["soft_acceptance_criteria"])
    assert r2["status"] == "noop"
    assert "soft_acceptance_criteria" in r2["skipped"]


def test_apply_quality_sop_for_skill_id_multi_path(tmp_path: Path, monkeypatch):
    sid = "demo_quality_skill"
    a = tmp_path / "a" / sid
    b = tmp_path / "b" / sid
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    body = "---\nname: demo\n---\n\n# Body\n"
    (a / "SKILL.md").write_text(body, encoding="utf-8")
    (b / "SKILL.md").write_text(body, encoding="utf-8")

    def _fake_candidates(skill_id, *, primary=None):
        assert skill_id == sid
        return [a / "SKILL.md", b / "SKILL.md"]

    monkeypatch.setattr(
        "core.management.execution_quality_review.candidate_skill_md_paths",
        _fake_candidates,
    )
    r = apply_quality_sop_for_skill_id(sid, issue_codes=["invented_nfr"])
    assert r["status"] == "applied"
    assert "invented_nfr" in r["applied"]
    assert len(r.get("paths") or []) == 2
    assert "eq_fix:invented_nfr" in (a / "SKILL.md").read_text(encoding="utf-8")
    assert "eq_fix:invented_nfr" in (b / "SKILL.md").read_text(encoding="utf-8")
    # sanity: real candidate helper finds at least engine/home when present
    assert isinstance(candidate_skill_md_paths("requirement_analysis"), list)


@pytest.mark.asyncio
async def test_resolve_review_io_restores_empty_string_and_text_envelope(monkeypatch):
    """Frontend race often POSTs output="" / {"text":""} — must restore from store."""

    class _Store:
        async def get_agent_execution(self, eid):
            return {
                "id": eid,
                "status": "completed",
                "input": {"message": "PRD 正文"},
                "output": {"text": "{'x-display-profile': '{\"title\": \"现场巡检\"}'}"},
                "metadata": {
                    "quality_review": {
                        "verdict": "fail",
                        "issues": [{"code": "architecture_sections_thin", "severity": "error"}],
                    }
                },
            }

    monkeypatch.setattr(
        "core.services.execution_store.get_execution_store",
        lambda: _Store(),
    )
    for body_out in ("", {"text": ""}, None):
        inp, out, st, embedded = await resolve_review_io_from_store(
            execution_id="run-race",
            kind="agent",
            body_input=None,
            body_output=body_out,
            body_status="completed",
        )
        assert "现场巡检" in str(out)
        assert st == "completed"
        assert embedded and embedded["issues"][0]["code"] == "architecture_sections_thin"
        chosen = pick_embedded_quality_review(
            embedded=embedded,
            body_output=body_out,
            resolved_output=out,
            prefer_embedded=False,
        )
        assert chosen is not None
        assert chosen["issues"][0]["code"] == "architecture_sections_thin"


def test_pick_embedded_skips_stale_empty_output_when_payload_restored():
    embedded = {
        "verdict": "fail",
        "issues": [{"code": "empty_output", "severity": "error"}],
    }
    assert (
        pick_embedded_quality_review(
            embedded=embedded,
            body_output="",
            resolved_output={"text": "long enough architecture body " * 5},
            prefer_embedded=True,
        )
        is None
    )


def test_pick_embedded_skips_stale_pass_when_body_has_product():
    """prefer_embedded must not lock a stored pass once the UI has real output."""
    from core.management.execution_quality_review import pick_embedded_quality_review

    embedded = {"verdict": "pass", "issues": [], "summary": {"health": "A"}}
    body = {
        "code": "## FILE: src/apiClient.ts\n```ts\nimport { x } from './utils';\n```",
        "language": "typescript",
    }
    assert (
        pick_embedded_quality_review(
            embedded=embedded,
            body_output=body,
            resolved_output=body,
            prefer_embedded=True,
        )
        is None
    )
    # Empty body race: still allow embedded pass
    assert (
        pick_embedded_quality_review(
            embedded=embedded,
            body_output="",
            resolved_output=body,
            prefer_embedded=True,
        )
        is not None
    )
    # execution_id-only (prefer_embedded false) must re-review stored A
    assert (
        pick_embedded_quality_review(
            embedded=embedded,
            body_output="",
            resolved_output=body,
            prefer_embedded=False,
        )
        is None
    )


@pytest.mark.asyncio
async def test_resolve_review_io_from_store_fills_input(monkeypatch):
    class _Store:
        async def get_skill_execution(self, eid):
            assert eid == "run-abc"
            return {
                "id": eid,
                "status": "completed",
                "input": {"message": "客户口述：不上公网"},
                "output": {"title": "PRD", "open_questions": ["预算？"]},
                "metadata": {"quality_review": {"verdict": "pass"}},
            }

        async def get_agent_execution(self, eid):
            return None

    monkeypatch.setattr(
        "core.services.execution_store.get_execution_store",
        lambda: _Store(),
    )
    inp, out, st, embedded = await resolve_review_io_from_store(
        execution_id="run-abc",
        kind="skill",
        body_input=None,
        body_output=None,
        body_status=None,
    )
    assert "不上公网" in str(inp)
    assert isinstance(out, dict)
    assert st == "completed"
    assert embedded and embedded.get("verdict") == "pass"


@pytest.mark.asyncio
async def test_resolve_review_io_prefers_body_input(monkeypatch):
    class _Store:
        async def get_agent_execution(self, eid):
            return {
                "id": eid,
                "status": "completed",
                "input": {"message": "from-store"},
                "output": {"text": "x"},
                "metadata": {},
            }

    monkeypatch.setattr(
        "core.services.execution_store.get_execution_store",
        lambda: _Store(),
    )
    inp, out, st, _ = await resolve_review_io_from_store(
        execution_id="run-agent",
        kind="agent",
        body_input={"message": "from-body"},
        body_output={"text": "body-out"},
        body_status="completed",
    )
    assert inp == {"message": "from-body"}
    assert out == {"text": "body-out"}
    assert st == "completed"


def test_architect_shallow_code_shell_fails_quality_a():
    """Regression: run-3044-style shell (Agent 口号 + 空壳 API + 仅上传数据流) must not grade A."""
    inp = {
        "message": (
            "任务背景：根据PRD完成系统架构设计\n"
            "目标：现场巡检报障小应用（拍照上报 → 班组长审批 → 派修 → 看板）。\n"
            "约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n"
            "请按架构师职责输出：1.上下文与假设（标明待确认）；2.逻辑架构；"
            "3.数据流（上报/审批/派修/看板）；4.对外 API 契约；5.安全与合规（照片落地、脱敏、内网）；"
            "6.6 周试点分期与风险。禁止编造未给定的第三方接口细节。"
        )
    }
    out = {
        "title": "现场巡检报障小应用",
        "overview": (
            "本系统采用Agent架构模式，主要用于现场巡检报障流程。"
            "系统设计遵循不上传照片到公网的原则，并且暂时无法确认钉钉API的具体细节。"
            "系统设计将分为多个组件，以确保系统的安全性和易扩展性。"
        ),
        "folder_structure": [
            {"name": "frontend", "tech": "Vue 3.2", "responsibility": "UI"},
            {"name": "backend", "tech": "FastAPI 0.8.2", "responsibility": "API"},
            {"name": "database", "tech": "PostgreSQL 13", "responsibility": "存储"},
        ],
        "data_flow": [
            {
                "description": "用户拍照上传，前端经 FastAPI 到后端，结果回前端并入库。",
                "steps": ["拍照上传", "后端处理", "返回结果"],
            }
        ],
        "api_design": [
            {
                "method": "POST",
                "path": "/api/capture",
                "description": "拍照上传",
                "request": {"headers": {}, "body": {"image": "照片数据"}},
                "response": {"status": 200, "body": "处理结果"},
            },
            {
                "method": "POST",
                "path": "/api/approve",
                "description": "审批",
                "request": {"body": {"id": "报障ID", "status": "审批状态"}},
                "response": {"status": 200, "body": "审批结果"},
            },
            {
                "method": "POST",
                "path": "/api/distribute",
                "description": "派修",
                "request": {"body": {"id": "报障ID", "assignee": "派修人员"}},
                "response": {"status": 200, "body": "派修结果"},
            },
        ],
        "rollout_and_risks": {
            "phases": [{"phase_name": "第一周", "description": "开发"}, {"phase_name": "第二周", "description": "测试"}],
            "risks": ["系统不稳定"],
        },
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="architecture_design",
    )
    assert r["verdict"] == "fail"
    assert r["summary"]["health"] != "A"
    msgs = " | ".join(i["message"] for i in r["issues"])
    assert "architecture_sections_thin" in {i["code"] for i in r["issues"]}
    assert ("数据流" in msgs) or ("API" in msgs) or ("安全" in msgs)


def test_architect_run7060_shell_with_dingtalk_sdk_fails_a():
    """Regression: run-70605115a225 — placeholder APIs + DingTalk SDK + slogan security must fail."""
    inp = {
        "message": (
            "任务背景：根据PRD完成系统架构设计\n"
            "【输入｜精简 PRD 摘要】\n"
            "目标：现场巡检报障小应用（拍照上报 → 班组长审批 → 派修 → 看板）。\n"
            "约束：照片不可上公网；希望对接钉钉但暂无 API 文档；6 周试点一个车间。\n"
            "请按架构师职责输出一版可评审的架构草稿：\n"
            "1. 上下文与假设（标明待确认）；\n"
            "2. 逻辑架构 + 关键组件职责；\n"
            "3. 数据流（上报/审批/派修/看板）与存储选型理由；\n"
            "4. 对外 API 契约草案（3～5 个端点：方法/路径/请求响应要点）；\n"
            "5. 安全与合规（照片落地、脱敏、内网边界）；\n"
            "6. 6 周试点的分期切片与风险。\n"
            "禁止编造未给定的第三方接口细节。"
        )
    }
    out = {
        "title": "现场巡检报障小应用",
        "overview": (
            "本系统设计旨在实现现场巡检报障流程，包括拍照上报、班组长审批、派修以及看板展示。"
            "系统要求照片不可上公网，且需对接钉钉但暂无明确 API 文档。"
            "系统设计将遵循内网和私有化落地原则。"
        ),
        "folder_structure": [
            {"name": "app", "type": "前端", "tech": "Vue 3.0", "responsibility": "前端页面展示及交互逻辑"},
            {
                "name": "api",
                "type": "后端",
                "tech": "FastAPI 3.0, Django 3.2",
                "responsibility": "API 接口设计及实现，包括拍照上传、审批、派修等",
            },
            {
                "name": "db",
                "type": "数据",
                "tech": "MySQL 8.0, PostgreSQL 13.0",
                "responsibility": "存储用户信息、审批记录、派修记录等",
            },
            {
                "name": "notification",
                "type": "中间件",
                "tech": "DingTalk SDK",
                "responsibility": "与钉钉进行交互，实现审批和派修通知",
            },
            {
                "name": "security",
                "type": "安全",
                "tech": "自定义",
                "responsibility": "确保照片不外传，对接钉钉时确保安全合规",
            },
        ],
        "api_design": [
            {
                "method": "POST",
                "path": "/api/picture",
                "description": "用户通过前端提交一张照片",
                "request": {"headers": {}, "body": {"image": "照片数据"}},
                "response": {"status": 200, "body": "照片上传成功"},
            },
            {
                "method": "POST",
                "path": "/api/approve",
                "description": "班组长审批照片",
                "request": {"headers": {}, "body": {"user_id": "班组长ID", "picture_id": "照片ID"}},
                "response": {"status": 200, "body": "审批通过"},
            },
            {
                "method": "POST",
                "path": "/api/assign",
                "description": "派修任务",
                "request": {"headers": {}, "body": {"user_id": "派修人员ID", "picture_id": "照片ID"}},
                "response": {"status": 200, "body": "派修任务完成"},
            },
            {
                "method": "GET",
                "path": "/api/dashboard",
                "description": "查看看板",
                "request": {"headers": {}, "body": {}},
                "response": {"status": 200, "body": "看板数据"},
            },
        ],
        "security": {"照片脱敏": "确保照片不外传，对接钉钉时确保安全合规"},
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="architecture_design",
    )
    assert r["verdict"] == "fail"
    assert r["summary"]["health"] != "A"
    codes = {i["code"] for i in r["issues"]}
    assert "architecture_sections_thin" in codes
    assert "invented_third_party_api" in codes
    msgs = " | ".join(i["message"] for i in r["issues"])
    assert ("API" in msgs) or ("安全" in msgs) or ("分期" in msgs)
    assert "DingTalk" in msgs or "钉钉" in msgs


def test_architect_empty_output_does_not_pile_prd_sop_issues():
    """Empty architect run must only report empty_output — not PRD hard-constraint SOP."""
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload="钉钉 API 未开放 / 待确认；照片不上公网",
        output={"text": ""},
        status="completed",
        hints="architecture_design architect_agent",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert codes == {"empty_output"}
    assert "missing_hard_constraint" not in codes
    assert "architecture_sections_thin" not in codes


def test_architect_without_pm_hint_does_not_use_prd_rules():
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload="钉钉 API 未开放 / 待确认；照片不上公网；要有数据流与安全合规章节",
        output={
            "text": (
                "{'title': '巡检', 'overview': '私有化部署', "
                "'components': [{'name': 'api'}], 'tech_stack': ['Python']}"
            )
        },
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "missing_hard_constraint" not in codes


def test_timeout_status_is_runtime_not_empty_sop():
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload="x",
        output=None,
        status="timeout",
        hints="architecture_design",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert codes == {"runtime_timeout"}
    assert "empty_output" not in codes


def test_architecture_template_echo_detected():
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload="现场巡检报障，钉钉 API 未开放",
        output={
            "text": (
                "{'x-display-profile': '架构设计', 'properties': {"
                "'goals': ['架构目标1：…'], 'overview': '架构总览'}}"
            )
        },
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "architecture_template_echo" in codes


def test_architect_flags_invented_dingtalk_api_and_unwraps_python_dict():
    """Python-dict-repr under text + invented 钉钉接口 must fail (not A/pass)."""
    payload = {
        "title": "现场巡检报障小应用",
        "overview": "私有化存储；暂无钉钉 API 文档",
        "folder_structure": [
            {
                "name": "api",
                "interfaces": [
                    {
                        "method": "POST",
                        "path": "/api/upload",
                        "request": {"body": {}},
                        "response": {"status": 200},
                    }
                ],
            }
        ],
        "data_flow": [
            {"step": 1, "details": "系统将照片信息发送至钉钉审批接口，触发审批流程"},
            {"step": 2, "details": "审批通过后，系统将派修信息发送至钉钉派修接口"},
        ],
        "security": {"photos": {"storage": "私有化存储"}},
        "open_questions": ["钉钉 API 文档"],
    }
    # Mimic store envelope: Python repr string inside {"text": ...}
    text_repr = repr(payload)
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=(
            "现场巡检报障。约束：照片不可上公网；希望对接钉钉但暂无 API 文档。"
            "禁止编造未给定的第三方接口细节。"
        ),
        output={"text": text_repr},
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "invented_third_party_api" in codes
    assert r.get("verdict") == "fail"


def test_dingtalk_overview_pending_api_not_false_invent():
    """Honest「对接钉钉但暂无 API」must NOT trip invented_third_party_api (e86a FP)."""
    from core.management.execution_quality_review import _dingtalk_invented_integration

    inp = "约束：希望对接钉钉但暂无 API 文档；禁止编造未给定的第三方接口细节。"
    honest = {
        "overview": "系统将对接钉钉平台，但暂无明确的 API 文档。照片不上公网。",
        "components": [
            {
                "name": "notify",
                "tech": "通知通道（钉钉·待确认）",
                "responsibility": "待对接钉钉审批通知",
            }
        ],
    }
    assert _dingtalk_invented_integration(inp, honest) is False
    bad = {
        "overview": "系统对接钉钉完成审批。",
        "folder_structure": [
            {
                "name": "notification",
                "tech": "DingTalk SDK",
                "responsibility": "与钉钉进行交互，实现审批和派修通知",
            }
        ],
    }
    assert _dingtalk_invented_integration(inp, bad) is True


def test_pending_markers_accept_component_tech():
    """SOP places 待确认 on component tech — must satisfy「标明待确认」 (run-76c009)."""
    from core.management.execution_quality_review import _architecture_pending_markers_missing

    inp = "1. 上下文与假设（标明待确认）；钉钉暂无 API 文档"
    out = {
        "context": "现场巡检报障小应用",
        "components": [
            {"name": "钉钉通知", "tech": "通知通道（钉钉·待确认）"},
        ],
    }
    assert _architecture_pending_markers_missing(inp, out) is False
    assert _architecture_pending_markers_missing(
        inp, {"context": "现场巡检报障", "components": [{"tech": "Spring Boot"}]}
    ) is True


def test_dingtalk_notify_channel_and_open_question_not_invent():
    """run-5eb7: 「对接钉钉通知通道」/「如何对接钉钉…？」must not trip invent gate."""
    from core.management.execution_quality_review import (
        _dingtalk_invented_integration,
        sanitize_architecture_third_party,
    )

    inp = "希望对接钉钉但暂无 API 文档；禁止编造未给定的第三方接口细节。"
    honest = {
        "context": "希望对接钉钉进行审批，但目前暂无钉钉的API文档。",
        "open_questions": ["如何对接钉钉审批和派修通知？"],
        "components": [{"name": "审批", "tech": "使用钉钉通知通道"}],
        "phases": [{"tasks": ["对接钉钉通知通道"]}],
    }
    assert _dingtalk_invented_integration(inp, honest) is False
    assert _dingtalk_invented_integration(
        inp,
        {"overview": "与钉钉进行交互，实现审批和派修通知", "tech": "DingTalk SDK"},
    ) is True
    # run-7e0e: tech OK but description says「对接钉钉实现」
    dirty = {
        "context": "希望对接钉钉但暂无 API 文档",
        "components": [
            {
                "name": "通知通道（钉钉·待确认）",
                "description": "负责对接钉钉实现审批和派修",
            }
        ],
    }
    assert _dingtalk_invented_integration(inp, dirty) is True
    clean = sanitize_architecture_third_party(dirty, inp)
    import json as _json

    assert "对接钉钉实现" not in _json.dumps(clean, ensure_ascii=False)
    assert _dingtalk_invented_integration(inp, clean) is False



def test_collect_apis_from_data_flows_details():
    """Models often nest method/path under data_flows[].details (run-5eb7)."""
    from core.management.execution_quality_review import (
        _collect_architecture_apis,
        _architecture_api_thin,
        _architecture_api_item_rich,
    )

    out = {
        "data_flows": [
            {
                "name": "上报",
                "details": [
                    {
                        "method": "POST",
                        "path": "/api/tickets",
                        "request": {"body": {"photo_ref": "内网 key", "shop_id": "S1"}},
                        "response": {"status": 201, "body": {"ticket_id": "t1", "status": "pending"}},
                    }
                ],
            },
            {
                "name": "看板",
                "details": [
                    {
                        "method": "GET",
                        "path": "/api/boards",
                        "request": {},
                        "response": {"status": 200, "body": {"items": [{"id": "1"}]}},
                    }
                ],
            },
        ]
    }
    apis = _collect_architecture_apis(out)
    assert len(apis) == 2
    assert all(_architecture_api_item_rich(a) for a in apis)
    assert (
        _architecture_api_thin("对外 API 契约草案（3～5 个端点）", out) is False
    )


def test_api_item_rich_accepts_ack_message_with_status():
    """run-fc50: request rich + response {status, body:{message:审批成功}} is draft-rich."""
    from core.management.execution_quality_review import (
        _architecture_api_item_rich,
        _architecture_api_thin,
    )

    item = {
        "method": "POST",
        "path": "/api/approvals",
        "request": {"body": {"ticket_id": "tkt_xxx", "approval_status": "approved"}},
        "response": {"status": 200, "body": {"message": "审批成功"}},
    }
    assert _architecture_api_item_rich(item) is True
    arch = {
        "api_contracts": [
            {
                "method": "POST",
                "path": "/api/tickets",
                "request": {"body": {"photo_ref": "k", "shop_id": "S1"}},
                "response": {"status": 201, "body": {"ticket_id": "t1"}},
            },
            item,
            {
                "method": "POST",
                "path": "/api/delivery",
                "request": {"body": {"ticket_id": "tkt_xxx", "delivery_status": "assigned"}},
                "response": {"status": 200, "body": {"message": "派修成功"}},
            },
        ]
    }
    assert _architecture_api_thin("对外 API 契约草案", arch) is False


def test_api_numeric_example_leaves_not_placeholder():
    """GET response with ticket_count:10 must count as rich (run-21ee FP)."""
    from core.management.execution_quality_review import (
        _api_payload_is_placeholder,
        _architecture_api_item_rich,
        _architecture_api_thin,
    )

    res = {"status": 200, "body": {"ticket_count": 10, "pending_count": 3}}
    assert _api_payload_is_placeholder(res) is False
    assert (
        _architecture_api_item_rich(
            {
                "method": "GET",
                "path": "/api/dashboard/tickets",
                "request": {},
                "response": res,
            }
        )
        is True
    )
    arch = {
        "api_contracts": [
            {
                "method": "POST",
                "path": "/api/tickets",
                "request": {"body": {"photo_ref": "key"}},
                "response": {"status": 201, "body": {"ticket_id": "t1"}},
            },
            {
                "method": "GET",
                "path": "/api/dashboard/tickets",
                "request": {},
                "response": res,
            },
            {
                "method": "GET",
                "path": "/api/boards/summary",
                "request": {},
                "response": res,
            },
        ]
    }
    assert _architecture_api_thin("对外 API 契约草案", arch) is False


def test_ensure_architecture_rollout_weeks_fills_phase1_shop_only():
    """run-4c35: phase=1 / 试点一个车间 without W1–W6 must normalize then pass gate."""
    from core.management.execution_quality_review import (
        ensure_architecture_rollout_weeks,
        _architecture_rollout_thin,
        review_execution_output,
    )

    inp = (
        "现场巡检报障；6 周试点一个车间；输出上下文与假设、数据流（上报/审批/派修/看板）、"
        "安全与合规、6 周分期与风险；钉钉暂无 API 文档禁止编造。"
    )
    thin = {
        "title": "现场巡检报障小应用架构设计",
        "context": "目标是开发现场巡检报障小应用；钉钉 API 文档待确认。",
        "components": [
            {"name": "上报", "tech": "内网 MinIO + 钉钉通知通道"},
            {"name": "审批", "tech": "待确认"},
            {"name": "派修", "tech": "待确认"},
            {"name": "看板", "tech": "待确认"},
        ],
        "data_flow": [
            {"description": "用户上传照片", "components": ["上报"]},
            {"description": "班组长审批", "components": ["审批"]},
            {"description": "班组长派修", "components": ["派修"]},
            {"description": "看板展示", "components": ["看板"]},
        ],
        "api_contracts": [
            {
                "method": "POST",
                "path": "/api/tickets",
                "request": {"body": {"photo_ref": "内网 key", "shop_id": "S1"}},
                "response": {"status": 201, "body": {"ticket_id": "t1"}},
            },
            {
                "method": "POST",
                "path": "/api/approvals",
                "request": {"body": {"ticket_id": "t1", "status": "approved"}},
                "response": {"status": 200, "body": {"ticket_id": "t1"}},
            },
            {
                "method": "POST",
                "path": "/api/assignments",
                "request": {"body": {"ticket_id": "t1", "status": "assigned"}},
                "response": {"status": 200, "body": {"ticket_id": "t1"}},
            },
            {
                "method": "GET",
                "path": "/api/dashboard/tickets",
                "request": {},
                "response": {"status": 200, "body": {"ticket_count": 10}},
            },
        ],
        "security": "照片落内网 MinIO，脱敏后入库，内网边界；钉钉通知通道待对接。",
        "rollout_and_risks": [
            {
                "phase": "1",
                "description": "试点一个车间，确保每个阶段的风险可控。",
                "risks": ["内网存储实现风险", "钉钉通知通道实现风险"],
            }
        ],
    }
    assert _architecture_rollout_thin(inp, thin) is True
    filled = ensure_architecture_rollout_weeks(thin, inp)
    assert _architecture_rollout_thin(inp, filled) is False
    assert re.search(r"W\s*1", str(filled["rollout_and_risks"]), re.I)
    assert re.search(r"W\s*6", str(filled["rollout_and_risks"]), re.I)

    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload={"message": inp},
        output=thin,
        status="completed",
        hints="architecture_design",
    )
    thin_msgs = [
        i["message"]
        for i in (r.get("issues") or [])
        if i.get("code") == "architecture_sections_thin" and i.get("severity") == "error"
    ]
    assert not any("按周切片" in m or "W1" in m for m in thin_msgs)
    assert "invented_third_party_api" not in {
        i["code"] for i in (r.get("issues") or []) if i.get("severity") == "error"
    }


def test_sanitize_architecture_third_party_rewrites_open_platform():
    from core.management.execution_quality_review import (
        sanitize_architecture_third_party,
        _dingtalk_invented_integration,
        review_execution_output,
    )

    inp = "希望对接钉钉但暂无 API 文档；禁止编造未给定的第三方接口细节。"
    dirty = {
        "title": "x",
        "context": "试点",
        "components": [
            {"name": "上报", "description": "负责拍照上报巡检照片，对接钉钉开放平台"},
            {"name": "通知", "description": "负责通知钉钉开放平台"},
        ],
        "api_contracts": [
            {
                "method": "POST",
                "path": "/api/tickets",
                "request": {"body": {"a": 1}},
                "response": {"status": 201, "body": {"id": "1"}},
            }
        ],
        "data_flow": "上报审批派修看板",
        "security": "照片落地内网 MinIO，脱敏，内网边界",
        "rollout_and_risks": "W1-W6 试点",
    }
    clean = sanitize_architecture_third_party(dirty, inp)
    blob = str(clean)
    assert "对接钉钉开放平台" not in blob
    assert "通知通道（钉钉·待确认）" in blob
    assert _dingtalk_invented_integration(inp, clean) is False
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=clean,
        status="completed",
        hints="architecture_design",
    )
    codes = {i["code"] for i in (r.get("issues") or []) if i.get("severity") == "error"}
    assert "invented_third_party_api" not in codes



def test_probe_architecture_sections_marker_present_on_engine_skill():
    probe = probe_quality_sop_markers(
        kind="skill",
        asset_id="architecture_design",
        issue_codes=["architecture_sections_thin", "public_cloud_photo_storage", "invented_third_party_api"],
    )
    assert "architecture_sections_thin" in probe["present_codes"]
    assert "public_cloud_photo_storage" in probe["present_codes"]
    assert "invented_third_party_api" in probe["present_codes"]
    assert probe["all_present"] is True


def test_build_fail_constraint_overlay_skips_runtime_only():
    text = build_fail_constraint_overlay(
        [
            {"code": "runtime_timeout", "severity": "error", "message": "超时"},
            {
                "code": "public_cloud_photo_storage",
                "severity": "error",
                "message": "禁止公有云存照片",
                "suggestion": "用内网 MinIO",
            },
        ]
    )
    assert FAIL_CONSTRAINT_BANNER in text
    assert "禁止公有云存照片" in text
    assert "超时" not in text
    assert "必含键" in text or "完整架构" in text
    # Must NOT leave a copyable lone endpoint JSON (models echo it as the whole answer)
    assert '"method":"POST"' not in text.replace(" ", "")
    # Compact: no multi-line「正确做法」bloat
    assert "正确做法" not in text


def test_build_fail_constraint_overlay_coding_skips_arch_keys():
    """FE coding fail-rerun must not inject architect ADR required keys."""
    text = build_fail_constraint_overlay(
        [
            {
                "code": "undeclared_api_schema_assumption",
                "severity": "warning",
                "message": "任务要求不自行推断 API，但产物定义了请求/响应字段且未标注临时假设",
            },
        ]
    )
    assert FAIL_CONSTRAINT_BANNER in text
    assert "undeclared_api_schema_assumption" in text
    assert "必含键" not in text
    assert "rollout_and_risks" not in text
    assert "ASSUMPTION" in text or "临时假设" in text
    assert "Vite" in text or "package.json" in text


def test_build_fail_constraint_overlay_no_endpoint_echo_bait():
    """run-f300ce2cac43: C→D after fail-rerun because overlay contained method=POST path=/api/tickets."""
    text = build_fail_constraint_overlay(
        [
            {
                "code": "architecture_sections_thin",
                "severity": "error",
                "message": "API 契约过薄：缺少可评审的请求/响应要点",
                "suggestion": "每个端点补充方法/路径/关键字段与响应要点",
            },
            {
                "code": "architecture_sections_thin",
                "severity": "error",
                "message": "产物只是单个 API 端点对象，不是完整架构草稿",
            },
        ]
    )
    assert "完整架构" in text
    assert "严禁复读" in text
    compact = text.replace(" ", "").lower()
    assert "method=post" not in compact
    assert "/api/tickets" not in compact
    assert "request.body=" not in compact
    assert '"method"' not in compact or '"path"' not in compact


def test_dingtalk_not_actual_call_not_false_invent():
    """run-4c35: 「不实际调用钉钉 API」must NOT trip invented_third_party_api."""
    from core.management.execution_quality_review import (
        _dingtalk_invented_integration,
        _invented_third_party_api_hits,
    )

    inp = "约束：希望对接钉钉但暂无 API 文档；禁止编造未给定的第三方接口细节。"
    honest = {
        "title": "巡检报障",
        "components": [
            {"name": "上报", "tech": "内网存储 + 钉钉通知通道"},
        ],
        "security": [
            "通过钉钉通知通道实现审批和派修，不实际调用钉钉 API，减少风险。",
        ],
    }
    assert _dingtalk_invented_integration(inp, honest) is False
    hits = _invented_third_party_api_hits(inp, str(honest))
    assert "调用钉钉接口" not in hits
    assert "DingTalk/钉钉 SDK" not in hits


def test_architecture_lone_api_output_fails():
    from core.management.execution_quality_review import _architecture_output_is_lone_api

    lone = {
        "method": "POST",
        "path": "/api/tickets",
        "request": {"body": {"photo_ref": "x"}},
        "response": {"status": 201, "body": {"ticket_id": "t"}},
    }
    assert _architecture_output_is_lone_api(lone) is True
    full = {"title": "x", "api_contracts": [lone], "components": [{"name": "api"}]}
    assert _architecture_output_is_lone_api(full) is False
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload="请输出完整架构。约束：对接钉钉但暂无 API 文档。",
        output=lone,
        status="completed",
        hints="architecture_design",
    )
    assert r.get("verdict") == "fail"
    msgs = " ".join(i.get("message") or "" for i in (r.get("issues") or []))
    assert "单个 API" in msgs or "完整架构" in msgs


def test_architecture_lone_api_python_repr_in_text_envelope():
    """run-30e631: model echoed API example as text=python-repr; unwrap must not dive into response."""
    from core.management.execution_quality_review import _unwrap_output, _architecture_output_is_lone_api

    wrapped = {
        "text": (
            "{'method': 'POST', 'path': '/api/tickets', 'description': '巡检报障上报', "
            "'request': {'body': {'photo_ref': 'minio://bucket/key', 'shop_id': 'W01', 'desc': '漏油'}}, "
            "'response': {'status': 201, 'body': {'ticket_id': 'tkt_xxx', 'status': 'pending_approval'}}}"
        )
    }
    unwrapped = _unwrap_output(wrapped)
    assert isinstance(unwrapped, dict)
    assert "method" in unwrapped and "path" in unwrapped
    assert _architecture_output_is_lone_api(unwrapped) is True
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=(
            "请输出完整架构草稿（上下文与假设/数据流/API/安全/6周分期）。"
            "约束：对接钉钉但暂无 API 文档。"
        ),
        output=wrapped,
        status="completed",
        hints="architecture_design",
    )
    assert r.get("verdict") == "fail"
    msgs = " ".join(i.get("message") or "" for i in (r.get("issues") or []))
    assert "单个 API" in msgs
    ov = r.get("rerun_constraint_overlay") or ""
    assert "完整架构 JSON" in ov
    assert '"method":"POST"' not in ov.replace(" ", "")


def test_review_primary_action_rerun_when_sop_iron_present():
    """architecture_sections_thin iron already in SKILL.md → CTA = 按失败点重跑."""
    inp = {
        "message": (
            "请输出上下文与假设、数据流、安全与合规、6周分期与风险。"
            "照片不可上公网。"
        )
    }
    out = {
        "title": "巡检",
        "overview": "私有化",
        "components": [{"name": "api"}],
        "open_questions": ["钉钉"],
    }
    r = review_execution_output(
        kind="agent",
        asset_id="architect_agent",
        asset_name="系统架构师",
        input_payload=inp,
        output=out,
        status="completed",
        hints="architecture_design",
    )
    assert r.get("verdict") == "fail"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "architecture_sections_thin" in codes
    # Only assert rerun path when every fixable code already has markers
    fixable = r.get("fixable_issue_codes") or []
    present = set((r.get("sop_iron") or {}).get("present_codes") or [])
    if fixable and set(fixable) <= present:
        assert r.get("primary_action") == "rerun_with_fail_constraints"
        assert FAIL_CONSTRAINT_BANNER in (r.get("rerun_constraint_overlay") or "")
        assert "按失败点重跑" in " ".join((r.get("fix_guide") or {}).get("steps") or [])


def test_clarification_only_fails_when_task_asks_for_code():
    """Coding smoke that only asks「准备好了吗」must not get quality A / pass."""
    inp = (
        "请完成一次编码冒烟：实现 POST /api/v1/inspection/reports 的路由 + Pydantic model；"
        "附 curl 验证说明。"
    )
    out = (
        "好的，让我们开始工作。\n\n"
        "### Step 0：准备阶段\n"
        "1. 从上下文读取 api_contracts\n\n"
        "请确认以下信息：\n"
        "1. api_contracts 是否已经准备好？\n"
        "2. frontend_code.files 列表是否已经准备好？\n\n"
        "如果你已经准备好，请告诉我，我们可以开始下一步。"
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": out},
        status="completed",
        hints="frontend_engineer code_generation",
    )
    assert r["verdict"] == "fail"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "clarification_only" in codes
    assert r.get("primary_action") == "check_runtime"


def test_clarification_only_skips_when_code_present():
    inp = "请完成一次编码冒烟：实现 POST /api/v1/inspection/reports"
    out = (
        "已实现创建报障接口。\n\n"
        "```python\n"
        "class ReportIn(BaseModel):\n"
        "    reporter_id: str\n"
        "```\n\n"
        "curl -X POST http://127.0.0.1:8000/api/v1/inspection/reports ...\n"
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": out},
        status="completed",
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "clarification_only" not in codes


def test_english_clarify_in_code_envelope_fails_quality_a():
    """Regression run-0b130688: code_generation stuffed clarify prose into {code,language}."""
    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成前端代码\n"
        "请完成一次编码冒烟（小切片，可运行）：\n"
        "1. 实现 POST /api/v1/inspection/reports（创建报障）的路由 + Pydantic model；\n"
        "2. 字段：reporter_id, equipment_id, description, photo_uris[]；\n"
        "3. 附 1 个成功 + 1 个校验失败的示例请求；\n"
        "4. 说明如何本地用 curl 验证；"
    )
    clarify = (
        "I understand you want a complete Python code example, but I need more details "
        "on what specific functionality or task you want to implement. Could you please "
        "provide more information or context about what you're looking for? For example, "
        "are you looking for a simple script, a class definition, or a function "
        "implementation? Also, what is the purpose or problem this code should solve? "
        "This will help me provide a more accurate and useful example."
    )
    # Exact shape from agent_executions.output_json for run-0b130688b5b6
    out = {"text": str({"code": clarify, "language": "python"})}
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output=out,
        status="completed",
        hints="frontend_engineer code_generation",
    )
    assert r.get("verdict") == "fail"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "clarification_only" in codes or "thin_code_stub" in codes
    assert (r.get("summary") or {}).get("health") != "A"


def test_code_body_substance_rejects_prose_mentioning_class():
    from core.management.execution_quality_review import _code_body_has_substance

    prose = (
        "I understand you want a complete Python code example. "
        "Are you looking for a class definition or a function implementation?"
    )
    assert _code_body_has_substance(prose) is False
    real = "from fastapi import APIRouter\nclass ReportIn(BaseModel):\n    reporter_id: str\n"
    assert _code_body_has_substance(real) is True


def test_quality_review_blocks_success_for_thin_stub_only():
    assert quality_review_blocks_success(
        {
            "verdict": "fail",
            "issues": [{"severity": "error", "code": "thin_code_stub", "message": "x"}],
        }
    )
    assert quality_review_blocks_success(
        {
            "verdict": "fail",
            "issues": [{"severity": "error", "code": "clarification_only", "message": "x"}],
        }
    )
    assert quality_review_blocks_success(
        {
            "verdict": "fail",
            "issues": [{"severity": "error", "code": "language_mismatch", "message": "x"}],
        }
    )
    assert quality_review_blocks_success(
        {
            "verdict": "fail",
            "issues": [{"severity": "error", "code": "autoreview_incomplete", "message": "x"}],
        }
    )
    # Soft architecture fail stays advisory for status (not hard coding block)
    assert not quality_review_blocks_success(
        {
            "verdict": "fail",
            "issues": [{"severity": "error", "code": "architecture_api_thin", "message": "x"}],
        }
    )
    assert not quality_review_blocks_success({"verdict": "pass", "issues": []})


def test_detect_requested_language_ignores_forbidden_python():
    """「禁止 Python/FastAPI」 must not count as requesting Python."""
    from core.management.execution_quality_review import _detect_requested_code_language

    assert _detect_requested_code_language(
        "生成前端 apiClient（禁止 Python/FastAPI）；输出 ## FILE *.ts"
    ) == "typescript"
    assert (
        _detect_requested_code_language(
            "根据 Architecture 生成前端代码；禁止 Python；实现报障表单切片。"
        )
        is None
    )


def test_detect_requested_language_backend_chip_ignores_banned_tsx():
    """run-c11c4dd16a9f: 「不要生成 Vite / App.tsx」 must not request TypeScript."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _detect_requested_code_language,
        is_non_deliverable_coding_output,
    )

    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成后端代码，不自行推断 API 格式\n"
        "【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。\n"
        "每条路由 + Pydantic；400/404；鉴权 TODO。禁止假对接钉钉。"
        "不要生成 Vite / App.tsx / package.json。\n"
        "不要用能否 uvicorn 启动当验收。\n"
        "调用 code_generation → autoreview → DONE。"
    )
    assert _detect_requested_code_language(inp) == "python"
    blob = (
        "## FILE: inspection_api/router.py\n```python\n"
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/v1/inspection/reports')\n"
        "def create():\n"
        "    return {'id': '1', 'status': 'pending'}  # TODO: auth\n"
        "```\n"
        "## FILE: inspection_api/schemas.py\n```python\n"
        "from pydantic import BaseModel\n"
        "class CreateReport(BaseModel):\n"
        "    reporter_id: str\n"
        "```\n"
    )
    codes = _coding_contract_fail_codes(inp, blob, {"text": blob, "language": "python"})
    assert "language_mismatch" not in codes
    assert not is_non_deliverable_coding_output(
        input_text=inp, output_text=blob, raw_out={"text": blob}
    )


def test_language_mismatch_typescript_vs_python_fails():
    """Regression run-da9cc25d: asked TS API client, got Python print-shell → must fail."""
    inp = (
        "Generate a TypeScript API client from the following api_contracts. "
        "Call code_generation first with full runnable function bodies "
        "(no empty ## FILE stubs), then call autoreview, then DONE.\n\n"
        "api_contracts:\n"
        "endpoints:\n"
        "  - method: GET\n"
        "    path: /api/tasks\n"
        "  - method: POST\n"
        "    path: /api/tasks\n"
        "models:\n"
        "  Task: {id: string, title: string, status: string}\n"
    )
    out = {
        "text": str(
            {
                "code": (
                    "## FILE: api_contracts.py\n```python\n"
                    "class APIContracts:\n"
                    "    def __init__(self):\n"
                    "        self.contracts = {}\n"
                    "```\n\n"
                    "## FILE: autoreview.py\n```python\n"
                    "def autoreview():\n"
                    "    print(\"Autoreview called. Reviewing code...\")\n"
                    "    # Add review logic here\n"
                    "    print(\"Code reviewed. Ready to deliver.\")\n"
                    "```\n\n"
                    "## FILE: deliver.py\n```python\n"
                    "def deliver():\n"
                    "    print(\"Delivering code...\")\n"
                    "    print(\"DONE\")\n"
                    "```\n"
                ),
                "language": "python",
            }
        )
    }
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output=out,
        status="completed",
        hints="frontend_engineer code_generation autoreview",
        skill_trace=[
            {"kind": "skill", "name": "code_generation", "status": "success"},
            {"kind": "skill", "name": "autoreview", "status": "approval_required"},
        ],
    )
    assert r.get("verdict") == "fail"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "language_mismatch" in codes
    assert "off_spec_coding" in codes or "autoreview_incomplete" in codes
    assert "autoreview_incomplete" in codes
    assert (r.get("summary") or {}).get("health") != "A"
    assert quality_review_blocks_success(r)


def test_language_field_stale_python_with_ts_body_not_mismatch():
    """code_generation default language=python must not kill a real TS body (run-2e2d)."""
    from core.management.execution_quality_review import (
        is_non_deliverable_coding_output,
        _detect_output_code_language,
    )

    inp = (
        "Generate a TypeScript API client from api_contracts. "
        "Call code_generation then autoreview then DONE.\n"
        "path: /api/tasks\n"
    )
    code = (
        "## FILE: src/api/tasks.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "export interface Task { id: string; title: string; status: string }\n"
        "export async function getTasks() {\n"
        "  const res = await axios.get('/api/tasks');\n"
        "  return res.data;\n"
        "}\n"
        "export async function createTask(title: string) {\n"
        "  const res = await axios.post('/api/tasks', { title });\n"
        "  return res.data;\n"
        "}\n"
        "```\n"
    )
    assert _detect_output_code_language(code, {"code": code, "language": "python"}) == "typescript"
    assert not is_non_deliverable_coding_output(
        input_text=inp,
        output_text=code,
        raw_out={"code": code, "language": "python", "text": code},
        hints="code_generation",
    )


def test_split_api_base_url_covers_stated_path():
    """apiClient with BASE + '/reports' must cover POST /api/v1/inspection/reports (run-054f7)."""
    from core.management.execution_quality_review import (
        is_non_deliverable_coding_output,
        _path_covered_in_output,
    )

    path = "/api/v1/inspection/reports"
    code = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "const API_BASE_URL = '/api/v1/inspection';\n"
        "export const apiClient = {\n"
        "  async createReport(reporter_id: string, equipment_id: string, "
        "description: string, photo_uris: string[]): Promise<void> {\n"
        "    await axios.post(`${API_BASE_URL}/reports`, {\n"
        "      reporter_id, equipment_id, description, photo_uris\n"
        "    });\n"
        "  }\n"
        "};\n"
        "```\n"
    )
    assert _path_covered_in_output(path, code)
    inp = (
        "请完成一次前端编码冒烟（TypeScript）：仅输出 ## FILE\n"
        "1. 根据契约生成 `apiClient`：POST /api/v1/inspection/reports；\n"
        "调用 code_generation → DONE。"
    )
    assert not is_non_deliverable_coding_output(
        input_text=inp,
        output_text=code,
        raw_out={"code": code, "language": "typescript", "text": code},
        hints="code_generation",
    )


def test_typescript_api_client_matching_language_passes_contract_gates():
    inp = (
        "Generate a TypeScript API client from api_contracts. "
        "Call code_generation then autoreview then DONE.\n"
        "path: /api/tasks\n"
    )
    code = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "export interface Task { id: string; title: string; status: string }\n"
        "export async function listTasks(): Promise<{ items: Task[]; total: number }> {\n"
        "  const res = await fetch('/api/tasks');\n"
        "  return res.json();\n"
        "}\n"
        "export async function createTask(title: string): Promise<Task> {\n"
        "  const res = await fetch('/api/tasks', {\n"
        "    method: 'POST',\n"
        "    body: JSON.stringify({ title }),\n"
        "  });\n"
        "  return res.json();\n"
        "}\n"
        "```\n"
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": str({"code": code, "language": "typescript"})},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "language_mismatch" not in codes
    assert "off_spec_coding" not in codes
    assert "autoreview_incomplete" not in codes
    assert "thin_code_stub" not in codes


def test_frontend_module_incomplete_fails_single_apiclient():
    """FE module task with only apiClient.ts must fail frontend_module_incomplete."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "请完成一次可组装前端模块（TypeScript/TSX）：\n"
        "1. ## FILE: frontend/src/types.ts；\n"
        "2. ## FILE: frontend/src/api/apiClient.ts — POST /api/v1/inspection/reports；\n"
        "3. ## FILE: frontend/src/pages/ReportFaultPage.tsx；\n"
        "鉴权未给出则标 TODO。调用 code_generation → autoreview → DONE。"
    )
    thin = (
        "## FILE: frontend/src/api/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "// TODO: auth\n"
        "export async function createReport(body: {\n"
        "  reporter_id: string; equipment_id: string;\n"
        "  description: string; photo_uris: string[];\n"
        "}) {\n"
        "  return axios.post('/api/v1/inspection/reports', body);\n"
        "}\n```\n"
    )
    codes = _coding_contract_fail_codes(
        input_text=inp,
        output_text=thin,
        hints="frontend_engineer code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "frontend_module_incomplete" in codes

    good = (
        "## FILE: frontend/src/types.ts\n```typescript\n"
        "export type ReportBody = {\n"
        "  reporter_id: string; equipment_id: string;\n"
        "  description: string; photo_uris: string[];\n"
        "};\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "import type { ReportBody } from '../types';\n"
        "// TODO: auth\n"
        "export async function createReport(body: ReportBody) {\n"
        "  return axios.post('/api/v1/inspection/reports', body);\n"
        "}\n```\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\n"
        "import { useState } from 'react';\n"
        "import { createReport } from '../api/apiClient';\n"
        "export function ReportFaultPage() {\n"
        "  const [desc, setDesc] = useState('');\n"
        "  return (\n"
        "    <form onSubmit={(e) => {\n"
        "      e.preventDefault();\n"
        "      void createReport({\n"
        "        reporter_id: 'u1', equipment_id: 'e1',\n"
        "        description: desc, photo_uris: [],\n"
        "      });\n"
        "    }}>\n"
        "      <textarea value={desc} onChange={(e) => setDesc(e.target.value)} />\n"
        "      <button type=\"submit\">上报</button>\n"
        "    </form>\n"
        "  );\n"
        "}\n```\n"
    )
    good_codes = _coding_contract_fail_codes(
        input_text=inp,
        output_text=good,
        hints="frontend_engineer code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "frontend_module_incomplete" not in good_codes
    assert "frontend_flow_pages_incomplete" not in good_codes
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": good},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert not quality_review_blocks_success(r)


def test_frontend_flow_pages_incomplete_fails_single_page_on_triad_prd():
    """上报/审批/派修 PRD with only ReportFaultPage must fail multi-flow gate."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_multi_flow_frontend,
        is_non_deliverable_coding_output,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成前端代码\n"
        "【输入摘要】\n- PRD：巡检报障（上报/审批/派修）\n"
        "- api_contracts 前缀：/api/v1/inspection\n"
        "请交付可组装前端模块（TypeScript/TSX）。不要写死成单页冒烟。\n"
        "调用 code_generation → autoreview → DONE。"
    )
    assert _input_asks_multi_flow_frontend(inp) is True

    single = (
        "## FILE: frontend/src/types.ts\n```typescript\n"
        "export interface CreateReportRequest {\n"
        "  reporter_id: string; equipment_id: string;\n"
        "  description: string; photo_uris: string[];\n"
        "}\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```typescript\n"
        "import type { CreateReportRequest } from '../types';\n"
        "// TODO: auth\n"
        "export async function createReport(body: CreateReportRequest) {\n"
        "  return fetch('/api/v1/inspection/reports', {\n"
        "    method: 'POST', body: JSON.stringify(body),\n"
        "  }).then((r) => r.json());\n"
        "}\n```\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\n"
        "import { createReport } from '../api/apiClient';\n"
        "export default function ReportFaultPage() {\n"
        "  return <button onClick={() => void createReport({\n"
        "    reporter_id: 'u', equipment_id: 'e', description: 'd', photo_uris: [],\n"
        "  })}>上报</button>;\n"
        "}\n```\n"
    )
    codes = _coding_contract_fail_codes(
        input_text=inp,
        output_text=single,
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "frontend_flow_pages_incomplete" in codes
    assert is_non_deliverable_coding_output(
        input_text=inp,
        output_text=single,
        raw_out={"text": single, "language": "typescript"},
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )

    multi = single + (
        "## FILE: frontend/src/pages/ApproveFaultPage.tsx\n```tsx\n"
        "export default function ApproveFaultPage() { return <div>审批</div>; }\n```\n"
        "## FILE: frontend/src/pages/DispatchRepairPage.tsx\n```tsx\n"
        "export default function DispatchRepairPage() { return <div>派修</div>; }\n```\n"
    )
    good_codes = _coding_contract_fail_codes(
        input_text=inp,
        output_text=multi,
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "frontend_flow_pages_incomplete" not in good_codes
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": single},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert any(i.get("code") == "frontend_flow_pages_incomplete" for i in (r.get("issues") or []))
    assert quality_review_blocks_success(r)


def test_isolated_fe_recipe_does_not_trigger_scaffold_gate():
    """「无 project_scaffold / 禁止 FastAPI」单独测用例不得误触脚手架门禁。"""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_multi_flow_frontend,
        _input_asks_startable_scaffold,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成前端代码，不自行推断 API 格式\n"
        "【单独测·可组装切片】本用例测业务模块，不是 Vite 工程。"
        "不要生成 package.json / vite.config；不要用能否 `npm run dev` 判断成败。\n"
        "【验收标准】至少 3 个页面：ReportFaultPage / ApproveFaultPage / DispatchRepairPage\n"
        "【输入摘要】无 project_scaffold（单独测 Agent）\n"
        "【api_contracts】\n"
        "- POST /api/v1/inspection/reports body: reporter_id, equipment_id, description, photo_uris[]\n"
        "- GET  /api/v1/inspection/reports\n"
        "- POST /api/v1/inspection/reports/{id}/approve\n"
        "- POST /api/v1/inspection/reports/{id}/dispatch\n"
        "禁止 Python/FastAPI。调用 code_generation → autoreview → DONE。"
    )
    assert _input_asks_startable_scaffold(inp) is False
    assert _input_asks_multi_flow_frontend(inp) is True

    good = (
        "## FILE: frontend/src/types.ts\n```ts\n"
        "export interface CreateReportRequest {"
        " reporter_id: string; equipment_id: string;"
        " description: string; photo_uris: string[]; }\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```ts\n"
        "// TODO: auth\n"
        "export async function createReport(p: CreateReportRequest) {"
        " return fetch('/api/v1/inspection/reports',{method:'POST',body:JSON.stringify(p)}); }\n"
        "export async function listReports() {"
        " return fetch('/api/v1/inspection/reports'); }\n"
        "export async function approveReport(id: string) {"
        " return fetch(`/api/v1/inspection/reports/${id}/approve`,{method:'POST'}); }\n"
        "export async function dispatchReport(id: string) {"
        " return fetch(`/api/v1/inspection/reports/${id}/dispatch`,{method:'POST'}); }\n```\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\n"
        "import { createReport } from '../api/apiClient';\n"
        "export default function ReportFaultPage() { return <div/>; }\n```\n"
        "## FILE: frontend/src/pages/ApproveFaultPage.tsx\n```tsx\n"
        "import { listReports, approveReport } from '../api/apiClient';\n"
        "export default function ApproveFaultPage() { return <div/>; }\n```\n"
        "## FILE: frontend/src/pages/DispatchRepairPage.tsx\n```tsx\n"
        "import { dispatchReport } from '../api/apiClient';\n"
        "export default function DispatchRepairPage() { return <div/>; }\n```\n"
    )
    codes = _coding_contract_fail_codes(inp, good, {"text": good})
    assert "scaffold_startup_incomplete" not in codes
    assert "scaffold_not_on_disk" not in codes
    assert "frontend_flow_pages_incomplete" not in codes
    assert "isolated_fe_vite_files" not in codes
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": good},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert not any(
        i.get("code") == "scaffold_startup_incomplete" for i in (r.get("issues") or [])
    )
    assert not quality_review_blocks_success(r) or not any(
        i.get("code") == "scaffold_startup_incomplete" for i in (r.get("issues") or [])
    )


def test_isolated_fe_extra_vite_entry_is_warning_not_hard_fail():
    """Isolated slice that also ships App.tsx/main.tsx is a warn, not a failed run."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_isolated_frontend_slice,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "【单独测·可组装切片】不是 Vite 工程。不要生成 package.json；"
        "无 project_scaffold。ApproveFaultPage DispatchRepairPage\n"
    )
    assert _input_asks_isolated_frontend_slice(inp) is True
    blob = (
        "## FILE: frontend/src/types.ts\n```ts\nexport type Id = string;\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```ts\n"
        "// TODO: auth\nexport async function listReports(){ return fetch('/api/v1/inspection/reports'); }\n```\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\nexport default function ReportFaultPage(){return <div/>}\n```\n"
        "## FILE: frontend/src/pages/ApproveFaultPage.tsx\n```tsx\nexport default function ApproveFaultPage(){return <div/>}\n```\n"
        "## FILE: frontend/src/pages/DispatchRepairPage.tsx\n```tsx\nexport default function DispatchRepairPage(){return <div/>}\n```\n"
        "## FILE: frontend/src/App.tsx\n```tsx\nexport default function App(){return <div/>}\n```\n"
        "## FILE: frontend/src/main.tsx\n```tsx\nimport App from './App';\n```\n"
    )
    codes = _coding_contract_fail_codes(inp, blob, {"text": blob})
    assert "isolated_fe_vite_files" in codes
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": blob},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    issue = next(i for i in (r.get("issues") or []) if i.get("code") == "isolated_fe_vite_files")
    assert issue.get("severity") == "warning"
    assert r.get("verdict") == "warn"
    assert quality_review_blocks_success(r) is False


def test_isolated_backend_extra_vite_files_same_gate_as_frontend():
    """Programmer/backend isolated slice must not ship Vite entries either."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_isolated_coding_slice,
        review_execution_output,
    )

    inp = (
        "【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。"
        "不要用能否单独启动服务判断成败。无 project_scaffold。\n"
        "禁止 Vite/package.json。调用 code_generation → DONE。"
    )
    assert _input_asks_isolated_coding_slice(inp) is True
    blob = (
        "## FILE: backend/routes.py\n```python\n"
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/v1/inspection/reports')\n"
        "def create():\n"
        "    return {'id': '1', 'status': 'pending'}\n"
        "```\n"
        "## FILE: frontend/src/App.tsx\n```tsx\nexport default function App(){return <div/>}\n```\n"
        "## FILE: frontend/package.json\n```json\n{\"name\":\"fe\"}\n```\n"
    )
    codes = _coding_contract_fail_codes(inp, blob, {"text": blob})
    assert "isolated_fe_vite_files" in codes
    r = review_execution_output(
        kind="agent",
        asset_id="programmer_agent",
        asset_name="程序员",
        input_payload={"message": inp},
        output={"text": blob},
        status="completed",
        hints="code_generation",
    )
    assert any(i.get("code") == "isolated_fe_vite_files" for i in (r.get("issues") or []))
    assert r.get("verdict") in ("warn", "fail")


def test_backend_isolated_triad_prd_does_not_require_tsx_pages():
    """上报/审批/派修 in a backend API slice must not inherit FE 3-page gates."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_backend_api_slice,
        _input_asks_frontend_module,
        _input_asks_multi_flow_frontend,
    )

    inp = (
        "【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。\n"
        "【输入摘要】PRD：巡检报障（上报/审批/派修）；无 project_scaffold\n"
        "Pydantic 字段与契约一致；## FILE: 切片（routes + schemas）。\n"
        "鉴权 TODO。调用 code_generation → DONE。\n"
    )
    assert _input_asks_backend_api_slice(inp) is True
    assert _input_asks_frontend_module(inp) is False
    assert _input_asks_multi_flow_frontend(inp) is False
    blob = (
        "## FILE: backend/routes.py\n```python\n"
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/v1/inspection/reports')\n"
        "def create():\n"
        "    return {'id': '1', 'status': 'pending'}  # TODO: auth\n"
        "```\n"
        "## FILE: backend/schemas.py\n```python\n"
        "from pydantic import BaseModel\n"
        "class CreateReport(BaseModel):\n"
        "    reporter_id: str\n"
        "    equipment_id: str\n"
        "    description: str\n"
        "    photo_uris: list\n"
        "```\n"
    )
    codes = _coding_contract_fail_codes(inp, blob, {"text": blob})
    assert "frontend_flow_pages_incomplete" not in codes
    assert "frontend_module_incomplete" not in codes


def test_scaffold_startup_incomplete_fails_readme_only_frontend():
    """Scaffold that only drops frontend/README.md is not a startable app."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_startable_scaffold,
        is_non_deliverable_coding_output,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "请生成可启动的前后端工程骨架（不要写业务 CRUD）：\n"
        "1. FastAPI：main.py + requirements.txt，uvicorn main:app --port 8000；\n"
        "2. Vite：frontend/package.json、vite.config.ts、index.html、src/main.tsx、src/App.tsx。\n"
        "禁止只交 frontend/README.md。调用 code_generation → DONE。"
    )
    assert _input_asks_startable_scaffold(inp) is True

    thin = (
        "## FILE: main.py\n```python\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'ok': True}\n"
        "```\n"
        "## FILE: requirements.txt\n```\nfastapi\nuvicorn\n```\n"
        "## FILE: frontend/README.md\n```markdown\nFE will work here.\n```\n"
    )
    codes = _coding_contract_fail_codes(inp, thin, {"text": thin})
    assert "scaffold_startup_incomplete" in codes
    assert is_non_deliverable_coding_output(
        input_text=inp, output_text=thin, raw_out={"text": thin}
    )

    good = thin.replace(
        "## FILE: frontend/README.md\n```markdown\nFE will work here.\n```\n",
        "## FILE: frontend/package.json\n```json\n"
        '{"name":"fe","scripts":{"dev":"vite"},"dependencies":{"react":"18.3.1"}}\n```\n'
        "## FILE: frontend/vite.config.ts\n```ts\n"
        "import { defineConfig } from 'vite';\n"
        "export default defineConfig({ server: { proxy: { '/api': 'http://127.0.0.1:8000' } } });\n```\n"
        "## FILE: frontend/index.html\n```html\n<div id='root'></div><script type='module' src='/src/main.tsx'></script>\n```\n"
        "## FILE: frontend/src/main.tsx\n```tsx\n"
        "import React from 'react';\nimport { createRoot } from 'react-dom/client';\n"
        "import App from './App';\ncreateRoot(document.getElementById('root')!).render(<App />);\n```\n"
        "## FILE: frontend/src/App.tsx\n```tsx\n"
        "export default function App() { return <div>ok</div>; }\n```\n"
        "## FILE: frontend/tsconfig.json\n```json\n"
        '{"compilerOptions":{"jsx":"react-jsx","strict":true},"include":["src"]}\n```\n'
        "## FILE: README.md\n```markdown\n"
        "backend: uvicorn main:app --port 8000\nfrontend: cd frontend && npm i && npm run dev\n```\n",
    )
    good_codes = _coding_contract_fail_codes(inp, good, {"text": good})
    assert "scaffold_startup_incomplete" not in good_codes
    assert "scaffold_not_on_disk" in good_codes
    assert "language_mismatch" not in good_codes
    persisted_codes = _coding_contract_fail_codes(
        inp, good, {"text": good, "persisted_root": "/tmp/run_workspaces/run-x"}
    )
    assert "scaffold_not_on_disk" not in persisted_codes
    r = review_execution_output(
        kind="agent",
        asset_id="scaffold_agent",
        asset_name="工程脚手架生成",
        input_payload={"message": inp},
        output={"text": thin},
        status="completed",
        hints="code_generation",
    )
    assert any(i.get("code") == "scaffold_startup_incomplete" for i in (r.get("issues") or []))
    assert quality_review_blocks_success(r)


def test_scaffold_fails_stray_python_quotes_and_missing_tsconfig():
    """Stray module \"\"\" or Vite+TS without tsconfig is not startable."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _delivered_python_quotes_broken,
        _python_triple_quotes_broken,
        _scaffold_missing_tsconfig,
        is_non_deliverable_coding_output,
    )

    inp = (
        "请生成可启动的前后端工程骨架（不要写业务 CRUD）：\n"
        "1. FastAPI：main.py + requirements.txt；\n"
        "2. Vite：frontend/package.json、vite.config.ts、index.html、"
        "src/main.tsx、src/App.tsx、tsconfig.json。\n"
        "调用 code_generation → DONE。"
    )
    assert _python_triple_quotes_broken(
        '"""\nfrom fastapi import FastAPI\napp = FastAPI()\n'
        '@app.get("/health")\ndef health():\n'
        '    """health."""\n    return {"status": "ok"}\n'
    )
    assert not _python_triple_quotes_broken(
        '"""FastAPI 空壳。"""\nfrom fastapi import FastAPI\napp = FastAPI()\n'
    )

    chain = (
        "## FILE: requirements.txt\n```\nfastapi\nuvicorn\n```\n"
        "## FILE: frontend/package.json\n```json\n"
        '{"name":"fe","scripts":{"dev":"vite","build":"tsc && vite build"},'
        '"dependencies":{"react":"18.3.1"}}\n```\n'
        "## FILE: frontend/vite.config.ts\n```ts\n"
        "import { defineConfig } from 'vite';\nexport default defineConfig({});\n```\n"
        "## FILE: frontend/index.html\n```html\n"
        "<div id='root'></div><script type='module' src='/src/main.tsx'></script>\n```\n"
        "## FILE: frontend/src/main.tsx\n```tsx\n"
        "import App from './App';\n```\n"
        "## FILE: frontend/src/App.tsx\n```tsx\n"
        "export default function App() { return <div>ok</div>; }\n```\n"
        "## FILE: README.md\n```markdown\nuvicorn + npm run dev\n```\n"
    )
    stray = (
        "## FILE: main.py\n```python\n"
        '"""\n'
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "@app.get('/health')\n"
        "def health():\n"
        '    """probe"""\n'
        "    return {'status': 'ok'}\n"
        "```\n" + chain
    )
    assert _delivered_python_quotes_broken(stray)
    stray_codes = _coding_contract_fail_codes(inp, stray, {"text": stray})
    assert "scaffold_startup_incomplete" in stray_codes
    assert is_non_deliverable_coding_output(
        input_text=inp, output_text=stray, raw_out={"text": stray}
    )

    no_ts = (
        "## FILE: main.py\n```python\n"
        '"""ok"""\nfrom fastapi import FastAPI\napp = FastAPI()\n```\n' + chain
    )
    assert _scaffold_missing_tsconfig(no_ts)
    no_ts_codes = _coding_contract_fail_codes(inp, no_ts, {"text": no_ts})
    assert "scaffold_startup_incomplete" in no_ts_codes

    ok = no_ts + (
        "## FILE: frontend/tsconfig.json\n```json\n"
        '{"compilerOptions":{"jsx":"react-jsx"},"include":["src"]}\n```\n'
    )
    ok_codes = _coding_contract_fail_codes(inp, ok, {"text": ok})
    assert "scaffold_startup_incomplete" not in ok_codes
    assert "broken_python_quotes" not in ok_codes
    assert "scaffold_not_on_disk" in ok_codes
    ok_disk = {"text": ok, "persisted_root": "/tmp/run_workspaces/run-ok"}
    assert "scaffold_not_on_disk" not in _coding_contract_fail_codes(inp, ok, ok_disk)
    assert not is_non_deliverable_coding_output(
        input_text=inp, output_text=ok, raw_out=ok_disk
    )


def test_scaffold_rereview_bare_markdown_uses_run_workspace(tmp_path, monkeypatch):
    """UI often POSTs unwrapped markdown; must not false-fail scaffold_not_on_disk."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        review_execution_output,
    )

    home = tmp_path / "aiplat-home"
    rid = "run-ui-rereview"
    root = home / "run_workspaces" / rid
    root.mkdir(parents=True)
    (root / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    inp = (
        "请生成可启动的前后端工程骨架（不要写业务 CRUD）：\n"
        "1. FastAPI：main.py + requirements.txt；\n"
        "2. Vite：frontend/package.json、vite.config.ts、index.html、"
        "src/main.tsx、src/App.tsx、tsconfig.json。\n"
        "调用 code_generation → DONE。"
    )
    blob = (
        "## FILE: main.py\n```python\n"
        '"""ok"""\nfrom fastapi import FastAPI\napp = FastAPI()\n```\n'
        "## FILE: requirements.txt\n```\nfastapi\nuvicorn\n```\n"
        "## FILE: frontend/package.json\n```json\n"
        '{"name":"fe","scripts":{"dev":"vite"},"dependencies":{"react":"18.3.1"}}\n```\n'
        "## FILE: frontend/vite.config.ts\n```ts\n"
        "import { defineConfig } from 'vite';\nexport default defineConfig({});\n```\n"
        "## FILE: frontend/index.html\n```html\n"
        "<div id='root'></div><script type='module' src='/src/main.tsx'></script>\n```\n"
        "## FILE: frontend/src/main.tsx\n```tsx\nimport App from './App';\n```\n"
        "## FILE: frontend/src/App.tsx\n```tsx\n"
        "export default function App() { return <div>ok</div>; }\n```\n"
        "## FILE: frontend/tsconfig.json\n```json\n"
        '{"compilerOptions":{"jsx":"react-jsx"},"include":["src"]}\n```\n'
        "## FILE: README.md\n```markdown\nuvicorn + npm run dev\n```\n"
    )
    assert "scaffold_not_on_disk" not in _coding_contract_fail_codes(
        inp, blob, blob, run_id=rid
    )
    r = review_execution_output(
        kind="agent",
        asset_id="scaffold_agent",
        asset_name="工程脚手架生成",
        input_payload={"message": inp},
        output=blob,
        status="completed",
        execution_id=rid,
    )
    assert r.get("verdict") == "pass"
    assert not any(
        i.get("code") == "scaffold_not_on_disk" for i in (r.get("issues") or [])
    )


def test_isolated_backend_broken_quotes_hard_fail():
    """Non-scaffold FastAPI slice with an unclosed \"\"\" still fails."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        is_non_deliverable_coding_output,
    )

    inp = (
        "【单独测·可组装切片】测 API 模块，不是完整 uvicorn 工程。"
        "Pydantic + APIRouter。调用 code_generation → DONE。"
    )
    blob = (
        "## FILE: backend/routes.py\n```python\n"
        '"""\n'
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "```\n"
    )
    codes = _coding_contract_fail_codes(inp, blob, {"text": blob})
    assert "broken_python_quotes" in codes
    assert "scaffold_startup_incomplete" not in codes
    assert is_non_deliverable_coding_output(
        input_text=inp, output_text=blob, raw_out={"text": blob}, scope="skill"
    )


def test_sibling_relative_imports_not_dangling():
    """同批交付的 types/apiClient/page 互相 import 不算悬空。"""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _dangling_local_imports,
    )

    blob = (
        "## FILE: frontend/src/types.ts\n```typescript\n"
        "export interface CreateInspectionReportRequest { title: string }\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```typescript\n"
        "import type { CreateInspectionReportRequest } from '../types';\n"
        "import axios from 'axios';\n"
        "// TODO: auth\n"
        "export async function createReport(body: CreateInspectionReportRequest) {\n"
        "  return axios.post('/api/v1/inspection/reports', body);\n"
        "}\n```\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\n"
        "import { createReport } from '../api/apiClient';\n"
        "export default function ReportFaultPage() { return null }\n```\n"
    )
    assert _dangling_local_imports(blob) == []
    codes = _coding_contract_fail_codes(
        input_text="生成前端模块 apiClient POST /api/v1/inspection/reports",
        output_text=blob,
        hints="code_generation",
        skill_trace=[{"name": "code_generation", "status": "success"}],
    )
    assert "dangling_local_import" not in codes


def test_undeclared_api_schema_assumption_warns_when_overview_only_assumes():
    """run-c66b5f: prose 假设 must not absolve types.ts that invents fields +「不推断」."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _undeclared_api_schema_assumption,
        is_non_deliverable_coding_output,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成前端代码，不自行推断 API 格式\n"
        "【输入摘要】\n- PRD：巡检报障\n- api_contracts 前缀：/api/v1/inspection\n"
        "请完成可组装前端模块（TypeScript/TSX）。"
    )
    # Overview claims ASSUMPTION; types.ts invents fields and denies inference.
    bad = (
        "### 步骤4：最优方案与关键假设\n\n"
        "**假设（因 `api_contracts` 未给出字段级细节，按最小可运行切片声明）**：\n\n"
        "## FILE: frontend/src/types.ts\n```typescript\n"
        "/** 约束：本文件不推断 API 格式，字段以 api_contracts 为准。 */\n"
        "export interface CreateInspectionReportRequest {\n"
        "  title: string;\n"
        "  location: string;\n"
        "  severity: string;\n"
        "  description: string;\n"
        "}\n"
        "export interface InspectionReportResponse {\n"
        "  id: string;\n"
        "  status: string;\n"
        "}\n```\n"
        "## FILE: frontend/src/api/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "// TODO: auth\n"
        "export async function createReport(body: CreateInspectionReportRequest) {\n"
        "  return axios.post('/api/v1/inspection/reports', body);\n"
        "}\n```\n"
        # Minimal page so frontend_module_incomplete does not mask the warn
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n```tsx\n"
        "export default function ReportFaultPage() {\n"
        "  return <form onSubmit={() => createReport({ title: '', location: '', severity: '', description: '' })} />;\n"
        "}\n```\n"
    )
    assert _undeclared_api_schema_assumption(inp, bad) is True
    codes = _coding_contract_fail_codes(
        input_text=inp,
        output_text=bad,
        hints="code_generation",
        skill_trace=[{"name": "code_generation", "status": "success"}],
    )
    assert "undeclared_api_schema_assumption" in codes
    assert "frontend_module_incomplete" not in codes
    # Soft warn must NOT seal the run as non-deliverable / failed (run-c896745b).
    assert not is_non_deliverable_coding_output(
        input_text=inp,
        output_text=bad,
        raw_out={"code": bad, "language": "typescript", "text": bad},
        hints="code_generation",
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"text": bad},
        status="completed",
        hints="code_generation",
    )
    assert r.get("verdict") == "warn"
    assert any(i.get("code") == "undeclared_api_schema_assumption" for i in r.get("issues") or [])
    assert not quality_review_blocks_success(r)


    # Honest: ASSUMPTION marker lives inside the types FILE → no flag
    honest = bad.replace(
        "/** 约束：本文件不推断 API 格式，字段以 api_contracts 为准。 */\n",
        "/** 临时假设：字段待真实 api_contracts 覆盖（ASSUMPTION）。 */\n",
    )
    assert _undeclared_api_schema_assumption(inp, honest) is False

    # 「假设契约（因…」inside types.ts also counts as honest labeling (run-c896745b).
    honest_qy = bad.replace(
        "/** 约束：本文件不推断 API 格式，字段以 api_contracts 为准。 */\n",
        "// 假设契约（因 api_contracts 未完整提供，此处为最小可运行切片）\n",
    )
    assert _undeclared_api_schema_assumption(inp, honest_qy) is False

    # import { type XxxRequest } must not count as inventing schema (run-c896745b apiClient).
    from core.management.execution_quality_review import _invents_request_response_schema

    api_only = (
        "import {\n"
        "  type CreateReportRequest,\n"
        "  type CreateReportResponse,\n"
        '} from "../types";\n'
        "export function createReport(p: CreateReportRequest): Promise<CreateReportResponse> {\n"
        "  return fetch('/api/v1/inspection/reports', { method: 'POST', body: JSON.stringify(p) })"
        ".then(r => r.json());\n"
        "}\n"
    )
    assert _invents_request_response_schema(api_only) is False

    # Declared fields in the task → not "invented"
    declared_inp = (
        inp + "\n请求体字段：title, location, severity, description；"
    )
    assert _undeclared_api_schema_assumption(declared_inp, bad) is False


def test_missing_auth_todo_and_dangling_import_fail_review():
    """Regression run-1b2df4ffd82c: TS client greenwashed without auth TODO + ./utils."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        is_non_deliverable_coding_output,
        quality_review_blocks_success,
        review_execution_output,
    )

    inp = (
        "任务背景：根据 Architecture 中的 api_contracts 生成前端代码\n"
        "请完成一次前端编码冒烟（TypeScript）：\n"
        "1. 根据契约生成 apiClient：POST /api/v1/inspection/reports；\n"
        "2. 字段：reporter_id, equipment_id, description, photo_uris[]；\n"
        "3. 用 ## FILE: *.ts 输出完整函数体；\n"
        "4. 附成功+校验失败示例；\n"
        "5. 鉴权未给出则标 TODO，禁止假实现「已对接钉钉」。\n"
        "调用 code_generation → autoreview → DONE。"
    )
    bad = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "import { reportSuccess, reportFail } from './utils';\n"
        "const API_URL = '/api/v1/inspection/reports';\n"
        "async function apiClient(\n"
        "  reporterId: string, equipmentId: string,\n"
        "  description: string, photoUris: string[]\n"
        "): Promise<void> {\n"
        "  const response = await axios.post(API_URL, {\n"
        "    reporter_id: reporterId,\n"
        "    equipment_id: equipmentId,\n"
        "    description,\n"
        "    photo_uris: photoUris,\n"
        "  });\n"
        "  reportSuccess(response.data);\n"
        "}\n"
        "```\n"
    )
    codes = _coding_contract_fail_codes(
        inp,
        bad,
        {"code": bad, "language": "typescript"},
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "missing_auth_todo" in codes
    assert "dangling_local_import" in codes
    assert is_non_deliverable_coding_output(
        input_text=inp,
        output_text=bad,
        raw_out={"code": bad, "language": "typescript"},
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"code": bad, "language": "typescript", "text": bad},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert r.get("verdict") == "fail"
    issue_codes = {i["code"] for i in (r.get("issues") or [])}
    assert "missing_auth_todo" in issue_codes
    assert "dangling_local_import" in issue_codes
    assert quality_review_blocks_success(r)

    good = (
        "## FILE: src/apiClient.ts\n```typescript\n"
        "import axios from 'axios';\n"
        "// TODO: auth/鉴权 — bearer token not specified in api_contracts\n"
        "const API_URL = '/api/v1/inspection/reports';\n"
        "export async function createInspectionReport(body: {\n"
        "  reporter_id: string;\n"
        "  equipment_id: string;\n"
        "  description: string;\n"
        "  photo_uris: string[];\n"
        "}) {\n"
        "  const res = await axios.post(API_URL, body);\n"
        "  return res.data;\n"
        "}\n"
        "// success\n"
        "createInspectionReport({\n"
        "  reporter_id: 'u1', equipment_id: 'e1',\n"
        "  description: 'leak', photo_uris: ['s3://in/a.jpg'],\n"
        "});\n"
        "// validation fail example (empty description)\n"
        "createInspectionReport({\n"
        "  reporter_id: 'u1', equipment_id: 'e1',\n"
        "  description: '', photo_uris: [],\n"
        "});\n"
        "```\n"
    )
    r2 = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"code": good, "language": "typescript", "text": good},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    good_codes = {i["code"] for i in (r2.get("issues") or [])}
    assert "missing_auth_todo" not in good_codes


def test_auth_todo_only_in_prose_still_fails():
    """Prose claim「添加了 TODO: auth」outside fences must not greenwash (run-62d703)."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _ensure_auth_todo_comment,
        _output_has_auth_todo,
        review_execution_output,
        quality_review_blocks_success,
    )

    inp = (
        "生成前端 apiClient：POST /api/v1/inspection/reports；"
        "鉴权未给出则标 TODO，禁止假实现「已对接钉钉」。"
    )
    prose_only = (
        "```typescript\n"
        "## FILE: apiClient.ts\n"
        "class ApiClient {\n"
        "  async postReport(body: ReportRequest): Promise<ApiResponse> {\n"
        "    const url = `${this.apiBaseUrl}/api/v1/inspection/reports`;\n"
        "    return fetch(url, { method: 'POST', body: JSON.stringify(body) }).then(r => r.json());\n"
        "  }\n"
        "}\n"
        "interface ReportRequest { reporter_id: string; equipment_id: string; description: string; photo_uris: string[]; }\n"
        "interface ApiResponse { success: boolean; message: string; }\n"
        "```\n\n"
        "在这个实现中，由于鉴权信息未给出，我们添加了 `TODO: auth/鉴权` 注释来表示这一点。\n"
    )
    assert not _output_has_auth_todo(prose_only)
    codes = _coding_contract_fail_codes(
        inp,
        prose_only,
        {"code": prose_only, "language": "typescript", "_language_locked": True},
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "missing_auth_todo" in codes
    patched = _ensure_auth_todo_comment(prose_only, language="typescript")
    assert _output_has_auth_todo(patched)
    assert "// TODO: auth" in patched
    assert "missing_auth_todo" not in _coding_contract_fail_codes(
        inp,
        patched,
        {"code": patched, "language": "typescript", "_language_locked": True},
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output={"code": prose_only, "language": "typescript", "_language_locked": True},
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert r.get("verdict") == "fail"
    assert "missing_auth_todo" in {i["code"] for i in (r.get("issues") or [])}
    assert quality_review_blocks_success(r)


def test_ensure_auth_todo_prefers_apiclient_fence_over_page():
    """run-91896f56: markdown ### TODO: auth must not count; patch apiClient fence."""
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _ensure_auth_todo_comment,
        _output_has_auth_todo,
    )

    inp = "鉴权标 TODO。生成 apiClient + ReportFaultPage。"
    blob = (
        "## FILE: frontend/src/api/apiClient.ts\n"
        "```typescript\n"
        "import axios from 'axios';\n"
        "\n"
        "export const apiClient = axios.create({ baseURL: '/api/v1/inspection' });\n"
        "export async function postReports(data: object) {\n"
        "  return (await apiClient.post('/reports', data)).data;\n"
        "}\n"
        "```\n\n"
        "## FILE: frontend/src/pages/ReportFaultPage.tsx\n"
        "```tsx\n"
        "import React from 'react';\n"
        "import { postReports } from '../api/apiClient';\n"
        "export const ReportFaultPage = () => <button onClick={() => postReports({})} />;\n"
        "```\n\n"
        "### TODO: auth/鉴权\n"
        "在实际应用中需要添加鉴权。\n"
    )
    assert not _output_has_auth_todo(blob)
    assert "missing_auth_todo" in _coding_contract_fail_codes(inp, blob, {"code": blob})
    patched = _ensure_auth_todo_comment(blob, language="typescript")
    assert _output_has_auth_todo(patched)
    # Comment lands in apiClient fence (before page)
    api_idx = patched.find("apiClient.ts")
    page_idx = patched.find("ReportFaultPage")
    todo_idx = patched.find("// TODO: auth")
    assert api_idx >= 0 and todo_idx > api_idx and (page_idx < 0 or todo_idx < page_idx)
    assert "missing_auth_todo" not in _coding_contract_fail_codes(
        inp, patched, {"code": patched, "language": "typescript"}
    )


def test_stringified_code_envelope_still_flags_dangling_import():
    """Stored output often is {text: \"{'code': ...}\"} — must unwrap then see ./utils."""
    from core.management.execution_quality_review import quality_review_blocks_success

    inp = (
        "前端编码冒烟 TypeScript apiClient POST /api/v1/inspection/reports；"
        "鉴权未给出则标 TODO，禁止假实现「已对接钉钉」。"
        "调用 code_generation → autoreview → DONE。"
    )
    code = (
        "## FILE: src/apiClient.ts\n\n```typescript\n"
        "import axios from 'axios';\n"
        "import { reportSuccess, reportFail } from './utils';\n"
        "const API_URL = '/api/v1/inspection/reports';\n"
        "async function apiClient(a: string, b: string, c: string, d: string[]) {\n"
        "  const response = await axios.post(API_URL, {\n"
        "    reporter_id: a, equipment_id: b, description: c, photo_uris: d,\n"
        "  });\n"
        "  reportSuccess(response.data);\n"
        "}\n"
        "```\n"
    )
    # Mimic agent_executions.output_json shape from run-1b2df4ffd82c
    stored = {"text": str({"code": code, "language": "typescript"})}
    r = review_execution_output(
        kind="agent",
        asset_id="frontend_engineer",
        asset_name="前端工程师",
        input_payload={"message": inp},
        output=stored,
        status="completed",
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert r.get("verdict") == "fail"
    codes = {i["code"] for i in (r.get("issues") or [])}
    assert "missing_auth_todo" in codes
    assert "dangling_local_import" in codes
    assert quality_review_blocks_success(r)

    # Seal / veto path must also unwrap — not only review_execution_output.
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        is_non_deliverable_coding_output,
    )

    sealed_codes = _coding_contract_fail_codes(
        inp,
        str(stored.get("text") or ""),
        stored,
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )
    assert "missing_auth_todo" in sealed_codes
    assert "dangling_local_import" in sealed_codes
    assert is_non_deliverable_coding_output(
        input_text=inp,
        output_text=str(stored.get("text") or ""),
        raw_out=stored,
        hints="code_generation autoreview",
        skill_trace=[
            {"name": "code_generation", "status": "success"},
            {"name": "autoreview", "status": "success"},
        ],
    )


def test_prd_and_architecture_prompts_skip_coding_file_gates():
    """PM/architect 交付/生成 + 上报/审批/派修 must not inherit TSX/## FILE gates."""
    from core.management.execution_examples import build_agent_task_examples
    from core.management.execution_quality_review import (
        _coding_contract_fail_codes,
        _input_asks_coding_delivery,
        _input_asks_multi_flow_frontend,
        is_non_deliverable_coding_output,
    )

    pm = build_agent_task_examples(
        display_name="产品经理",
        description="与用户对话收集需求，生成结构化PRD",
        skill_ids=["requirement_analysis"],
    )
    pm_inp = next(e["content"] for e in pm if "PRD" in e.get("title", ""))
    assert _input_asks_coding_delivery(pm_inp) is False
    assert _input_asks_multi_flow_frontend(pm_inp) is False

    prd_body = (
        "# 现场巡检报障 PRD 草稿\n"
        "## 背景与目标\n工人拍照上报，班组长审批后派修。照片不能传到公网。\n"
        "## FR-001 上报\n验收：提交后返回 ticket_id。\n"
        "## FR-002 审批\n验收：approved=true 后 status=approved。\n"
        "## FR-003 派修\n验收：dispatch 后有 repair_task_id。\n"
        "钉钉 API 文档未开放 / 集成方式待确认。\n"
        '{"functional_requirements":[{"name":"上报","acceptance_criteria":["ticket_id"]}],'
        '"constraints":{"security":["不上公网"]}}\n'
    )
    assert _coding_contract_fail_codes(pm_inp, prd_body, {"text": prd_body}) == []
    assert not is_non_deliverable_coding_output(
        input_text=pm_inp,
        output_text=prd_body,
        raw_out={"text": prd_body},
        hints="requirement_analysis",
        scope="full",
    )
    r = review_execution_output(
        kind="agent",
        asset_id="pm_agent",
        asset_name="产品经理",
        input_payload={"message": pm_inp},
        output={"text": prd_body},
        status="completed",
        hints="requirement_analysis",
    )
    codes = {i.get("code") for i in (r.get("issues") or [])}
    assert "frontend_flow_pages_incomplete" not in codes
    assert "thin_code_stub" not in codes
    assert "frontend_module_incomplete" not in codes

    arch = build_agent_task_examples(
        display_name="系统架构师",
        description="根据PRD完成系统架构设计",
        skill_ids=["architecture_design"],
    )
    arch_inp = next(e["content"] for e in arch if "架构草稿" in e.get("title", ""))
    assert _input_asks_coding_delivery(arch_inp) is False
    assert _input_asks_multi_flow_frontend(arch_inp) is False
    arch_body = (
        "## 上下文与假设\n照片不可上公网；钉钉 API 待确认。\n"
        "## 逻辑架构\n上报/审批/派修/看板四个组件。\n"
        "## api_contracts 草案\nPOST /api/v1/inspection/reports\n"
        '{"document_type":"architecture_design","tech_stack":["FastAPI","Vite"]}\n'
    )
    assert "frontend_flow_pages_incomplete" not in _coding_contract_fail_codes(
        arch_inp, arch_body, {"text": arch_body}
    )