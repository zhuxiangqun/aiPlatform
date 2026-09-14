"""Phase B security_review team + security_plan handler skeleton tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

from core.harness.execution.team_planner import load_team_template
from core.engine.skills.security_plan.handler import (
    DEFAULT_MAX_PATHS,
    SINK_WHITELIST,
    _filter_hot_paths,
    execute as plan_execute,
)


def test_security_review_team_loads():
    tpl = load_team_template("security_review")
    assert tpl is not None
    assert tpl.name == "security_review"
    assert len(tpl.stages) == 5
    ids = [s.get("id") for s in tpl.stages]
    assert ids == [
        "security_plan",
        "security_trace",
        "security_critique",
        "security_report",
        "security_evidence",
    ]
    assert tpl.stages[0]["skill_name"] == "security_plan"
    assert tpl.stages[3].get("hitl") is True  # security_report
    assert tpl.stages[4].get("skill_name") == "security_evidence"
    assert (tpl.stages[4].get("node_config") or {}).get("enabled") is False
    assert tpl.stages[0].get("failure_strategy") == "fail_pipeline"
    for s in tpl.stages:
        assert s.get("allow_dynamic_spawn") is False
        assert s.get("skill_name")
        assert s.get("output_artifact")
        assert s.get("execution_backend") == "llm"
        assert (s.get("tools") or []) == []


def test_security_plan_skill_files_exist():
    core = Path(__file__).resolve().parents[4]  # .../core
    for name in (
        "security_plan",
        "security_trace",
        "security_critique",
        "security_report",
        "security_evidence",
    ):
        skill = core / "engine" / "skills" / name / "SKILL.md"
        assert skill.is_file(), skill
        assert (core / "engine" / "skills" / name / "handler.py").is_file()


def test_filter_hot_paths_whitelist_and_layers():
    paths = [
        {
            "id": "path:1",
            "sink_id": "sink:subprocess:a.py",
            "entry_id": "entry:x",
            "layer": "platform",
            "score": 100,
            "via": [],
            "risk_hint": "external→sink_without_gate",
        },
        {
            "id": "path:2",
            "sink_id": "sink:filesystem_write:b.py",
            "entry_id": "entry:y",
            "layer": "platform",
            "score": 99,
            "via": [],
            "risk_hint": "external→sink_without_gate",
        },
        {
            "id": "path:3",
            "sink_id": "sink:sql:c.py",
            "entry_id": "entry:z",
            "layer": "core",
            "score": 98,
            "via": ["m"],
            "risk_hint": "external→sink_without_gate",
        },
    ]
    out = _filter_hot_paths(
        paths,
        sink_whitelist=set(SINK_WHITELIST),
        entry_layers={"platform", "app"},
        max_paths=DEFAULT_MAX_PATHS,
    )
    assert len(out) == 1
    assert out[0]["id"] == "path:1"
    assert out[0]["max_severity"] == "candidate"


def test_plan_stage_node_config_present():
    tpl = load_team_template("security_review")
    nc = tpl.stages[0].get("node_config") or {}
    assert nc.get("max_paths") == 20
    assert "core" in (nc.get("entry_layers") or [])
    assert "subprocess" in (nc.get("sink_whitelist") or [])


def test_build_handler_params_merges_node_config():
    from core.harness.execution.pipeline_stage import PipelineStageMixin
    from core.schemas_builder import PipelineStageConfig

    class _T(PipelineStageMixin):
        def _resolve_project_label(self, state):
            return "t"

    stage = PipelineStageConfig(
        id="security_plan",
        agent_id="security_planner",
        node_config={"max_paths": 12, "sink_whitelist": ["sql"]},
    )
    params = _T()._build_handler_params(stage, {})
    assert params["max_paths"] == 12
    assert params["sink_whitelist"] == ["sql"]


def test_plan_execute_with_injected_empty_graph(monkeypatch):
    from core.harness.knowledge.security_view import SecurityView, RepoSummary

    def _fake_build(**kwargs):
        return SecurityView(
            schema_version="secview.v1",
            repo_id="t",
            built_at="",
            graph_stats={"files": 0},
            layers={},
            entries=[],
            sinks=[],
            gates=[],
            hot_paths=[],
            repo_summary=RepoSummary(),
            metrics={"heuristic": True},
        )

    monkeypatch.setattr(
        "core.harness.knowledge.security_view.build_security_view",
        _fake_build,
    )

    result = asyncio.run(plan_execute({"force": True}))
    assert result["schema_version"] == "secview.v1"
    assert result["params"]["max_paths"] == DEFAULT_MAX_PATHS
    assert result["params"]["max_severity"] == "candidate"
    assert result["top_hot_paths"] == []
    assert "subprocess" in result["params"]["sink_whitelist"]


def test_critique_refutes_gate_likely_and_ops():
    from core.engine.skills.security_critique.handler import execute as critique_execute

    plan = {
        "top_hot_paths": [
            {
                "id": "path:1",
                "entry_id": "entry:platform/api/a.py",
                "sink_id": "sink:subprocess:core/x.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
                "score": 90,
            },
            {
                "id": "path:2",
                "entry_id": "entry:aiPlat-platform/apps/fde/api/fde_acceptance.py",
                "sink_id": "sink:subprocess:aiPlat-core/core/api/routers/diagnostics.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
                "score": 100,
            },
            {
                "id": "path:3",
                "entry_id": "entry:p.py",
                "sink_id": "sink:sql:s.py",
                "gates_on_path": ["gate:1"],
                "risk_hint": "gate_present",
                "score": 50,
            },
        ]
    }
    trace = {
        "traces": [
            {
                "path_id": "path:1",
                "possible_gates": [r"\bDepends\s*\("],
                "anchors": [{"file": "a.py", "line": 1, "snippet": "x"}],
            },
            {
                "path_id": "path:2",
                "possible_gates": [],
                "anchors": [
                    {"file": "fde_acceptance.py", "line": 1, "snippet": "@router.get"},
                    {
                        "file": "diagnostics.py",
                        "line": 1,
                        "snippet": "subprocess.run(['x'])",
                    },
                ],
            },
            {
                "path_id": "path:3",
                "possible_gates": [],
                "anchors": [{"file": "s.py", "line": 1, "snippet": "execute("}],
            },
        ]
    }
    out = asyncio.run(
        critique_execute({"security_plan": plan, "security_trace": trace})
    )
    assert out["counts"]["refuted"] >= 2
    assert all(f.get("severity") == "candidate" for f in out["findings"])
    ref_ids = {r["path_id"] for r in out["refuted"]}
    assert "path:1" in ref_ids  # gate_likely
    assert "path:2" in ref_ids  # ops accepted_risk
    assert "path:3" in ref_ids  # gate_on_path


def test_critique_refutes_weak_anchor_and_internal_tooling():
    from core.engine.skills.security_critique.handler import execute as critique_execute

    plan = {
        "top_hot_paths": [
            {
                "id": "path:w",
                "entry_id": "entry:aiPlat-platform/apps/fde/api/fde_acceptance.py",
                "sink_id": "sink:subprocess:aiPlat-core/core/harness/context/engine.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            },
            {
                "id": "path:t",
                "entry_id": "entry:aiPlat-platform/apps/fde/api/fde_reports.py",
                "sink_id": "sink:subprocess:aiPlat-core/core/management/arch_guard_base.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            },
            {
                "id": "path:g",
                "entry_id": "entry:aiPlat-platform/apps/fde/api/fde_acceptance.py",
                "sink_id": "sink:subprocess:aiPlat-core/core/engine/skills/autoreview/diff_loader.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            },
            {
                "id": "path:keep",
                "entry_id": "entry:aiPlat-platform/apps/misc/api/download.py",
                "sink_id": "sink:network_egress:aiPlat-infra/utils/http.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            },
        ]
    }
    trace = {
        "traces": [
            {
                "path_id": "path:w",
                "possible_gates": [],
                "anchors": [
                    {"file": "fde_acceptance.py", "line": 19, "snippet": "@router.get(\"/x\")"},
                    {"file": "engine.py", "line": 1, "snippet": '"""'},
                ],
            },
            {
                "path_id": "path:t",
                "possible_gates": [],
                "anchors": [
                    {"file": "fde_reports.py", "line": 21, "snippet": "@router.get(\"/r\")"},
                    {
                        "file": "arch_guard_base.py",
                        "line": 327,
                        "snippet": "result = subprocess.run(proc_cmd,",
                    },
                ],
            },
            {
                "path_id": "path:g",
                "possible_gates": [],
                "anchors": [
                    {"file": "fde_acceptance.py", "line": 19, "snippet": "@router.get(\"/x\")"},
                    {
                        "file": "diff_loader.py",
                        "line": 30,
                        "snippet": "result = subprocess.run(cmd, capture_output=True, text=True)",
                    },
                ],
            },
            {
                "path_id": "path:keep",
                "possible_gates": [],
                "anchors": [
                    {"file": "download.py", "line": 10, "snippet": "@router.post(\"/fetch\")"},
                    {
                        "file": "http.py",
                        "line": 5,
                        "snippet": "return requests.get(url)",
                    },
                ],
            },
        ]
    }
    out = asyncio.run(
        critique_execute({"security_plan": plan, "security_trace": trace})
    )
    ref = {r["path_id"]: r["reason"] for r in out["refuted"]}
    assert "path:w" in ref and "weak_sink_anchor" in ref["path:w"]
    assert "path:t" in ref
    assert "path:g" in ref
    assert out["counts"]["findings"] == 1
    assert out["findings"][0]["path_id"] == "path:keep"


