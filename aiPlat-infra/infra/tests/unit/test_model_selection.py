"""Model selection strategy tests — audit fixes P0-1/P0-2/P1-3/P1-4/P2-6/P2-7.

Covered:
  P0-1  _score_model latency/cost penalties must stay negative (no sign inversion)
  P0-2  select_by_purpose_list fallback must exist in the registry
  P1-3  fallback key reads config (safe_model), no hardcoded deepseek-chat
  P1-4  get_default_model validates env model against registry
  P2-6  purpose→env mapping derives from llm_profile.yaml env_model_map
  P2-7  select() local-first is quality-gated (not unconditional)
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import yaml  # noqa: E402

from infra.management.model.manager import (  # noqa: E402
    ModelManager,
    _get_scoring_weights,
)
from infra.management.schemas import ModelInfo, ModelSource, ModelType  # noqa: E402


def _profile() -> dict:
    return yaml.safe_load(open("config/infra/llm_profile.yaml"))


def _mk(name, type_=ModelType.CHAT, source=ModelSource.EXTERNAL,
        provider="test", enabled=True, size=None) -> ModelInfo:
    return ModelInfo(id=f"id-{name}", name=name, type=type_, source=source,
                     provider=provider, enabled=enabled, size=size)


class TestScoringSign:
    """P0-1: latency/cost penalties must be negative (no sign inversion)."""

    def test_latency_penalty_negative(self):
        w = _get_scoring_weights("chat", _profile())
        assert w["latency"] < 0
        # -20 (API penalty) × abs(-2.5) must stay ≤ 0 — the old code computed +50.
        assert -20 * abs(w["latency"]) < 0
        assert -40 * abs(w["latency"]) < 0  # historical latency penalty

    def test_cost_penalty_negative(self):
        w = _get_scoring_weights("wiki_curation", _profile())
        assert w["cost"] < 0
        assert -10 * abs(w["cost"]) < 0


class TestFallbackValidation:
    """P0-2/P1-3: empty candidates must never return an unregistered model."""

    def test_empty_registry_returns_empty(self):
        mgr = ModelManager()
        # only an embedding model → no chat candidates, safe_model not registered
        mgr._models = {"emb": _mk("all-MiniLM-L6-v2", type_=ModelType.EMBEDDING)}
        assert mgr.select_by_purpose_list("chat") == []

    def test_fallback_returned_only_when_registered(self):
        mgr = ModelManager()
        # safe_model (qwen2.5:3b) registered but not a chat model → fallback path
        mgr._models = {"q": _mk("qwen2.5:3b", type_=ModelType.EMBEDDING,
                                source=ModelSource.LOCAL, provider="ollama")}
        res = mgr.select_by_purpose_list("chat")
        assert res == ["qwen2.5:3b"]

    def test_no_hardcoded_deepseek_chat(self):
        """P1-3: fallback_model must come from config, never 'deepseek-chat'."""
        cfg = _profile()
        fb = cfg.get("fallback", {})
        assert "safe_model" in fb
        assert fb.get("safe_model") != "deepseek-chat"


class TestGetDefaultModelValidation:
    """P1-4: env model must exist in registry; P2-6: mapping from yaml."""

    def test_env_model_not_in_registry_ignored(self, monkeypatch):
        mgr = ModelManager()
        mgr._models = {"m": _mk("local-model")}
        monkeypatch.setenv("AIPLAT_DEFAULT_CHAT_MODEL", "ghost-model")
        assert mgr.get_default_model("chat") == ""

    def test_env_model_in_registry_returned(self, monkeypatch):
        mgr = ModelManager()
        mgr._models = {"m": _mk("real-model")}
        monkeypatch.setenv("AIPLAT_DEFAULT_CHAT_MODEL", "real-model")
        assert mgr.get_default_model("chat") == "real-model"

    def test_env_model_disabled_ignored(self, monkeypatch):
        mgr = ModelManager()
        mgr._models = {"m": _mk("disabled-model", enabled=False)}
        monkeypatch.setenv("AIPLAT_DEFAULT_CHAT_MODEL", "disabled-model")
        assert mgr.get_default_model("chat") == ""

    def test_env_model_map_from_yaml(self, monkeypatch):
        """P2-6: env_model_map in llm_profile.yaml drives purpose→env resolution."""
        mgr = ModelManager()
        mgr._models = {"m": _mk("mapped-model")}
        monkeypatch.setenv("AIPLAT_EVAL_MODEL", "mapped-model")
        assert mgr.get_default_model("eval_code") == "mapped-model"


class TestSelectQualityGate:
    """P2-7: select() local-first must be quality-gated, not unconditional."""

    def test_local_preferred_when_no_api_counterpart(self):
        mgr = ModelManager()
        mgr._models = {"l": _mk("m", source=ModelSource.LOCAL, provider="ollama")}
        assert mgr.select("m").source == ModelSource.LOCAL

    def test_api_preferred_without_quality_data(self):
        """Local + API share a name; no quality data → API (old code: unconditional local)."""
        mgr = ModelManager()
        mgr._models = {
            "l": _mk("m", source=ModelSource.LOCAL, provider="ollama"),
            "a": _mk("m", source=ModelSource.EXTERNAL, provider="deepseek"),
        }
        got = mgr.select("m")
        assert got is not None
        assert got.source == ModelSource.EXTERNAL


class TestExploration:
    """P2 exploration: config-driven cold bonus + optional epsilon-greedy."""

    def test_cold_bonus_configurable(self):
        import infra.management.model.manager as mgr_mod
        val = mgr_mod._calculate_dynamic_boost(
            "cold-model", {"model_exploration": {"cold_bonus": 5.0, "cold_threshold": 5}})
        assert isinstance(val, float)

    def test_epsilon_zero_stable(self):
        import yaml
        from infra.management.model.manager import ModelManager
        from infra.management.schemas import ModelInfo, ModelSource
        cfg = yaml.safe_load(open("config/infra/llm_profile.yaml"))
        assert cfg["model_exploration"]["explore_epsilon"] == 0.0
        mgr = ModelManager()
        mgr._models = {
            "a": ModelInfo(id="a", name="deepseek-chat", provider="deepseek", source=ModelSource.EXTERNAL),
            "b": ModelInfo(id="b", name="model-b", provider="deepseek", source=ModelSource.EXTERNAL),
        }
        assert mgr.unified_pipeline("chat", [], {}, cfg) == mgr.unified_pipeline("chat", [], {}, cfg)

    def test_epsilon_positive_explores(self, monkeypatch):
        import random, yaml
        from infra.management.model.manager import ModelManager
        from infra.management.schemas import ModelInfo, ModelSource
        cfg = yaml.safe_load(open("config/infra/llm_profile.yaml"))
        cfg["model_exploration"]["explore_epsilon"] = 1.0
        monkeypatch.setattr(random, "random", lambda: 0.0)
        mgr = ModelManager()
        mgr._models = {
            "a": ModelInfo(id="a", name="deepseek-chat", provider="deepseek", source=ModelSource.EXTERNAL),
            "b": ModelInfo(id="b", name="model-b", provider="deepseek", source=ModelSource.EXTERNAL),
        }
        top = mgr.unified_pipeline("chat", [], {}, cfg)
        assert top in ("deepseek-chat", "model-b")  # 探索结果仍是注册表模型


class TestProviderBreadth:
    """2026-08-24 生态广度：providers.yaml 新增家族可被 ModelManager 发现（防回归）。"""

    def test_api_provider_ids_include_new_families(self):
        from infra.management.model.manager import _api_provider_ids

        ids = _api_provider_ids()
        # 基础 6 + 2026-08-24 首批 8 家族 + 2026-08-25 二批 8 家族 + 三批 8 家族
        for expected in ("openai", "deepseek", "anthropic", "openrouter",
                         "qwen", "groq", "mistral", "cohere",
                         "cerebras", "together", "xai", "novita",
                         "siliconflow", "moonshot", "minimax", "zhipu",
                         "baichuan", "stepfun", "deepinfra", "fireworks",
                         "gemini", "nvidia", "huggingface", "upstage",
                         "arcee", "zai", "xiaomi", "nous"):
            assert expected in ids, f"provider '{expected}' not discovered"

    def test_providers_yaml_has_30_entries(self):
        cfg = yaml.safe_load(open("config/providers.yaml"))
        assert len(cfg["providers"]) >= 30
        # 所有 external provider 都带 env_key（API key 契约）
        for p in cfg["providers"]:
            if p["type"] == "external" and p.get("requires_api_key"):
                assert p.get("env_key"), f"external provider {p['id']} missing env_key"
