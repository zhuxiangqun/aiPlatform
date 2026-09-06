"""Unit tests for PRD quality gate (media checklist + contradictions)."""

from __future__ import annotations

import pytest

from core.harness.execution.prd_gate_loader import clear_prd_gate_pack_cache
from core.harness.execution.prd_quality_gate import (
    assess_prd,
    apply_gate_to_prd,
    is_media_prd,
    normalize_constraints,
)


@pytest.fixture(autouse=True)
def _reset_prd_gate_packs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_PRD_GATES_DIR", str(tmp_path / "prd_gates"))
    clear_prd_gate_pack_cache()
    yield
    clear_prd_gate_pack_cache()


def _media_prd(**overrides):
    base = {
        "title": "智能视频内容理解工具",
        "description": "基于 URL 或本地文件导入视频，画面分析与问答",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频导入",
                "description": "URL 与本地上传",
                "acceptance_criteria": [
                    "支持 http/https URL 导入，拒绝内网 IP",
                    "支持 MP4/AVI/MOV/MKV，单文件 ≤2GB",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "description": "基于音轨特征，不转写",
                "acceptance_criteria": [
                    "基于音轨特征分析，不生成逐字转写文本",
                    "输出主题标签与整体情绪倾向",
                ],
            },
            {
                "id": "FR-006",
                "name": "数据安全",
                "description": "加密存储",
                "acceptance_criteria": [
                    "上传视频使用 AES-256 加密后存储",
                ],
            },
        ],
        "user_stories": [],
        "constraints": {},
        "open_questions": [],
    }
    base.update(overrides)
    return base


def test_is_media_prd():
    assert is_media_prd(_media_prd())
    assert not is_media_prd({
        "title": "订单系统",
        "functional_requirements": [
            {"id": "FR-1", "name": "下单", "acceptance_criteria": ["返回 order_id"]},
        ],
    })


def test_asr_topic_contradiction_blocks():
    report = assess_prd(_media_prd())
    codes = {i["code"] for i in report["issues"]}
    assert "asr_topic_contradiction" in codes
    assert report["ok"] is False


def test_decisions_alone_do_not_clear_semantic_asr_contradiction():
    """speech_pipeline=audio_features_only without rewriting semantic ACs must still fail."""
    prd = _media_prd(decisions={
        "url_source_scope": "direct_media_url",
        "speech_pipeline": "audio_features_only",
        "encryption_key_mgmt": "per-tenant KMS envelope",
        "analysis_sla": "P95 ≤ 1.5× video duration",
        "confidence_empty_policy": "empty_list",
    }, constraints={
        "platform": "Web",
        "performance": ["P95 ≤ 1.5× video duration"],
        "security": ["AES-256 with per-tenant KMS"],
    })
    prd["functional_requirements"].append({
        "id": "FR-002",
        "name": "画面分析",
        "acceptance_criteria": [
            "主体置信度 ≥0.7；未识别到主体时输出空列表",
        ],
    })
    report = assess_prd(prd)
    codes = {i["code"] for i in report["issues"] if i["severity"] == "error"}
    assert "asr_topic_contradiction" in codes
    assert report["ok"] is False


def test_acoustic_rewrite_clears_asr_contradiction():
    """Only removing semantic wording clears the check — not a disclaimer token alone."""
    prd = _media_prd(decisions={
        "url_source_scope": "direct_media_url",
        "speech_pipeline": "audio_features_only",
        "encryption_key_mgmt": "per-tenant KMS envelope",
        "analysis_sla": "P95 ≤ 1.5× video duration",
        "confidence_empty_policy": "empty_list",
    }, constraints={
        "platform": "Web",
        "performance": ["P95 ≤ 1.5× video duration"],
        "security": ["AES-256 with per-tenant KMS"],
    })
    # Rewrite FR-004 ACs to acoustic wording (no 主题/要点 left)
    for fr in prd["functional_requirements"]:
        if fr.get("id") == "FR-004":
            fr["acceptance_criteria"] = [
                "基于音轨特征分析，不生成逐字转写文本",
                "输出语音特征标签（语种/说话人数量/情绪倾向等声学粗标签，非转写语义）",
            ]
    prd["functional_requirements"].append({
        "id": "FR-002",
        "name": "画面分析",
        "acceptance_criteria": [
            "主体置信度 ≥0.7；未识别到主体时输出空列表",
        ],
    })
    report = assess_prd(prd)
    assert report["ok"] is True, report["issues"]
    assert report["scores"]["consistency"] >= 7.0
    assert report["scores"]["open_questions_closed"] >= 7.0


