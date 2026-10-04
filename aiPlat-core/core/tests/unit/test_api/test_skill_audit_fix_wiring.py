"""One-click skill fix must link propose ops to audit issues."""

from __future__ import annotations

from pathlib import Path

from core.management.asset_audit import index_skill_lint_fixes, summarize_audit_issues
from core.management.skill_linter import lint_skill, propose_skill_fixes


def test_apply_lint_fix_allows_full_schema_upsert():
    src = (Path(__file__).resolve().parents[3] / "api/routers/workspace_skills.py").read_text(
        encoding="utf-8"
    )
    assert '("input_schema",)' in src
    assert '("output_schema",)' in src
    assert "in_replace" in src
    eng = (Path(__file__).resolve().parents[3] / "api/routers/engine_skills.py").read_text(
        encoding="utf-8"
    )
    assert '("input_schema",)' in eng
    assert '("execution_type",)' in eng


def test_handler_present_aligns_execution_type(tmp_path):
    (tmp_path / "handler.py").write_text("# handler\n", encoding="utf-8")
    skill = {
        "id": "upload_video",
        "name": "upload_video",
        "description": "上传视频",
        "execution_type": "prompt",
        "metadata": {"scope": "workspace", "skill_dir": str(tmp_path)},
        "input_schema": {"file": {"type": "file"}},
        "output_schema": {"play_url": {"type": "string"}},
    }
    lint = lint_skill(skill)
    codes = {e.get("code") for e in (lint.get("errors") or [])} | {
        w.get("code") for w in (lint.get("warnings") or [])
    }
    assert "exec_type_dir_mismatch" in codes
    fx = propose_skill_fixes(skill=skill, lint=lint)
    idx = index_skill_lint_fixes(fx.get("fixes") or [])
    assert idx["exec_type_dir_mismatch"]["fix_id"] == "fix_align_execution_type"
    op = (idx["exec_type_dir_mismatch"].get("patch") or {}).get("ops") or []
    assert any(x.get("path") == ["execution_type"] and x.get("value") == "handler" for x in op)


def test_workspace_routing_disambiguation_is_auto():
    skill = {
        "id": "s1",
        "name": "s1",
        "description": "上传视频文件",
        "metadata": {
            "scope": "workspace",
            "_observability": {"wrong_top1": 9, "n": 10},
            "trigger_conditions": ["上传", "视频", "文件", "链接", "进度", "格式"],
            "keywords": {"objects": ["视频"], "actions": ["上传"]},
        },
        "input_schema": {"file": {"type": "file"}},
        "output_schema": {"play_url": {"type": "string"}},
    }
    lint = lint_skill(skill)
    codes = {w.get("code") for w in (lint.get("warnings") or [])} | {
        e.get("code") for e in (lint.get("errors") or [])
    }
    if "routing_needs_disambiguation" not in codes:
        lint = {
            "warnings": [{"code": "routing_needs_disambiguation", "message": "x"}],
            "errors": [],
        }
    fx = propose_skill_fixes(skill=skill, lint=lint)
    hit = next((f for f in (fx.get("fixes") or []) if f.get("fix_id") == "fix_routing_disambiguate"), None)
    assert hit is not None
    assert hit.get("auto_applicable") is True


def test_index_skill_lint_fixes_links_non_auto_with_ops():
    fixes = [
        {
            "fix_id": "fix_generate_triggers_keywords",
            "issue_code": "triggers_too_few",
            "covers_issue_codes": ["triggers_too_few", "missing_negative_triggers"],
            "auto_applicable": True,
            "patch": {
                "format": "frontmatter_merge",
                "ops": [
                    {"op": "upsert", "path": ["trigger_conditions"], "value": ["a", "b", "c", "d", "e", "f"]},
                    {"op": "upsert", "path": ["negative_triggers"], "value": ["不做OCR"]},
                ],
            },
        }
    ]
    idx = index_skill_lint_fixes(fixes)
    assert "triggers_too_few" in idx
    assert "missing_negative_triggers" in idx
    assert idx["triggers_too_few"]["fix_id"] == "fix_generate_triggers_keywords"


def test_workspace_propose_marks_trigger_fix_auto():
    skill = {
        "id": "tech_like",
        "name": "tech_like",
        "description": "做技术选型",
        "category": "analysis",
        "metadata": {
            "scope": "workspace",
            "trigger_conditions": ["选型"],
            "keywords": {"objects": ["技术", "方案"], "actions": ["选型", "对比"]},
        },
        "input_schema": {"q": {"type": "string"}},
        "output_schema": {"markdown": {"type": "string", "required": True}},
    }
    lint = lint_skill(skill)
    fx = propose_skill_fixes(skill=skill, lint=lint)
    fixes = fx.get("fixes") or []
    gen = next((f for f in fixes if f.get("fix_id") == "fix_generate_triggers_keywords"), None)
    assert gen is not None, f"expected generate fix, got {[f.get('fix_id') for f in fixes]}"
    assert gen.get("auto_applicable") is True
    assert "missing_negative_triggers" in (gen.get("covers_issue_codes") or [])
    assert "generic_description" not in (gen.get("covers_issue_codes") or [])
    idx = index_skill_lint_fixes(fixes)
    assert idx.get("missing_negative_triggers")
    assert idx.get("triggers_too_few")
    # generic_description should map to rewrite, not generate
    assert (idx.get("generic_description") or {}).get("fix_id") in (
        None,
        "fix_rewrite_description_contract",
    ) or "generic_description" not in {
        w.get("code") for w in (lint.get("warnings") or [])
    }


