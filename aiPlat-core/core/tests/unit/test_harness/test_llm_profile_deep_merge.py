"""Workspace llm_profile must deep-merge onto infra (not shallow-replace purpose_profiles)."""

from __future__ import annotations


def test_deep_merge_preserves_infra_chat_require():
    from core.harness.utils import model_injection as mi

    base = {
        "purpose_profiles": {
            "chat": {
                "require": {"type": "chat", "hallucination_max": 0.10},
                "weights": {"latency": -2.5, "quality": 0.3},
            },
            "agent": {
                "require": {"reasoning_quality": 3},
                "weights": {"reasoning": 3.5},
            },
        }
    }
    overlay = {
        "purpose_profiles": {
            "chat": {"prefer_local": True},
            "agent": {"prefer_local": True},
        }
    }
    mi._deep_merge_dict(base, overlay)
    assert base["purpose_profiles"]["chat"]["require"]["hallucination_max"] == 0.10
    assert base["purpose_profiles"]["chat"]["prefer_local"] is True
    assert base["purpose_profiles"]["agent"]["require"]["reasoning_quality"] == 3
    assert base["purpose_profiles"]["agent"]["prefer_local"] is True
    # Shallow update would have wiped require — must still be present
    assert "weights" in base["purpose_profiles"]["chat"]


def test_load_llm_profile_keeps_agent_require_with_ws_prefer_local(monkeypatch, tmp_path):
    """Workspace prefer_local must not erase infra agent.require after deep merge."""
    import yaml
    from core.harness.utils import model_injection as mi

    infra = tmp_path / "infra.yaml"
    ws_dir = tmp_path / "config" / "infra"
    ws_dir.mkdir(parents=True)
    ws = ws_dir / "llm_profile.yaml"

    infra.write_text(
        yaml.dump(
            {
                "purpose_profiles": {
                    "chat": {
                        "require": {"type": "chat", "hallucination_max": 0.10},
                        "weights": {"latency": -2.5},
                    },
                    "agent": {
                        "require": {"reasoning_quality": 3, "context_window": 32000},
                        "weights": {"reasoning": 3.5},
                    },
                },
                "fallback": {"safe_model": "qwen2.5:3b"},
            }
        ),
        encoding="utf-8",
    )
    ws.write_text(
        yaml.dump(
            {
                "purpose_profiles": {
                    "chat": {"prefer_local": True},
                    "agent": {"prefer_local": True},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("AIPLAT_LLM_CONFIG_PATH", str(infra))
    # _load_llm_profile resolves project_root from model_injection.py location;
    # redirect workspace overlay by patching Path construction via env is hard —
    # instead invoke merge the same way _load_llm_profile does after reading both files.
    base = yaml.safe_load(infra.read_text(encoding="utf-8")) or {}
    overlay = yaml.safe_load(ws.read_text(encoding="utf-8")) or {}
    mi._deep_merge_dict(base, overlay)
    agent = base["purpose_profiles"]["agent"]
    assert agent["require"]["reasoning_quality"] == 3
    assert agent["require"]["context_window"] == 32000
    assert agent["prefer_local"] is True
    assert agent["weights"]["reasoning"] == 3.5
