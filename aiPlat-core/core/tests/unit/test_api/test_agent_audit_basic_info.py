"""Agent AI audit: model strategy / toolset / loop / permissions / pipeline."""
from __future__ import annotations

from pathlib import Path

import pytest


def _write_agent(tmp_path, agent_id: str, body: str) -> None:
    agent_dir = tmp_path / ".aiplat" / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(body, encoding="utf-8")


@pytest.mark.asyncio
async def test_audit_conversational_react_loop_uses_agent_purpose(tmp_path, monkeypatch):
    """Architect-like: agent_type=conversational + loop_type=react → purpose=agent (not chat)."""
    _write_agent(
        tmp_path,
        "audit_arch_like",
        "---\n"
        "name: audit_arch_like\n"
        "agent_type: conversational\n"
        "status: ready\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "config:\n"
        "  model: tiny-weak:1b\n"
        "  system_prompt: you are an architect\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    class _MI:
        name = "tiny-weak:1b"

    class _Mgr:
        def select(self, model_name: str = "", purpose: str = ""):
            return _MI() if model_name == "tiny-weak:1b" else None

        def get_model_tier(self, model_name, profile_data=None):
            return "small"

    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "strong-reasoner:70b",
            "model_tier": "large",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {
            "purpose_profiles": {
                "agent": {"require": {"reasoning_quality": 3}},
                "chat": {"require": {"type": "chat"}},
            }
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "infra.management.model.manager._filter_capability",
        lambda model, purpose, profile, profile_data=None: False if purpose == "agent" else True,
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_arch_like")
    cats = {i["category"] for i in resp.issues}
    assert "missing_skill_model_purpose" in cats
    assert "model_unsuitable" in cats
    hit = next(i for i in resp.issues if i["category"] == "model_unsuitable")
    assert "purpose=agent" in hit["message"]
    assert hit["fix"]["model"] == "strong-reasoner:70b"


@pytest.mark.asyncio
async def test_audit_flags_model_unsuitable_for_purpose(tmp_path, monkeypatch):
    _write_agent(
        tmp_path,
        "audit_model_gate",
        "---\n"
        "name: audit_model_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "skill_model_purpose: agent\n"
        "config:\n"
        "  model: tiny-weak:1b\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))

    class _Reg:
        def list_tools(self):
            return []

    monkeypatch.setattr("core.apps.tools.base.get_tool_registry", lambda: _Reg())

    class _MI:
        name = "tiny-weak:1b"

    class _Mgr:
        def select(self, model_name: str = "", purpose: str = ""):
            return _MI() if model_name == "tiny-weak:1b" else None

        def get_model_tier(self, model_name, profile_data=None):
            return "small"

    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "strong-reasoner:70b",
            "model_tier": "large",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {
            "purpose_profiles": {
                "agent": {
                    "require": {"reasoning_quality": 3, "context_window": 32000},
                }
            }
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "infra.management.model.manager._filter_capability",
        lambda model, purpose, profile, profile_data=None: False,
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_model_gate")
    hit = next(i for i in resp.issues if i["category"] == "model_unsuitable")
    assert hit["current"] == "tiny-weak:1b"
    assert hit["fix"]["type"] == "set_model"
    assert hit["fix"]["model"] == "strong-reasoner:70b"


@pytest.mark.asyncio
async def test_audit_flags_model_local_ram_exceeded(tmp_path, monkeypatch):
    """Fixed local model over RAM budget must warn (wedge risk), not only suboptimal."""
    _write_agent(
        tmp_path,
        "audit_model_ram",
        "---\n"
        "name: audit_model_ram\n"
        "agent_type: conversational\n"
        "status: ready\n"
        "loop_type: react\n"
        "skill_model_purpose: agent\n"
        "config:\n"
        "  model: gemma4:12b\n"
        "  system_prompt: you are an architect\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    class _MI:
        name = "gemma4:12b"
        size = int(7.6 * 1024**3)
        provider = "ollama"
        enabled = True

    class _Mgr:
        def select(self, model_name: str = "", purpose: str = ""):
            return _MI() if model_name == "gemma4:12b" else None

        def get_model_tier(self, model_name, profile_data=None):
            return "T4"

    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5-coder:7b",
            "model_tier": "T4",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {
            "purpose_profiles": {"agent": {"require": {"reasoning_quality": 2}}},
            "fallback": {"local_max_ram_ratio": 0.40},
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "infra.management.model.manager._filter_capability",
        lambda model, purpose, profile, profile_data=None: True,
    )
    monkeypatch.setattr(
        "infra.management.model.manager._hard_filter",
        lambda model, res, profile_data=None: (
            False,
            "local model 7.6GB exceeds 40% of RAM — would wedge Ollama",
        ),
    )
    monkeypatch.setattr(
        "infra.management.model.manager.collect_platform_resources",
        lambda: type("R", (), {"ram_bytes": 4 * 1024**3, "ram_total_bytes": 16 * 1024**3})(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_model_ram")
    hit = next(i for i in resp.issues if i["category"] == "model_local_ram_exceeded")
    assert hit["severity"] == "warning"
    assert hit["current"] == "gemma4:12b"
    assert hit["fix"]["model"] == "qwen2.5-coder:7b"


@pytest.mark.asyncio
async def test_audit_flags_model_suboptimal_same_tier(tmp_path, monkeypatch):
    """Fixed model that passes capability but differs from pipeline pick must warn,
    even when tier labels are identical (gemma4:12b vs qwen2.5-coder:7b both T4)."""
    _write_agent(
        tmp_path,
        "audit_model_subopt",
        "---\n"
        "name: audit_model_subopt\n"
        "agent_type: conversational\n"
        "status: ready\n"
        "loop_type: react\n"
        "skill_model_purpose: agent\n"
        "config:\n"
        "  model: gemma4:12b\n"
        "  system_prompt: you are an architect\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )

    class _MI:
        name = "gemma4:12b"

    class _Mgr:
        def select(self, model_name: str = "", purpose: str = ""):
            return _MI() if model_name == "gemma4:12b" else None

        def get_model_tier(self, model_name, profile_data=None):
            return "T4"  # same tier as recommended — old bug required tier mismatch

    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5-coder:7b",
            "model_tier": "T4",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {
            "purpose_profiles": {
                "agent": {"require": {"reasoning_quality": 2}},
            }
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: _Mgr(),
    )
    monkeypatch.setattr(
        "infra.management.model.manager._filter_capability",
        lambda model, purpose, profile, profile_data=None: True,
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_model_subopt")
    hit = next(i for i in resp.issues if i["category"] == "model_suboptimal")
    assert hit["severity"] == "warning"
    assert hit["current"] == "gemma4:12b"
    assert hit["fix"]["model"] == "qwen2.5-coder:7b"


@pytest.mark.asyncio
async def test_audit_flags_model_unavailable(tmp_path, monkeypatch):
    _write_agent(
        tmp_path,
        "audit_model_missing",
        "---\n"
        "name: audit_model_missing\n"
        "agent_type: conversational\n"
        "status: ready\n"
        "skill_model_purpose: chat\n"
        "config:\n"
        "  model: does-not-exist:99b\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"chat": {"require": {"type": "chat"}}}},
    )

    class _Mgr:
        def select(self, model_name: str = "", purpose: str = ""):
            return None

        def get_model_tier(self, model_name, profile_data=None):
            return "unknown"

    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: _Mgr(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_model_missing")
    hit = next(i for i in resp.issues if i["category"] == "model_unavailable")
    assert hit["severity"] == "error"
    assert hit["fix"]["model"] == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_audit_flags_invalid_toolset_and_loop(tmp_path, monkeypatch):
    _write_agent(
        tmp_path,
        "audit_policy_gate",
        "---\n"
        "name: audit_policy_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "toolset: not_a_real_set\n"
        "loop_type: mystery\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type("M", (), {"select": lambda self, **k: None, "get_model_tier": lambda self, *a, **k: "unknown"})(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_policy_gate")
    cats = {i["category"] for i in resp.issues}
    assert "invalid_toolset" in cats
    assert "invalid_loop_type" in cats


@pytest.mark.asyncio
async def test_audit_flags_hitl_without_phase(tmp_path, monkeypatch):
    _write_agent(
        tmp_path,
        "audit_hitl_gate",
        "---\n"
        "name: audit_hitl_gate\n"
        "agent_type: react\n"
        "status: ready\n"
        "phase: design\n"
        "hitl_after_execute: true\n"
        "permissions:\n"
        "  - llm:generate\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type("M", (), {"select": lambda self, **k: None, "get_model_tier": lambda self, *a, **k: "unknown"})(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_hitl_gate")
    cats = {i["category"] for i in resp.issues}
    assert "hitl_phase_missing" in cats
    assert "missing_phase_description" in cats
    assert "missing_loop_type" not in cats
    assert "missing_permissions" not in cats


@pytest.mark.asyncio
async def test_audit_silent_on_default_loop_and_permissions(tmp_path, monkeypatch):
    """UI defaults (react / llm:generate) must not nag when AGENT.md omits them."""
    _write_agent(
        tmp_path,
        "audit_defaults_ok",
        "---\n"
        "name: audit_defaults_ok\n"
        "agent_type: react\n"
        "status: ready\n"
        "config:\n"
        "  system_prompt: you are a test agent\n"
        "---\n"
        "## Persona\n"
        "test\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type(
            "M",
            (),
            {"select": lambda self, **k: None, "get_model_tier": lambda self, *a, **k: "unknown"},
        )(),
    )

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_defaults_ok")
    cats = {i["category"] for i in resp.issues}
    assert "missing_loop_type" not in cats
    assert "missing_permissions" not in cats
    assert "permissions_incomplete" not in cats
    assert "invalid_loop_type" not in cats


def _stub_model(monkeypatch):
    monkeypatch.setattr(
        "core.apps.tools.base.get_tool_registry",
        lambda: type("R", (), {"list_tools": lambda self: []})(),
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection.best_model_for_purpose_with_meta",
        lambda purpose, messages=None: {
            "model": "qwen2.5:7b",
            "model_tier": "medium",
            "model_purpose": purpose,
        },
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._load_llm_profile",
        lambda: {"purpose_profiles": {"agent": {}, "chat": {}}},
    )
    monkeypatch.setattr(
        "core.harness.utils.model_injection._get_cached_model_manager",
        lambda: type(
            "M",
            (),
            {"select": lambda self, **k: None, "get_model_tier": lambda self, *a, **k: "unknown"},
        )(),
    )


@pytest.mark.asyncio
async def test_audit_flags_thin_sop_content(tmp_path, monkeypatch):
    _write_agent(
        tmp_path,
        "audit_sop_thin",
        "---\n"
        "name: audit_sop_thin\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - architecture_design\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: short\n"
        "---\n"
        "hello\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    _stub_model(monkeypatch)

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_sop_thin")
    cats = {i["category"] for i in resp.issues}
    assert "sop_short" in cats or "sop_missing_role" in cats
    assert "sop_missing_flow" in cats or "sop_missing_goal" in cats or "sop_missing_quality" in cats
    assert "sop_skills_unreferenced" in cats
    assert any(i["severity"] == "warning" and str(i["category"]).startswith("sop_") for i in resp.issues)
    hit = next(i for i in resp.issues if i["category"] == "sop_skills_unreferenced")
    assert hit.get("fix_available") is True
    assert hit.get("fix", {}).get("type") == "append_sop_skill_refs"
    assert "architecture_design" in ((hit.get("fix") or {}).get("skills") or [])
    appendix = str((hit.get("fix") or {}).get("appendix") or "")
    assert "`architecture_design`" in appendix


@pytest.mark.asyncio
async def test_audit_sop_skill_refs_fix_clears_warning(tmp_path, monkeypatch):
    """One-click appendix upsert makes sop_skills_unreferenced disappear."""
    from core.management.asset_audit import upsert_sop_skill_refs_appendix

    thin = (
        "# 角色：架构师\n\n"
        "## 工作流程\n"
        "1. 读取 PRD\n"
        "2. 产出架构\n\n"
        "## 输出格式\n"
        "必须包含 components；禁止编造。\n"
    )
    fixed = upsert_sop_skill_refs_appendix(thin, ["architecture_design"])
    _write_agent(
        tmp_path,
        "audit_sop_refs_fixed",
        "---\n"
        "name: audit_sop_refs_fixed\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - architecture_design\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: 你是架构师\n"
        "---\n"
        f"{fixed}\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    _stub_model(monkeypatch)

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_sop_refs_fixed")
    cats = {i["category"] for i in resp.issues}
    assert "sop_skills_unreferenced" not in cats


@pytest.mark.asyncio
async def test_audit_rich_sop_passes_content_gates(tmp_path, monkeypatch):
    sop = (
        "# 角色：架构师\n\n"
        "根据 PRD 输出架构。\n\n"
        "## 工作流程\n"
        "1. 读取 PRD\n"
        "2. 调用 `architecture_design` 生成架构 JSON\n"
        "3. 自检验收\n\n"
        "## 输出格式\n"
        "必须包含 components；禁止上公网存储客户照片。\n"
    )
    _write_agent(
        tmp_path,
        "audit_sop_rich",
        "---\n"
        "name: audit_sop_rich\n"
        "agent_type: react\n"
        "status: ready\n"
        "required_skills:\n"
        "  - architecture_design\n"
        "loop_type: react\n"
        "toolset: workspace_default\n"
        "permissions:\n"
        "  - llm:generate\n"
        "config:\n"
        "  system_prompt: 你是架构师\n"
        "---\n"
        f"{sop}\n",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path / ".aiplat"))
    _stub_model(monkeypatch)

    from core.api.routers.workspace_agents import audit_agent_config

    resp = await audit_agent_config("audit_sop_rich")
    cats = {i["category"] for i in resp.issues}
    assert "sop_missing_role" not in cats
    assert "sop_missing_flow" not in cats
    assert "sop_missing_goal" not in cats
    assert "sop_missing_quality" not in cats
    assert "sop_skills_unreferenced" not in cats
    assert "sop_empty" not in cats
    assert "sop_content_ok" in cats
    hit = next(i for i in resp.issues if i["category"] == "sop_content_ok")
    assert hit["severity"] == "info"


def test_empty_agent_sop_one_click_appendices():
    src = (
        Path(__file__).resolve().parents[3]
        / "api"
        / "routers"
        / "workspace_agents.py"
    ).read_text(encoding="utf-8")
    assert 'category": "sop_empty"' not in src
    assert "0 < n < 80" in src
    assert "fix_append_sop_role" in src
    assert "fix_append_sop_flow" in src
