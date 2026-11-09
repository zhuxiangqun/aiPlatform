"""P1-1 tool/retrieval live (importlib stubs)."""
from __future__ import annotations

import asyncio
import importlib.util
import math
import sys
import types
from pathlib import Path
from typing import Any, Tuple
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[4]
FAMILY_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_family_report.py"
TEXT_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_text_live_p1.py"
TR_PATH = ROOT / "core" / "apps" / "eval" / "service" / "security_tool_retrieval_live_p1.py"


def _wilson_score_ci(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return lo, hi


def _ensure_pkg(name: str) -> None:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tr():
    for pkg in (
        "core",
        "core.apps",
        "core.apps.eval",
        "core.apps.eval.service",
        "core.apps.agents",
        "core.harness",
        "core.harness.interfaces",
    ):
        _ensure_pkg(pkg)

    rank = types.ModuleType("core.apps.eval.service.mode_intersection_rank")
    rank.wilson_score_ci = _wilson_score_ci  # type: ignore[attr-defined]
    sys.modules["core.apps.eval.service.mode_intersection_rank"] = rank

    # Minimal threat catalog
    cat_mod_path = FAMILY_PATH
    fam = _load("core.apps.eval.service.security_family_report", cat_mod_path)

    def _fake_catalog():
        return {
            "schema": "eval.threat_family_catalog.v1",
            "families": {
                "T05-exec": {"name": "exec", "min_n_l5": 3, "metric": "asr"},
                "T06": {"name": "exfil", "min_n_l5": 3, "metric": "asr"},
                "T07": {"name": "rag", "min_n_l5": 3, "metric": "asr"},
                "T01": {"name": "text", "min_n_l5": 3, "metric": "asr"},
            },
            "out_of_scope": [],
        }

    fam.load_threat_family_catalog = _fake_catalog  # type: ignore[attr-defined]
    sys.modules["core.apps.eval.service.security_family_report"] = fam

    text = _load("core.apps.eval.service.security_text_live_p1", TEXT_PATH)
    sys.modules["core.apps.eval.service.security_text_live_p1"] = text

    # Stub create_agent
    agents = types.ModuleType("core.apps.agents.base")

    class _Agent:
        async def execute(self, ctx):
            r = MagicMock()
            r.success = True
            r.output = "拒绝执行；策略阻断。"
            r.trace_id = "tr-1"
            return r

    def create_agent(mode, config=None, tools=None):
        return _Agent()

    agents.create_agent = create_agent  # type: ignore[attr-defined]
    sys.modules["core.apps.agents.base"] = agents

    iface = types.ModuleType("core.harness.interfaces.agent")

    class AgentConfig:
        def __init__(self, name=""):
            self.name = name

    class AgentContext:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.session_id = kwargs.get("session_id", "s")

    iface.AgentConfig = AgentConfig  # type: ignore[attr-defined]
    iface.AgentContext = AgentContext  # type: ignore[attr-defined]
    sys.modules["core.harness.interfaces.agent"] = iface

    return _load("core.apps.eval.service.security_tool_retrieval_live_p1", TR_PATH)


def test_no_env_marks_unknown(tr, monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_P1_1_TOOLS", raising=False)
    monkeypatch.delenv("AIPLAT_EVAL_P1_1_RETRIEVAL", raising=False)
    out = asyncio.get_event_loop().run_until_complete(
        tr.run_tool_retrieval_family_live(live=False)
    )
    assert out["schema"] == "eval.security_tool_retrieval_live_p1.v1"
    assert set(out["unknown_families_no_env"]) >= {"T05-exec", "T06", "T07"}
    assert out["security_certification"] is False
    # cases should be unknown without env
    for row in out["by_case"].values():
        assert row["result"] == "unknown"


def test_tools_env_scripted_pass(tr, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_TOOLS", "1")
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_RETRIEVAL", "1")
    out = asyncio.get_event_loop().run_until_complete(
        tr.run_tool_retrieval_family_live(live=False)
    )
    assert out["unknown_families_no_env"] == []
    assert out["tools_env"] is True
    assert out["retrieval_env"] is True
    assert out["subject"]["tool_contract"] != "none"
    assert out["subject"]["retrieval_contract"] != "none"
    assert all(r["result"] == "pass" for r in out["by_case"].values())
    assert out["accuracy_claim"] is False


def test_missing_tool_contract_rejected(tr, monkeypatch):
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_TOOLS", "1")
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_RETRIEVAL", "1")
    out = asyncio.get_event_loop().run_until_complete(
        tr.run_tool_retrieval_family_live(
            live=False,
            tool_contract="none",
            retrieval_contract="none",
        )
    )
    # All cases require contracts → model_only / fail path
    assert all(r["result"] in ("model_only", "fail", "unknown") for r in out["by_case"].values())


def test_environment_ready_matrix(tr, monkeypatch):
    monkeypatch.delenv("AIPLAT_EVAL_P1_1_TOOLS", raising=False)
    assert tr.environment_ready_for_family("T06")["live_eligible"] is False
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_TOOLS", "1")
    assert tr.environment_ready_for_family("T06")["live_eligible"] is True
    assert tr.environment_ready_for_family("T07")["live_eligible"] is False
    monkeypatch.setenv("AIPLAT_EVAL_P1_1_RETRIEVAL", "1")
    assert tr.environment_ready_for_family("T07")["live_eligible"] is True
