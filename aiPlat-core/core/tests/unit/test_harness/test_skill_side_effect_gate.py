from core.harness.execution.skill_side_effect_gate import (
    ERROR_CODE,
    skill_result_if_unrealized_side_effects,
    unrealized_side_effect_reason,
)
from core.harness.interfaces import SkillConfig


class _PromptSkill:
    def __init__(self, cfg):
        self._config = cfg


def test_prompt_write_is_unrealized():
    skill = _PromptSkill(
        SkillConfig(
            name="upload_like",
            effects=[{"type": "write", "resources": ["filesystem:~"]}],
            metadata={"execution_type": "prompt"},
        )
    )
    reason = unrealized_side_effect_reason(skill)
    assert reason and ERROR_CODE in reason
    refused = skill_result_if_unrealized_side_effects(skill)
    assert refused is not None and refused.success is False


def test_prompt_emit_is_allowed():
    skill = _PromptSkill(
        SkillConfig(
            name="prd",
            effects=[{"type": "emit", "resources": ["artifact:prd"]}],
            metadata={"execution_type": "prompt"},
        )
    )
    assert unrealized_side_effect_reason(skill) is None


def test_handler_write_allowed_when_handler_on_disk(tmp_path):
    hp = tmp_path / "handler.py"
    hp.write_text("def execute(params):\n    return {'ok': True}\n", encoding="utf-8")
    skill = _PromptSkill(
        SkillConfig(
            name="fs",
            effects=[{"type": "write", "resources": ["filesystem:~"]}],
            metadata={
                "execution_type": "handler",
                "filesystem": {"skill_dir": str(tmp_path)},
            },
        )
    )
    assert unrealized_side_effect_reason(skill) is None


def test_mutating_permission_without_handler_refused():
    skill = _PromptSkill(
        SkillConfig(
            name="wiki_like",
            metadata={
                "execution_type": "prompt",
                "permissions": ["wiki:write"],
            },
        )
    )
    assert unrealized_side_effect_reason(skill)


def test_read_effect_with_write_resource_is_unrealized():
    skill = _PromptSkill(
        SkillConfig(
            name="site_like",
            effects=[{"type": "read", "resources": ["browser:page", "filesystem:write"]}],
            metadata={"execution_type": "prompt"},
        )
    )
    assert unrealized_side_effect_reason(skill)


def test_http_permission_prompt_is_unrealized():
    skill = _PromptSkill(
        SkillConfig(
            name="api_like",
            metadata={"execution_type": "prompt", "permissions": ["http:request"]},
        )
    )
    assert unrealized_side_effect_reason(skill)


def test_empty_effects_upload_sop_is_unrealized():
    skill = {
        "name": "upload_like",
        "execution_type": "prompt",
        "description": "接收用户上传的视频文件，存储并生成可访问的播放链接。",
        "input_schema": {"file": {"type": "file", "required": True}},
        "output_schema": {"play_url": {"type": "string"}},
        "permissions": [],
        "effects": [],
        "body": "## 执行流程\n1. 上传文件到对象存储\n2. 生成播放链接\n",
    }
    reason = unrealized_side_effect_reason(skill)
    assert reason and ERROR_CODE in reason


def test_emit_code_generation_not_inferred_from_file_blocks():
    skill = _PromptSkill(
        SkillConfig(
            name="code_generation",
            description="根据需求生成代码（## FILE: 格式）。",
            effects=[{"type": "emit", "resources": ["artifact:file_blocks"]}],
            metadata={"execution_type": "prompt"},
        )
    )
    assert unrealized_side_effect_reason(skill) is None


def test_python_class_non_generic_allowed():
    class ApplyPatch:
        def __init__(self):
            self._config = SkillConfig(
                name="patch",
                effects=[{"type": "write", "resources": ["filesystem:~"]}],
                metadata={"execution_type": "python_class"},
            )

    assert unrealized_side_effect_reason(ApplyPatch()) is None
