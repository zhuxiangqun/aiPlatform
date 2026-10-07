"""Tool/MCP create-dialog prompts must be registered without importing workbench app."""

from core.apps.workbench.prompts import register_workbench_prompts
from core.harness.utils.prompt_loader import _sync_resolve


def test_tool_create_dialog_prompt_registered():
    register_workbench_prompts()
    text = _sync_resolve("tool-create-dialog", history="", latest_user="创建一个上传工具")
    assert "latest_user" in text or "创建一个上传工具" in text
    role = _sync_resolve("tool-create-dialog-system-role")
    assert "Tool" in role


def test_mcp_create_dialog_prompt_registered():
    register_workbench_prompts()
    text = _sync_resolve("mcp-create-dialog", history="", latest_user="接 OSS")
    assert "接 OSS" in text or "latest_user" in text
