"""Upload Tool/MCP create dialog asks plain-language questions, not SRE jargon."""

from core.apps.common.upload_create_clarify import (
    maybe_upload_mcp_clarify,
    maybe_upload_tool_clarify,
)
from core.apps.workbench.prompts import register_workbench_prompts
from core.harness.utils.prompt_loader import _sync_resolve

SEED = (
    "帮我做一个把本地视频传到云存储、并返回能播放链接的 Tool。"
    "我不是技术人员，请用选择题问我（哪家云 / 桶名或还没建 / 链接能不能公开点开），"
    "不要问 endpoint 或环境变量名。"
)


def test_seed_asks_plain_language_not_endpoint():
    gate = maybe_upload_tool_clarify(text=SEED, history=[])
    assert gate and gate["next"] == "ask"
    blob = (gate.get("reply") or "") + "\n".join(gate.get("questions") or [])
    assert "不传到云上" in blob or "哪家云" in blob
    assert "endpoint" not in blob.lower()
    assert "ACCESS_KEY" not in blob
    assert "环境变量名" not in blob


def test_unsure_answers_draft_aliyun_template():
    gate = maybe_upload_tool_clarify(
        text="还不确定",
        history=[{"role": "user", "content": SEED}],
    )
    assert gate and gate["next"] == "draft"
    assert gate["name"] == "oss_upload"
    assert "OSS_ACCESS_KEY_ID" in gate["description"]
    assert "raise" in gate["description"]


def test_tencent_bucket_and_signed_link():
    gate = maybe_upload_tool_clarify(
        text="腾讯云，桶名叫 video-prod，只有限时链接能播",
        history=[{"role": "user", "content": SEED}],
    )
    assert gate and gate["next"] == "draft"
    assert gate["name"] == "cos_upload"
    assert "COS_SECRET_ID" in gate["description"]
    assert "签名" in gate["description"]


def test_skip_cloud_does_not_draft_oss_tool():
    gate = maybe_upload_tool_clarify(
        text="不传到云上，为什么要存到云端？",
        history=[{"role": "user", "content": SEED}],
    )
    assert gate and gate["next"] == "ask"
    assert gate.get("questions") == []
    assert "可以不上云" in (gate.get("reply") or "")
    assert "改成只出文案" in (gate.get("reply") or "")


def test_non_upload_passthrough():
    assert maybe_upload_tool_clarify(text="把 Markdown 转成 HTML", history=[]) is None


def test_mcp_seed_plain_language():
    seed = (
        "帮我接入云存储上传 MCP。我不是技术人员，请用选择题问哪家云、桶名（或还没建）、"
        "链接能不能公开点开，不要先问 SSE 地址或密钥名。"
    )
    gate = maybe_upload_mcp_clarify(text=seed, history=[])
    assert gate and gate["next"] == "ask"
    assert "SSE" not in "\n".join(gate.get("questions") or [])


def test_prompt_forbids_endpoint_quiz():
    register_workbench_prompts()
    role = _sync_resolve("tool-create-dialog")
    assert "环境变量名" not in role or "禁止问" in role
    assert "哪家云" in role
