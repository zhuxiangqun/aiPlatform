"""Unit tests for LLM execution-examples JSON extraction + thin gate (no LLM)."""

import json

from core.apps.skills.service.skill_execution_examples_llm import _extract_json_array
from core.management.execution_examples import example_content_is_thin, filter_rich_execution_examples


def test_extract_json_array_plain():
    body = (
        "段落一。进展：上架门禁已接通。"
        "段落一。进展：上架门禁已接通。"
        "段落一。进展：上架门禁已接通。"
        "\n段落二：风险冒烟偏弱。\n段落三：下周补用例。\n请输出三点摘要并标注风险"
    )
    raw = json.dumps([{"title": "长文摘要", "content": {"text": body}}], ensure_ascii=False)
    out = _extract_json_array(raw)
    assert len(out) == 1
    assert out[0]["title"] == "长文摘要"
    assert "段落一" in out[0]["content"]


def test_extract_json_array_fenced_and_rejects_legacy_and_thin():
    rich = (
        "【周报】\n一、进展：资产审批上架门禁已接通，依赖校验返回明细。"
        "\n二、风险：部分冒烟用例仍是一句话占位，难以验证压缩质量。"
        "\n三、下周：按能力类型丰富执行测试用例并清理待审核队列。"
        "\n请输出三点摘要+一条风险+一条行动（勿编造）。"
    )
    raw = "```json\n" + json.dumps(
        [
            {"title": "坏占位", "content": "请按本能力说明完成一次冒烟测试"},
            {"title": "坏一句", "content": {"user_requirement": "做个搜索功能"}},
            {"title": "好", "content": rich},
        ],
        ensure_ascii=False,
    ) + "\n```"
    out = _extract_json_array(raw)
    titles = [e["title"] for e in out]
    assert "好" in titles
    assert "坏占位" in titles  # extract keeps chips; schema/thin gate drops later
    kept = filter_rich_execution_examples(out, min_keep=1)
    assert [e["title"] for e in kept] == ["好"]


def test_filter_rich_drops_one_liners():
    kept = filter_rich_execution_examples(
        [
            {"title": "薄", "content": '{"q":"hi"}'},
            {
                "title": "厚",
                "content": (
                    "【简单冒烟】\n角色：采购员在 PC 搜商品\n目标：关键词出结果\n"
                    "范围：不做图片搜、不做个性化推荐\n"
                    "约束：常见词 1s 内出结果（口述待压测）\n"
                    "未知：拼音/错别字容错是否要做\n"
                    "请按契约输出可检查结果，禁止空话。"
                ),
            },
        ],
        min_keep=1,
    )
    assert len(kept) == 1
    assert kept[0]["title"] == "厚"
    assert example_content_is_thin('{"user_requirement":"做个搜索"}') is True


def test_skill_llm_uses_skill_execution_and_persist_only_on_llm():
    from pathlib import Path

    from core.management.execution_examples import accept_llm_execution_examples

    schema = {
        "file": {"type": "file", "required": True, "description": "本地视频文件，支持MP4"},
        "file_size": {"type": "integer", "required": True, "description": "字节不超过2GB"},
    }
    poisoned = [
        {"title": "主", "content": json.dumps({"file": "示例: 本地视频文件，支持MP4", "file_size": 3}, ensure_ascii=False)},
        {"title": "边", "content": json.dumps({"file": "本地视频文件，支持MP4", "file_size": 8}, ensure_ascii=False)},
    ]
    assert accept_llm_execution_examples(poisoned, schema, skill_hint="upload_video") == []

    svc = Path(__file__).resolve().parents[3] / "apps/skills/service/skill_execution_examples_llm.py"
    text = svc.read_text(encoding="utf-8")
    assert 'best_model_for_purpose("skill_execution")' in text
    assert "clarify" not in text
    assert "accept_llm_execution_examples" in text
    assert "run_generate_skill_execution_examples" in text
    from core.apps.skills.service.skill_execution_examples_llm import skill_md_frontmatter_and_excerpt

    class _Empty:
        metadata = {}

    _fm, excerpt = skill_md_frontmatter_and_excerpt(None, _Empty(), "code_generation")
    assert excerpt
    assert "FILE" in excerpt or "代码" in excerpt or len(excerpt) > 80
    router = Path(__file__).resolve().parents[3] / "api/routers/workspace_skills.py"
    rt = router.read_text(encoding="utf-8")
    assert "run_generate_skill_execution_examples" in rt
    engine = Path(__file__).resolve().parents[3] / "api/routers/engine_skills.py"
    et = engine.read_text(encoding="utf-8")
    assert "run_generate_skill_execution_examples" in et
    assert "/skills/{skill_id}/execution-help" in et
    mgr = Path(__file__).resolve().parents[3] / "management/skill_manager.py"
    assert "_resolve_skill_example_schema" in mgr.read_text(encoding="utf-8")
    agent_r = Path(__file__).resolve().parents[3] / "api/routers/workspace_agents.py"
    at = agent_r.read_text(encoding="utf-8")
    assert 'persist and str(result.get("source") or "") == "llm"' in at
    agent_svc = Path(__file__).resolve().parents[3] / "apps/agents/service/agent_execution_examples_llm.py"
    assert "accept_llm_execution_examples" in agent_svc.read_text(encoding="utf-8")