def test_disclaimer_plus_topic_label_still_blocks():
    """「声学特征」disclaimer must not green-pass leftover 主题标签."""
    prd = _media_prd()
    for fr in prd["functional_requirements"]:
        if fr.get("id") == "FR-004":
            fr["acceptance_criteria"] = [
                "基于音轨声学特征分析，不包含语音转写",
                "输出主题标签与整体情绪倾向",
            ]
    report = assess_prd(prd)
    codes = {i["code"] for i in report["issues"]}
    assert "asr_topic_contradiction" in codes
    assert report["ok"] is False


def test_disclaimer_plus_topic_structural_repair_allows_ready():
    """Disclaimer + leftover 主题: structural repair rewrites FR and may READY."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = _media_prd()
    for fr in prd["functional_requirements"]:
        if fr.get("id") == "FR-004":
            fr["acceptance_criteria"] = [
                "基于音轨声学特征分析，不包含语音转写",
                "输出主题标签与整体情绪倾向",
            ]
    final, report = factory_finalize_prd(prd)
    blob = " ".join(
        " ".join(fr.get("acceptance_criteria") or [])
        for fr in (final.get("functional_requirements") or [])
        if isinstance(fr, dict)
    )
    assert "主题标签" not in blob or "禁止主题标签" in blob
    assert "声学粗标签" in blob or "非转写语义" in blob
    assert report["ok"] is True, report["issues"]
    assert not report.get("wash_blocked")
    assert "asr_topic_contradiction" in (
        (final.get("_prd_gate") or {}).get("structural_cleared") or []
    )


def test_open_questions_block_confirm():
    prd = {
        "title": "简单工具",
        "functional_requirements": [
            {"id": "FR-1", "name": "A", "acceptance_criteria": ["x"]},
        ],
        "constraints": {"performance": ["P95<1s"], "security": ["HTTPS"]},
        "open_questions": ["还要不要支持移动端？"],
    }
    report = assess_prd(prd)
    assert report["ok"] is False
    assert any(i["code"] == "open_questions_present" for i in report["issues"])


def test_apply_gate_force():
    prd = _media_prd()
    # Without enrich, still blocked
    with pytest.raises(ValueError, match="质量门禁"):
        apply_gate_to_prd(prd, force=False, enrich=False)
    # Structural repair closes contradiction → confirmable
    normalized, report = apply_gate_to_prd(prd, force=False, enrich=True)
    assert report["ok"] is True, report["issues"]
    assert not report.get("wash_blocked")
    assert normalized["decisions"]["speech_pipeline"] == "audio_features_only"
    # force still works on unrelated failures
    normalized2, report2 = apply_gate_to_prd(prd, force=True, enrich=True)
    assert normalized2["decisions"]["speech_pipeline"] == "audio_features_only"


def test_factory_finalize_closes_videosense_style_prd():
    """VideoSense-style contradiction: scrub may rewrite text but must NOT green-pass."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = {
        "title": "智能视频内容理解工具 (VideoSense)",
        "description": "基于URL导入或本地上传的视频，提供画面分析、字幕提取、语音特征分析",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频导入",
                "acceptance_criteria": [
                    "用户可通过粘贴URL导入视频，系统校验协议为http/https且拒绝内网IP/本地协议地址",
                    "支持MP4/AVI/MOV/MKV，单文件≤2GB",
                ],
            },
            {
                "id": "FR-002",
                "name": "画面分析",
                "acceptance_criteria": [
                    "识别画面主体，每个主体标注置信度且置信度≥0.7",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "acceptance_criteria": [
                    "基于音轨特征分析，不生成逐字转写文本",
                    "输出主题标签与整体情绪倾向",
                ],
            },
            {
                "id": "FR-006",
                "name": "数据安全",
                "acceptance_criteria": [
                    "上传的视频文件使用AES-256加密后存储",
                    "删除操作需二次确认，删除后不可恢复",
                ],
            },
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    assert raw["ok"] is False
    final, report = factory_finalize_prd(prd)
    assert report["ok"] is True, report["issues"]
    assert not report.get("wash_blocked")
    assert final["decisions"]["url_source_scope"] == "direct_media_url"
    assert final["decisions"]["speech_pipeline"] == "audio_features_only"
    assert final["decisions"]["encryption_key_mgmt"]
    assert final["decisions"]["confidence_empty_policy"] == "empty_list"
    assert final["constraints"]["performance"]
    assert final["constraints"]["security"]
    assert report.get("repairs")
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in fr.get("acceptance_criteria") or []
    )
    assert "声学" in blob or "语音特征" in blob
    assert "主题标签" not in blob or "声学" in blob

