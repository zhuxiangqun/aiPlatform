"""N23 deepen：企业域 OCS 扫描（DomainRouter + 词汇预注册）；certified 恒 false。"""
from __future__ import annotations

from pathlib import Path

import yaml

from core.api.core_facade import (
    evaluate_ocs_enterprise_scan_gate,
    run_ocs_enterprise_scan_suite,
)
from core.harness.knowledge.ontology_completeness import (
    evaluate_ocs_enterprise_scan_gate as core_gate,
    run_ocs_enterprise_scan_suite as core_suite,
)
from core.harness.ontology_engine.graph_index import GraphIndex

ROOT = Path(__file__).resolve().parents[6]
PROBE = "n23-probe"


def _seed_probe(home: Path) -> None:
    onto = home / "ontologies"
    onto.mkdir(parents=True, exist_ok=True)
    (onto / f"{PROBE}.yaml").write_text(
        yaml.dump(
            {
                "name": PROBE,
                "namespace": f"http://example/{PROBE}/",
                "ocs_threshold": 80,
                "classes": {
                    "ProbeClass": {
                        "label": "Probe",
                        "tier": "logic",
                        "required_fields": ["id"],
                    },
                },
                "object_properties": [],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    GraphIndex._loaded_instances.clear()


def test_suite_and_gate_honesty(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _seed_probe(home)
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()

    suite = core_suite(domain_ids=[PROBE])
    assert suite["ok"] is True
    assert suite["passed"] == 4
    assert suite["certified"] is False
    assert suite["n23_full_conformance"] is False
    assert suite["enterprise_complete"] is False
    assert suite.get("domains") == [PROBE]
    gate = core_gate(suite)
    assert gate["ok"] is True
    bad = dict(suite)
    bad["enterprise_complete"] = True
    honesty = core_gate(bad)
    assert honesty["ok"] is False
    assert "honesty_certified_flag_forbidden" in honesty["issues"]


def test_facade_suite(tmp_path, monkeypatch):
    home = tmp_path / "home"
    _seed_probe(home)
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    GraphIndex._loaded_instances.clear()

    suite = run_ocs_enterprise_scan_suite(domain_ids=[PROBE])
    assert suite["ok"] is True
    gate = evaluate_ocs_enterprise_scan_gate(suite)
    assert gate["ok"] is True
    assert gate["certified"] is False


def test_empty_domain_list_fails_vocab():
    suite = core_suite(domain_ids=[])
    assert suite["ok"] is False
    ids = {c["id"]: c for c in suite["cases"]}
    assert ids["vocab_prereg_required"]["ok"] is False


def test_docs_and_wiring_state():
    ocs = (
        ROOT
        / "aiPlat-core"
        / "core"
        / "harness"
        / "knowledge"
        / "ontology_completeness.py"
    )
    text = ocs.read_text(encoding="utf-8")
    assert "run_ocs_enterprise_scan_suite" in text
    assert "evaluate_ocs_enterprise_scan_gate" in text
    facade = ROOT / "aiPlat-core" / "core" / "api" / "core_facade.py"
    assert "run_ocs_enterprise_scan_suite" in facade.read_text(encoding="utf-8")