def test_critique_refutes_infra_management_ops():
    from core.engine.skills.security_critique.handler import execute as critique_execute

    plan = {
        "top_hot_paths": [
            {
                "id": "path:i",
                "entry_id": "entry:aiPlat-core/core/api/routers/models_route.py",
                "sink_id": "sink:subprocess:aiPlat-infra/infra/management/network/manager.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            }
        ]
    }
    trace = {
        "traces": [
            {
                "path_id": "path:i",
                "possible_gates": [],
                "anchors": [
                    {"file": "models_route.py", "line": 1, "snippet": "@router.get"},
                    {
                        "file": "manager.py",
                        "line": 51,
                        "snippet": "proc = subprocess.run(['lsof', '-i'])",
                    },
                ],
            }
        ]
    }
    out = asyncio.run(
        critique_execute({"security_plan": plan, "security_trace": trace})
    )
    assert out["counts"]["findings"] == 0
    assert out["refuted"][0]["reason"] == "accepted_risk:infra_management_ops"


def test_critique_refutes_prose_eval_false_positive():
    from core.engine.skills.security_critique.handler import execute as critique_execute

    plan = {
        "top_hot_paths": [
            {
                "id": "path:p",
                "entry_id": "entry:aiPlat-core/core/api/routers/wiki.py",
                "sink_id": "sink:eval_exec:aiPlat-core/core/harness/knowledge/domain_maturity.py",
                "gates_on_path": [],
                "risk_hint": "external→sink_without_gate",
            }
        ]
    }
    trace = {
        "traces": [
            {
                "path_id": "path:p",
                "possible_gates": [],
                "anchors": [
                    {"file": "wiki.py", "line": 1, "snippet": "@router.get"},
                    {
                        "file": "domain_maturity.py",
                        "line": 10,
                        "snippet": "6. eval_score — Golden Query eval (None if not available)",
                    },
                ],
            }
        ]
    }
    out = asyncio.run(
        critique_execute({"security_plan": plan, "security_trace": trace})
    )
    assert out["counts"]["findings"] == 0
    assert out["refuted"][0]["reason"] == "prose_eval_false_positive"
    from core.engine.skills.security_report.handler import execute as report_execute

    out = asyncio.run(
        report_execute(
            {
                "security_plan": {
                    "schema_version": "secview.v1",
                    "_token_estimate": 100,
                    "top_hot_paths": [{}],
                    "params": {"heuristic": True},
                },
                "security_trace": {"traces": [{}]},
                "security_critique": {
                    "findings": [{"severity": "critical", "summary": "x"}],
                    "refuted": [{"path_id": "p"}],
                },
            }
        )
    )
    assert out["header"]["phase"] == "B"
    assert out["header"]["max_severity"] == "candidate"
    assert out["findings"][0]["severity"] == "candidate"
    assert out["header"]["counts"]["refuted"] == 1


def test_phase_c_default_off():
    from core.engine.skills.security_evidence.handler import execute as ev

    out = asyncio.run(
        ev(
            {
                "security_report": {
                    "findings": [
                        {
                            "path_id": "path:1",
                            "severity": "candidate",
                            "sink_id": "sink:eval_exec:aiPlat-core/core/apps/exec_drivers/ssh.py",
                            "category": "rce",
                        }
                    ]
                },
                "enabled": False,
            }
        )
    )
    assert out["enabled"] is False
    assert out["results"] == []


def test_phase_c_ssh_driver_refute_and_merge():
    from core.engine.skills.security_evidence.handler import (
        execute as ev,
        merge_evidence_into_report,
    )

    finding = {
        "path_id": "path:35",
        "severity": "candidate",
        "sink_id": "sink:eval_exec:aiPlat-core/core/apps/exec_drivers/ssh.py",
        "entry_id": "entry:aiPlat-core/core/api/routers/diagnostics.py",
        "category": "rce",
    }
    evidence = asyncio.run(
        ev({"security_report": {"findings": [finding]}, "enabled": True})
    )
    assert evidence["enabled"] is True
    assert evidence["counts"]["candidates"] == 1
    assert evidence["results"][0]["disposition"] == "refuted"
    assert evidence["results"][0]["physical_evidence"] is True
    assert Path(evidence["results"][0]["evidence_path"]).is_file()

    report = {
        "header": {"phase": "B", "max_severity": "candidate"},
        "findings": [dict(finding)],
        "refuted": [],
    }
    merged = merge_evidence_into_report(report, evidence)
    assert merged["header"]["phase"] == "C"
    assert merged["findings"][0]["severity"] == "refuted"
    assert merged["findings"][0]["physical_evidence"] is True


def test_phase_c_ssrf_fixture():
    from core.engine.skills.security_evidence.handler import execute as ev

    evidence = asyncio.run(
        ev(
            {
                "enabled": True,
                "security_report": {
                    "findings": [
                        {
                            "path_id": "path:ssrf",
                            "severity": "candidate",
                            "category": "ssrf",
                            "sink_id": "sink:network_egress:x.py",
                        }
                    ]
                },
            }
        )
    )
    assert evidence["results"][0]["assert_id"] == "ssrf_fixture_block"
    assert evidence["results"][0]["disposition"] in {"refuted", "confirmed"}