def test_factory_finalize_rewrites_user_videosense_contradiction():
    """User-facing VideoSense draft with 语义分析/无上限/硬字幕 must be rewritten."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd, render_prd_markdown

    prd = {
        "title": "智能视频内容理解工具 (VideoSense)",
        "description": "画面分析、字幕提取（依赖平台已有字幕）与语音内容分析（不转写）",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入与下载",
                "acceptance_criteria": [
                    "支持上传 MP4/MOV/AVI/MKV 格式视频文件，单文件大小无上限。",
                    "输入 URL 时，仅解析指向视频文件的直链；禁止访问内网/私有 IP 地址及 file:// 协议（SSRF 防护）。",
                ],
            },
            {
                "id": "FR-003",
                "name": "字幕提取",
                "description": "提取视频中已存在的字幕轨道（如硬字幕或软字幕）",
                "acceptance_criteria": [
                    "若视频包含软字幕轨道，能提取并输出字幕文本及时间码。",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "description": "对语音轨道内容（非转写）进行语义分析",
                "acceptance_criteria": [
                    "基于已有语音内容（非转写）进行语义分析。",
                    "输出主题标签、情感倾向或关键话题摘要。",
                ],
            },
            {
                "id": "FR-005",
                "name": "报告",
                "acceptance_criteria": ["整合画面、字幕、语音结果生成 JSON 报告"],
            },
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "asr_topic_contradiction" in codes or "speech_summary_without_transcript" in codes
    assert "upload_size_unlimited" in codes
    assert "hard_soft_subtitle_mismatch" in codes

    final, report = factory_finalize_prd(prd)
    assert "asr_topic_contradiction" not in (report.get("wash_blocked") or [])
    assert "speech_summary_without_transcript" not in (report.get("wash_blocked") or [])
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in (fr.get("acceptance_criteria") or [])
    )
    assert "无上限" not in blob
    assert "2GB" in blob or "2GiB" in final["decisions"].get("upload_max_bytes", "")
    assert "声学" in blob or "语音特征" in blob
    assert "语义分析" not in blob or "声学" in blob
    assert "软字幕" in blob or final["decisions"].get("subtitle_scope") == "soft_track_only"

    md = render_prd_markdown(final)
    assert "## 项目名称：" in md
    # Wash-blocked: must NOT emit PRD_READY via ok path — marker only if no open Qs;
    # gate still stores draft but builder strips READY when ok=False.
    assert "决策" in md
    assert "speech_pipeline" in md
    # Chat must not still advertise unlimited upload
    assert "无上限" not in md

def test_factory_finalize_mvp_speech_rate_and_ssrf():
    """Simplified MVP PRD with 字/分钟 + 不冲突 + 相对报告耗时 must auto-repair."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = {
        "title": "智能视频内容理解工具",
        "description": "输入视频直链或本地文件，提取画面标签、字幕与语音特征（不转写）",
        "functional_requirements": [
            {
                "id": "FR-01",
                "name": "视频接入与下载",
                "acceptance_criteria": [
                    "输入直链媒体 URL（mp4/mov/webm）可成功下载并进入分析流程",
                    "上传本地视频文件（≤2GB）可成功入库",
                ],
            },
            {
                "id": "FR-02",
                "name": "视频画面分析",
                "acceptance_criteria": [
                    '对每个视频输出 ≥3 个画面标签（如"室内会议"）',
                    "画面标签粒度与语音分析结果不冲突（见决策节一致性约束）",
                ],
            },
            {
                "id": "FR-03",
                "name": "字幕提取",
                "acceptance_criteria": [
                    "无字幕轨道时返回空字幕列表并标注无可用字幕",
                ],
            },
            {
                "id": "FR-04",
                "name": "语音特征分析（不转写）",
                "acceptance_criteria": [
                    "输出平均语速（字/分钟，基于已有字幕或语音能量估算）",
                    "输出静音段占比（%）",
                    "输出检测到的说话人数量估计值",
                ],
            },
            {
                "id": "FR-05",
                "name": "内容理解报告生成",
                "acceptance_criteria": [
                    "报告包含画面标签、字幕摘要、语音特征三个章节",
                    "报告生成耗时不超过分析总耗时的 10%",
                ],
            },
        ],
        "constraints": {},
        "decisions": {
            "speech_pipeline": "audio_features_only",
            "url_source_scope": "direct_media_url",
            "encryption_key_mgmt": "N/A",
        },
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "speech_rate_chars_without_transcript" in codes
    assert "ssrf_guard_missing" in codes
    assert "modality_no_conflict_unverifiable" in codes
    assert "relative_report_latency_untestable" in codes
    assert raw["ok"] is False

    final, report = factory_finalize_prd(prd)
    assert report["ok"] is True, report["issues"]
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in fr.get("acceptance_criteria") or []
    )
    assert "音节" in blob or "双路径" in blob or "若存在字幕" in blob
    assert "SSRF" in blob or "内网" in blob
    assert "不冲突" not in blob or "如实展示" in blob
    assert "10%" not in blob
    assert final["decisions"].get("vision_tag_granularity") == "global_coarse"
    assert any("auto:rewrite_speech_rate_dual" in r or "ssrf" in r for r in (report.get("repairs") or []))


