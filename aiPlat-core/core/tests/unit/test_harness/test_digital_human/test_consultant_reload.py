"""Hot-reload AGENT.md + constitution by mtime."""
from __future__ import annotations

import time
from types import SimpleNamespace

from core.harness.digital_human.consultant_reload import (
    apply_system_prompt,
    clear_reload_cache,
    load_constitution_fresh,
    parse_agent_system_prompt,
    refresh_consultant_prompt,
)


def test_parse_nested_system_prompt():
    raw = """---
name: platform_consultant
config:
  system_prompt: |
    你是小朱测试提示词。
    第二行。
---

# body
"""
    sp = parse_agent_system_prompt(raw)
    assert "小朱测试提示词" in sp
    assert "第二行" in sp


def test_refresh_on_mtime(monkeypatch, tmp_path):
    clear_reload_cache()
    home = tmp_path / "aiplat"
    agent_dir = home / "agents" / "platform_consultant"
    agent_dir.mkdir(parents=True)
    md = agent_dir / "AGENT.md"
    md.write_text(
        "---\nname: platform_consultant\nconfig:\n  system_prompt: |\n    版本一\n---\n\n# x\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPLAT_HOME", str(home))

    conv = SimpleNamespace(system_prompt="旧")
    cfg = SimpleNamespace(metadata={"system_prompt": "旧"})
    agent = SimpleNamespace(_conv_config=conv, _config=cfg)

    assert refresh_consultant_prompt(agent)
    assert "版本一" in conv.system_prompt
    assert cfg.metadata["system_prompt"].strip().startswith("版本一")

    # same mtime → no-op
    assert not refresh_consultant_prompt(agent)

    time.sleep(0.02)
    md.write_text(
        "---\nname: platform_consultant\nconfig:\n  system_prompt: |\n    版本二热更新\n---\n\n# x\n",
        encoding="utf-8",
    )
    assert refresh_consultant_prompt(agent)
    assert "版本二热更新" in conv.system_prompt


def test_constitution_mtime(monkeypatch, tmp_path):
    clear_reload_cache()
    path = tmp_path / "consultant_constitution.md"
    path.write_text("# 心智卡A\n规则一\n", encoding="utf-8")
    monkeypatch.setattr(
        "core.harness.digital_human.consultant_reload.constitution_path",
        lambda: path,
    )
    t1 = load_constitution_fresh(max_chars=500)
    assert "心智卡A" in t1
    t1b = load_constitution_fresh(max_chars=500)
    assert t1b == t1  # cache hit

    time.sleep(0.02)
    path.write_text("# 心智卡B\n规则二热更新\n", encoding="utf-8")
    t2 = load_constitution_fresh(max_chars=500)
    assert "心智卡B" in t2
    assert "规则二热更新" in t2


def test_apply_system_prompt_empty():
    assert not apply_system_prompt(None, "x")
    assert not apply_system_prompt(SimpleNamespace(), "")