def test_promote_legacy_io_lists_to_schema_is_auto_applicable():
    skill = {
        "id": "upload_video",
        "name": "upload_video",
        "description": "上传视频到对象存储并返回播放地址",
        "category": "general",
        "metadata": {"scope": "workspace"},
        "input": [
            {"name": "file", "type": "file", "required": True, "description": "视频文件"},
        ],
        "output": [
            {"name": "play_url", "type": "string", "required": True},
        ],
        "input_schema": {},
        "output_schema": {},
    }
    lint = lint_skill(skill)
    codes = {w.get("code") for w in (lint.get("warnings") or [])}
    assert "missing_input_schema" in codes
    assert "missing_output_schema" in codes
    fx = propose_skill_fixes(skill=skill, lint=lint)
    idx = index_skill_lint_fixes(fx.get("fixes") or [])
    assert idx["missing_input_schema"]["fix_id"] == "fix_promote_input_schema"
    assert idx["missing_output_schema"]["fix_id"] == "fix_promote_output_schema"
    assert idx["missing_input_schema"].get("auto_applicable") is True


def test_requirement_sop_fills_schema_without_io_lists(tmp_path):
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: upload_video\ninput_schema: {}\noutput_schema: {}\n---\n\n"
        "# 视频文件上传\n\n"
        "## 功能\n接收用户上传的视频文件，存储并生成可访问的播放链接。\n\n"
        "## 限制\n- 文件大小: 不超过2GB\n- 上传进度: 每500ms刷新一次\n",
        encoding="utf-8",
    )
    skill = {
        "id": "upload_video",
        "name": "upload_video",
        "description": "接收用户上传的视频文件并返回播放链接",
        "metadata": {"scope": "workspace", "filesystem": {"skill_md": str(md)}},
        "input_schema": {},
        "output_schema": {},
    }
    lint = lint_skill(skill)
    fx = propose_skill_fixes(skill=skill, lint=lint)
    idx = index_skill_lint_fixes(fx.get("fixes") or [])
    inn_ops = (idx["missing_input_schema"].get("patch") or {}).get("ops") or []
    out_ops = (idx["missing_output_schema"].get("patch") or {}).get("ops") or []
    in_val = next((op.get("value") for op in inn_ops if op.get("path") == ["input_schema"]), {})
    out_val = next((op.get("value") for op in out_ops if op.get("path") == ["output_schema"]), {})
    assert "file" in in_val
    assert "file_size" in in_val
    assert "play_url" in out_val
    assert "progress" in out_val
    assert "prompt" not in in_val
    assert "result" not in out_val


def test_empty_schema_without_io_list_has_no_invented_fix():
    skill = {
        "id": "blank_io",
        "name": "blank_io",
        "description": "x",
        "metadata": {"scope": "workspace"},
        "input_schema": {},
        "output_schema": {},
    }
    lint = lint_skill(skill)
    fx = propose_skill_fixes(skill=skill, lint=lint)
    ids = {f.get("fix_id") for f in (fx.get("fixes") or [])}
    assert "fix_promote_input_schema" not in ids
    assert "fix_promote_output_schema" not in ids


def test_sop_execution_flow_heading_is_enough(tmp_path):
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: upload_video\n---\n\n# t\n\n## 执行流程\n1. 上传\n",
        encoding="utf-8",
    )
    skill = {
        "id": "upload_video",
        "name": "upload_video",
        "description": "上传视频",
        "metadata": {"filesystem": {"skill_md": str(md)}},
        "input_schema": {"file": {"type": "file"}},
        "output_schema": {"play_url": {"type": "string"}},
    }
    lint = lint_skill(skill)
    codes = {w.get("code") for w in (lint.get("warnings") or [])}
    assert "sop_missing_flow" not in codes


def test_sop_missing_flow_gets_append_fix(tmp_path):
    md = tmp_path / "SKILL.md"
    md.write_text("---\nname: x\n---\n\n只有功能说明，没有流程。\n", encoding="utf-8")
    skill = {
        "id": "x",
        "name": "x",
        "description": "说明文字足够长",
        "metadata": {"scope": "workspace", "filesystem": {"skill_md": str(md)}},
        "input_schema": {"a": {"type": "string"}},
        "output_schema": {"b": {"type": "string"}},
    }
    lint = lint_skill(skill)
    codes = {w.get("code") for w in (lint.get("warnings") or [])}
    assert "sop_missing_flow" in codes
    fx = propose_skill_fixes(skill=skill, lint=lint)
    idx = index_skill_lint_fixes(fx.get("fixes") or [])
    assert idx["sop_missing_flow"]["fix_id"] == "fix_sop_append_flow"