def test_factory_finalize_rewrites_speech_summary_without_asr():
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = {
        "title": "视频工具",
        "description": "视频语音分析",
        "functional_requirements": [
            {
                "id": "FR-04",
                "name": "语音分析（不转写）",
                "acceptance_criteria": ["不生成逐字转写文本", "输出语种与说话人数量"],
            },
            {
                "id": "FR-05",
                "name": "报告",
                "acceptance_criteria": ["报告包含语音摘要章节"],
            },
        ],
        "constraints": {"platform": "Web", "performance": ["P95 ok"], "security": ["HTTPS"]},
        "decisions": {"speech_pipeline": "audio_features_only", "url_source_scope": "direct_media_url"},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "speech_summary_without_transcript" in codes

    final, report = factory_finalize_prd(prd)
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in fr.get("acceptance_criteria") or []
    )
    assert "语音摘要" not in blob or "特征" in blob
    assert "语音特征" in blob or "声学" in blob
    assert any("rewrite_speech_summary" in r or "structural:" in r for r in (report.get("repairs") or []))
    assert report["ok"] is True, report["issues"]
    assert "speech_summary_without_transcript" not in (report.get("wash_blocked") or [])

def test_normalize_constraints_from_scope():
    prd = {
        "title": "X",
        "scope": "- 平台: Web\n- 性能: P95 < 2s\n- 安全: HTTPS\n",
        "functional_requirements": [],
    }
    out = normalize_constraints(prd)
    assert out["constraints"]["platform"] == "Web"
    assert "P95 < 2s" in out["constraints"]["performance"]
    assert "HTTPS" in out["constraints"]["security"]


