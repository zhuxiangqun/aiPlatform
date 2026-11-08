"""P1.0 Case Factory draft path + P0 acceptance smoke (T2/T7/T10/T12 anchors)."""
from __future__ import annotations

import pytest

from core.apps.eval.service.case_factory import (
    CaseFactoryError,
    dedupe_cases_by_hash,
    generate_cases_from_template,
    publish_draft_workspace_pack,
    validate_case_dict,
)
from core.apps.eval.service.case_pack_legacy import (
    ManifestValidationError,
    apply_manifest_sampling,
    expand_sets_to_manifest,
)
from core.apps.eval.service.case_pack_registry import PackRegistryError, assert_pack_acl


def test_generate_validate_dedupe_publish(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {
            "category": "normal",
            "rubric": {"type": "lexical", "must_contain": ["ok"]},
            "id_stem": "tpl",
        },
        variants=[
            {"prompt": "say ok"},
            {"prompt": "say ok"},  # duplicate hash after normalize
            {"prompt": "say ok please", "case_id": "tpl-unique"},
        ],
    )
    assert len(cases) == 3
    for c in cases:
        validate_case_dict(c)
    deduped = dedupe_cases_by_hash(cases)
    assert len(deduped) == 2
    out = publish_draft_workspace_pack(
        pack_id="ws.factory.demo",
        version="0.1.0",
        cases=deduped,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert out["ok"] is True
    assert out["claim_eligible"] is False
    assert out["n_cases"] == 2
    assert out["registry"]["status"] == "draft"


def test_factory_cannot_freeze_or_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    cases = generate_cases_from_template(
        {"prompt": "x", "rubric": {"type": "lexical"}, "category": "normal"},
        variants=[{"case_id": "c1"}],
    )
    with pytest.raises(CaseFactoryError, match="frozen"):
        publish_draft_workspace_pack(
            pack_id="ws.x",
            version="1.0.0",
            cases=cases,
            workspace_id="ws-a",
            kind="frozen",
        )


def test_p0_acceptance_anchors():
    # T2 seed stability
    man, _, _ = expand_sets_to_manifest(["default/normal", "default/noise"])
    a, _ = apply_manifest_sampling(man, strategy="random", sample_n=3, seed=99)
    b, _ = apply_manifest_sampling(man, strategy="random", sample_n=3, seed=99)
    assert [r["case_id"] for r in a] == [r["case_id"] for r in b]
    # T7 generated+claim blocked at factory/registry layer via publish kind curated only
    # T10 ACL
    with pytest.raises(PackRegistryError, match="ACL deny"):
        assert_pack_acl(
            scope="workspace",
            workspace_id="ws-a",
            caller_workspace_id="ws-b",
        )
    # T12 shortfall
    with pytest.raises(ManifestValidationError, match="shortfall"):
        apply_manifest_sampling(
            man,
            strategy="stratified",
            sample_n=1,
            seed=1,
            min_per_stratum=999,
            on_insufficient="error",
        )
