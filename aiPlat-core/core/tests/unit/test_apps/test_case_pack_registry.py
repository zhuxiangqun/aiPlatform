"""Pack registry ACL + atomic write + manifest hash verify (P0 nails 2/4/5)."""
from __future__ import annotations

import copy
import threading

import pytest

from core.apps.eval.service.case_pack_hash import compute_pack_hash
from core.apps.eval.service.case_pack_legacy import (
    ManifestValidationError,
    expand_sets_to_manifest,
    task_dict_to_case,
    verify_manifest_case_hashes,
)
from core.apps.eval.service.case_pack_registry import (
    PackRegistryError,
    assert_pack_acl,
    get_pack_version,
    register_pack_version,
)


def test_verify_manifest_hashes_ok():
    man, _, _ = expand_sets_to_manifest(["default/normal"])
    assert man
    verify_manifest_case_hashes(man)  # no raise


def test_verify_manifest_hash_mismatch_fail_closed():
    man, _, _ = expand_sets_to_manifest(["default/normal"])
    assert man
    bad = copy.deepcopy(man)
    bad[0]["hash"] = "sha256:" + ("0" * 64)
    with pytest.raises(ManifestValidationError, match="hash mismatch"):
        verify_manifest_case_hashes(bad)


def test_workspace_acl_cross_deny():
    with pytest.raises(PackRegistryError, match="ACL deny"):
        assert_pack_acl(
            scope="workspace",
            workspace_id="ws-a",
            caller_workspace_id="ws-b",
            write=False,
        )


def test_global_write_denied_p0():
    with pytest.raises(PackRegistryError, match="read-only"):
        assert_pack_acl(scope="global", write=True)


def test_registry_atomic_duplicate_and_concurrent(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    case = task_dict_to_case(
        {
            "task_id": "r1",
            "user_input": "hi",
            "success_criteria": {"must_contain": ["hi"]},
            "category": "normal",
        },
        set_id="custom/x",
    )
    ph = compute_pack_hash(
        pack_id="ws.demo",
        version="1.0.0",
        kind="curated",
        claim_eligible=False,
        scope="workspace",
        object_types=["agent"],
        cases=[case],
    )
    meta = register_pack_version(
        pack_id="ws.demo",
        version="1.0.0",
        kind="curated",
        claim_eligible=False,
        scope="workspace",
        pack_hash=ph,
        object_types=["agent"],
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert meta["hash"] == ph
    got = get_pack_version(
        pack_id="ws.demo",
        version="1.0.0",
        scope="workspace",
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert got["hash"] == ph

    with pytest.raises(PackRegistryError, match="already registered"):
        register_pack_version(
            pack_id="ws.demo",
            version="1.0.0",
            kind="curated",
            claim_eligible=False,
            scope="workspace",
            pack_hash=ph,
            workspace_id="ws-a",
            caller_workspace_id="ws-a",
        )

    errors: list = []

    def _race(ver: str) -> None:
        try:
            register_pack_version(
                pack_id="ws.demo",
                version=ver,
                kind="curated",
                claim_eligible=False,
                scope="workspace",
                pack_hash=ph,
                workspace_id="ws-a",
                caller_workspace_id="ws-a",
            )
        except PackRegistryError as e:
            errors.append(str(e))

    t1 = threading.Thread(target=_race, args=("2.0.0",))
    t2 = threading.Thread(target=_race, args=("2.0.0",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # One success, one fail — registry file must remain readable
    assert len(errors) == 1
    get_pack_version(
        pack_id="ws.demo",
        version="2.0.0",
        scope="workspace",
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )


def test_generated_claim_blocked_on_register(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    with pytest.raises(Exception, match="claim_eligible"):
        register_pack_version(
            pack_id="gen.x",
            version="1.0.0",
            kind="generated",
            claim_eligible=True,
            scope="workspace",
            pack_hash="sha256:" + ("a" * 64),
            workspace_id="ws-a",
            caller_workspace_id="ws-a",
        )


def test_expand_workspace_registers_pack(tmp_path, monkeypatch):
    """Production wire: expand_sets_to_manifest syncs workspace packs into registry."""
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    man, refs, _ = expand_sets_to_manifest(
        ["default/normal"],
        scope="workspace",
        kind="curated",
        claim_eligible=False,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert man and refs
    got = get_pack_version(
        pack_id=refs[0]["pack_id"],
        version=refs[0]["version"],
        scope="workspace",
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert got["hash"] == refs[0]["hash"]
    # second expand must not clobber; same hash ok
    _, refs2, _ = expand_sets_to_manifest(
        ["default/normal"],
        scope="workspace",
        kind="curated",
        claim_eligible=False,
        workspace_id="ws-a",
        caller_workspace_id="ws-a",
    )
    assert refs2[0]["hash"] == refs[0]["hash"]