def test_factory_finalize_no_size_cap_and_no_asr_phrase():
    """「无大小上限」+「不进行语音转写」must rewrite size and infer audio_features_only."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd, render_prd_markdown

    prd = {
        "title": "智能视频内容理解工具",
        "description": "画面分析、字幕提取与语音分析",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入与下载",
                "acceptance_criteria": [
                    "支持上传常见视频格式（MP4/MOV/AVI/MKV），单文件无大小上限",
                    "仅解析直链视频文件；禁止访问内网地址与 file:// 协议（SSRF 防护）",
                ],
            },
            {
                "id": "FR-003",
                "name": "字幕提取",
                "acceptance_criteria": [
                    "依赖平台已有字幕轨道，不进行语音转写",
                    "无字幕轨道时返回 NO_SUBTITLE_TRACK",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音分析",
                "acceptance_criteria": [
                    "仅分析视频中已有的语音内容，不执行语音转写",
                    "语音分析输出包括语速、情感倾向、说话人数量等特征",
                ],
            },
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "upload_size_unlimited" in codes

    final, report = factory_finalize_prd(prd)
    assert report["ok"] is True, report["issues"]
    assert final["decisions"]["speech_pipeline"] == "audio_features_only"
    assert final["decisions"].get("upload_max_bytes") == "2GiB"
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in fr.get("acceptance_criteria") or []
    )
    assert "无大小上限" not in blob and "无上限" not in blob
    assert "2GB" in blob
    md = render_prd_markdown(final)
    assert "无大小上限" not in md
    assert "speech_pipeline: audio_features_only" in md


def test_factory_finalize_factory_chat_videosense_prd():
    """App-factory draft: webpage vs direct URL, download-fail, no-ASR keywords."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd, render_prd_markdown

    prd = {
        "title": "智能视频内容理解工具",
        "description": "智能视频内容理解工具，支持通过视频链接或本地上传获取视频，并提供画面分析、字幕提取与语音内容分析能力。",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入与下载",
                "description": "支持用户通过本地上传视频文件或提供视频网页链接两种方式输入视频，系统负责获取视频文件并存储，供后续分析使用。",
                "priority": "high",
                "acceptance_criteria": [
                    "支持上传 MP4/MOV/AVI/MKV 格式，单文件大小 ≤2GB；超过 2GB 时拒绝上传并提示「文件过大，请上传 ≤2GB 的视频」",
                    "输入网页链接时，仅解析直链视频文件（如 .mp4/.mov/.avi/.mkv 结尾的 URL）；禁止访问内网地址（如 127.0.0.1、10.x.x.x 等）与 `file://` 协议（SSRF 防护）",
                    "下载失败时返回明确错误码（如 `DOWNLOAD_FAILED`），且不阻塞其他任务或后续分析流程",
                    "上传或下载成功后，返回唯一的视频 ID（如 UUID），用于后续分析任务关联",
                ],
            },
            {
                "id": "FR-002",
                "name": "视频画面分析",
                "description": "对视频进行抽帧，并基于画面内容生成结构化的画面理解结果。",
                "priority": "high",
                "acceptance_criteria": [
                    "系统自动从视频中抽取关键帧（默认每 5 秒一帧，或按场景变化自适应抽帧），并记录每帧的时间戳",
                    "对每个关键帧生成画面描述，包含主要物体、场景类型、人物活动等要素",
                    "输出结构化结果：每帧包含时间戳、画面描述文本、物体标签列表（如 ['人','汽车','会议室']）",
                    "当视频无有效画面（如纯黑帧或纯色帧）时，输出明确提示「该帧无有效画面内容」",
                    "分析结果按时间顺序组织，支持按时间戳定位到具体帧",
                ],
            },
            {
                "id": "FR-003",
                "name": "字幕提取",
                "description": "从视频中提取字幕内容。若视频内嵌字幕流，则直接提取；若视频无内嵌字幕，则提示用户补充字幕文件（如 .srt/.vtt）。",
                "priority": "standard",
                "acceptance_criteria": [
                    "若视频包含内嵌字幕流，系统直接提取字幕文本，并按时间轴输出（起始时间、结束时间、字幕文本）",
                    "若视频无内嵌字幕，系统提示「该视频无内嵌字幕，请上传 .srt 或 .vtt 字幕文件」，并允许用户上传字幕文件",
                    "用户上传字幕文件后，系统解析并输出带时间轴的字幕内容",
                    "提取或解析的字幕内容支持按时间段检索",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "description": "对视频中已有的语音轨道内容进行分析，提取说话人、语速、情绪、关键词等信息，但不进行语音转写。",
                "priority": "standard",
                "acceptance_criteria": [
                    "系统检测视频是否包含语音轨道；若无语音轨道，输出提示「该视频无语音内容」",
                    "当存在语音轨道时，分析并输出语音特征：语速（字/分钟）、平均音调、情绪倾向（如积极/中性/消极）",
                    "提取语音中的关键词或主题标签（如 ['产品介绍','价格讨论']），不输出逐字转写文本",
                    "分析结果按时间段分段输出（如每 30 秒一段），便于定位",
                ],
            },
        ],
        "user_stories": [
            {
                "id": "US-001",
                "story": "作为内容审核员，我想要上传本地视频或粘贴视频链接，以便系统自动获取视频文件进行分析",
                "priority": "high",
                "related_fr": ["FR-001"],
            },
            {
                "id": "US-004",
                "story": "作为内容审核员，我想要分析视频语音的特征与关键词，以便判断视频的语气与主题倾向",
                "priority": "standard",
                "related_fr": ["FR-004"],
            },
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "asr_topic_contradiction" in codes
    assert "webpage_vs_direct_url_mismatch" in codes
    assert "download_fail_must_not_continue_analysis" in codes

    final, report = factory_finalize_prd(prd)
    assert "asr_topic_contradiction" not in (report.get("wash_blocked") or [])
    assert final["decisions"]["speech_pipeline"] == "audio_features_only"
    assert final["decisions"].get("subtitle_scope") == "soft_track_only"

    fr1 = next(fr for fr in final["functional_requirements"] if fr["id"] == "FR-001")
    assert "网页链接" not in str(fr1.get("description"))
    acs = " ".join(str(a) for a in fr1["acceptance_criteria"])
    assert "不进入本视频" in acs or "仅终止本视频" in acs
    assert "后续分析流程" not in acs

    fr4 = next(fr for fr in final["functional_requirements"] if fr["id"] == "FR-004")
    assert "关键词" not in str(fr4.get("description"))
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in fr.get("acceptance_criteria") or []
    )
    assert "主题标签" not in blob or "声学" in blob
    assert "音节密度" in blob or "字/分钟" in blob

    stories = " ".join(str(us.get("story") or us.get("description") or "") for us in final["user_stories"])
    assert "关键词" not in stories
    assert "主题倾向" not in stories

    md = render_prd_markdown(final)
    assert "网页链接" not in md
    assert "speech_pipeline: audio_features_only" in md


def test_no_asr_contain_phrasing_and_reject_webpage_not_mismatch():
    """「不包含语音转写」+ 主题/要点 must error; 「拒绝网页链接」must not false-positive."""
    from core.harness.execution.prd_quality_gate import assess_prd, factory_finalize_prd

    prd = {
        "title": "智能视频内容理解工具",
        "description": "基于视频链接或本地上传视频，提供画面分析、字幕提取与语音内容分析能力，不包含语音转写。",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入与下载",
                "acceptance_criteria": [
                    "支持上传 MP4/MOV/AVI/MKV，单文件 ≤2GB；超过时拒绝并提示「文件过大，请上传 ≤2GB 的视频」",
                    "输入视频 URL 时，仅接受以 .mp4/.mov/.avi/.mkv 结尾的直链媒体文件；拒绝解析网页链接或非直链页面",
                    "拒绝访问内网/私有 IP 及 file://（SSRF 防护）",
                    "下载失败返回 DOWNLOAD_FAILED，仅终止当前任务，不阻塞队列中其他任务",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "description": "提取主题、要点、情感等信息，不进行语音到文字的转写。",
                "acceptance_criteria": [
                    "输出主题标签、关键要点、情感倾向等结构化信息",
                    "无语音轨道时提示「该视频无可用语音内容」",
                ],
            },
        ],
        "user_stories": [
            {
                "id": "US-004",
                "story": "作为市场分析师，我想要分析视频语音中传达的主题和情感，以便评估传播效果。",
                "related_fr": ["FR-004"],
            }
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "asr_topic_contradiction" in codes or "speech_summary_without_transcript" in codes
    assert "webpage_vs_direct_url_mismatch" not in codes

    final, report = factory_finalize_prd(prd)
    assert "asr_topic_contradiction" not in (report.get("wash_blocked") or [])
    assert "speech_summary_without_transcript" not in (report.get("wash_blocked") or [])
    assert final["decisions"].get("speech_pipeline") == "audio_features_only"
    blob = " ".join(
        str(a)
        for fr in final["functional_requirements"]
        for a in (fr.get("acceptance_criteria") or [])
    )
    assert "主题标签" not in blob or "禁止主题标签" in blob or "声学" in blob
    stories = " ".join(str(us.get("story") or "") for us in final.get("user_stories") or [])
    assert "主题和情感" not in stories
    assert "主题与情感" not in stories


def test_reject_or_webpage_prompt_not_url_mismatch():
    """「输入其他格式或网页链接时提示仅支持直链」is reject-path, not dual scope."""
    from core.harness.execution.prd_quality_gate import assess_prd, factory_finalize_prd

    prd = {
        "title": "智能视频内容理解工具",
        "description": "直链或本地上传，画面/字幕/语音分析，不进行语音转写",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入与下载",
                "acceptance_criteria": [
                    "支持上传 MP4，单文件 ≤2GB",
                    "支持输入以 .mp4 结尾的直链视频 URL；输入其他格式或网页链接时提示「仅支持直链视频文件」",
                    "禁止访问内网及 file://（SSRF 防护）",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音内容分析",
                "description": "语义分析提取主题要点，不进行语音转写",
                "acceptance_criteria": [
                    "输出语音内容摘要（主题、核心要点）",
                    "输出情感倾向",
                ],
            },
        ],
        "user_stories": [
            {
                "id": "US-004",
                "story": "作为审核员，我想要分析语音内容的主题与情感，以便判断信息",
                "related_fr": ["FR-004"],
            }
        ],
        "constraints": {},
        "decisions": {},
        "open_questions": [],
    }
    raw = assess_prd(prd)
    codes = {i["code"] for i in raw["issues"] if i["severity"] == "error"}
    assert "webpage_vs_direct_url_mismatch" not in codes
    assert "asr_topic_contradiction" in codes or "speech_summary_without_transcript" in codes
    final, report = factory_finalize_prd(prd)
    assert "asr_topic_contradiction" not in (report.get("wash_blocked") or [])
    assert "speech_summary_without_transcript" not in (report.get("wash_blocked") or [])
    assert final["decisions"]["speech_pipeline"] == "audio_features_only"
    stories = " ".join(str(us.get("story") or "") for us in final["user_stories"])
    assert "主题与情感" not in stories


def test_format_pm_gate_guidance_includes_media_hints():
    """Video requirement text must inject media pm_hints for PM generation-time."""
    from core.harness.execution.prd_quality_gate import format_pm_gate_guidance, matched_packs_for_text

    text = "智能视频内容理解工具，本地上传或视频链接，画面分析、字幕提取、语音分析不转写"
    packs = matched_packs_for_text(text)
    assert any(p.get("domain_id") == "media" for p in packs)
    assert any(p.get("domain_id") == "_common" for p in packs)

    guidance = format_pm_gate_guidance(text)
    assert "PRD 域质量约束" in guidance
    assert "### media" in guidance
    assert "BAD" in guidance or "禁止写" in guidance
    assert "GOOD" in guidance or "语种估计" in guidance
    assert "洗绿" in guidance or "首稿" in guidance
    assert "speech_pipeline" in guidance


def test_format_pm_gate_guidance_common_only_without_media_triggers():
    from core.harness.execution.prd_quality_gate import format_pm_gate_guidance

    guidance = format_pm_gate_guidance("做一个待办清单 Web 应用，支持登录")
    assert "PRD 域质量约束" in guidance
    assert "### _common" in guidance
    assert "### media" not in guidance
    assert "SSRF" in guidance or "constraints" in guidance


def test_forbid_topic_wording_does_not_false_positive():
    """「禁止主题/不输出主题」must not trip asr_topic_contradiction."""
    prd = {
        "title": "智能视频内容理解工具",
        "description": "直链或本地上传；画面/软字幕/语音声学特征；不包含语音转写",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入",
                "acceptance_criteria": [
                    "支持上传 MP4/MOV，单文件 ≤2GB",
                    "仅接受直链媒体 URL；拒绝内网 IP 与 file://（SSRF 防护）",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音声学特征分析",
                "description": "基于音轨声学特征；不进行语音转写；禁止主题与语义摘要",
                "acceptance_criteria": [
                    "检测有无音轨；无音轨时提示「该视频无可用音轨」",
                    "输出声学粗标签（语种估计/说话人数量估计/情绪倾向，非转写语义）；不输出主题、要点或语音内容摘要",
                ],
            },
        ],
        "user_stories": [
            {
                "id": "US-004",
                "story": "作为分析师，我想查看语种估计与情绪倾向（声学），以便粗判传播氛围",
                "related_fr": ["FR-004"],
            }
        ],
        "constraints": {
            "platform": "Web",
            "performance": ["P95 ≤ 1.5× video duration"],
            "security": ["HTTPS + SSRF reject private IPs"],
        },
        "decisions": {
            "url_source_scope": "direct_media_url",
            "speech_pipeline": "audio_features_only",
            "subtitle_scope": "soft_track_only",
            "analysis_sla": "P95 ≤ 1.5× video duration",
            "encryption_key_mgmt": "N/A",
        },
        "open_questions": [],
    }
    report = assess_prd(prd)
    codes = {i["code"] for i in report["issues"] if i["severity"] == "error"}
    assert "asr_topic_contradiction" not in codes, report["issues"]
    assert report["ok"] is True, report["issues"]


def test_acoustic_only_first_draft_passes_without_wash_block():
    """Correct no-ASR acoustic-only first draft must pass finalize (no wash_blocked)."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = {
        "title": "智能视频内容理解工具",
        "description": "直链或本地上传；画面/软字幕/语音声学特征；不包含语音转写",
        "functional_requirements": [
            {
                "id": "FR-001",
                "name": "视频输入",
                "acceptance_criteria": [
                    "支持上传 MP4/MOV，单文件 ≤2GB",
                    "仅接受直链媒体 URL；拒绝内网 IP 与 file://（SSRF 防护）",
                ],
            },
            {
                "id": "FR-004",
                "name": "语音声学特征分析",
                "description": "基于音轨声学特征，不进行语音转写",
                "acceptance_criteria": [
                    "检测有无音轨；无音轨时提示「该视频无可用语音内容」",
                    "输出语音特征标签（语种估计/说话人数量估计/情绪倾向等声学粗标签，非转写语义）",
                ],
            },
        ],
        "user_stories": [
            {
                "id": "US-004",
                "story": "作为分析师，我想查看语种估计与情绪倾向（声学），以便粗判传播氛围",
                "related_fr": ["FR-004"],
            }
        ],
        "constraints": {
            "platform": "Web",
            "performance": ["P95 ≤ 1.5× video duration"],
            "security": ["HTTPS + SSRF reject private IPs"],
        },
        "decisions": {
            "url_source_scope": "direct_media_url",
            "speech_pipeline": "audio_features_only",
            "subtitle_scope": "soft_track_only",
            "analysis_sla": "P95 ≤ 1.5× video duration",
            "encryption_key_mgmt": "N/A",
        },
        "open_questions": [],
    }
    raw = assess_prd(prd)
    assert raw["ok"] is True, raw["issues"]
    final, report = factory_finalize_prd(prd)
    assert report["ok"] is True, report["issues"]
    assert not report.get("wash_blocked")
    assert final["decisions"]["speech_pipeline"] == "audio_features_only"


def test_structural_repair_clears_wash_block_on_contradiction():
    """asr_topic on raw → structural repair → finalize READY (not scrub-only wash)."""
    from core.harness.execution.prd_quality_gate import factory_finalize_prd

    prd = _media_prd()
    raw = assess_prd(prd)
    assert "asr_topic_contradiction" in {i["code"] for i in raw["issues"]}
    final, report = factory_finalize_prd(prd)
    assert report["ok"] is True, report["issues"]
    assert not report.get("wash_blocked")
    assert final["decisions"].get("speech_pipeline") == "audio_features_only"
    assert "asr_topic_contradiction" in (
        (final.get("_prd_gate") or {}).get("structural_cleared") or []
    )
    fr4 = next(fr for fr in final["functional_requirements"] if fr.get("id") == "FR-004")
    assert "声学" in str(fr4.get("name", "")) + str(fr4.get("acceptance_criteria"))


def test_scrub_alone_without_structural_still_wash_blocks(monkeypatch):
    """If structural_repairs do not run, scrub must not clear wash_blocked."""
    from core.harness.execution import prd_quality_gate as g

    def _no_structural(prd, codes):
        return prd, [], []

    monkeypatch.setattr(g, "_apply_structural_repairs", _no_structural)
    prd = _media_prd()
    final, report = g.factory_finalize_prd(prd)
    assert report["ok"] is False
    assert "asr_topic_contradiction" in (report.get("wash_blocked") or [])
    assert "洗绿不可放行" in " ".join(i.get("message", "") for i in report["issues"])
