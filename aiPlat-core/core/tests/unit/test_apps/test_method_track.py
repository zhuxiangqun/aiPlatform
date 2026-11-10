"""Method track — Arena/G2b/S1 must not become Subjects."""
from __future__ import annotations

import pytest

from core.apps.eval.service.method_track import (
    METHOD_KINDS,
    MethodTrackError,
    assert_not_subject_method,
    assert_subject_kinds_exclude_methods,
    list_method_kinds,
    method_catalog,
)
from core.apps.eval.service.subject_adapter import get_subject_adapter, list_subject_kinds


def test_method_kinds_canonical():
    assert list_method_kinds() == ["arena", "g2b", "s1"]
    assert METHOD_KINDS == {"arena", "g2b", "s1"}


def test_method_catalog_honesty():
    rows = method_catalog()
    assert len(rows) == 3
    for row in rows:
        assert row["track"] == "method"
        assert row["object_type_eligible"] is False
        assert row["subject_adapter_eligible"] is False
        assert row["claim_eligible"] is False
        assert "honesty" in row


def test_get_subject_adapter_refuses_methods():
    for kind in ("arena", "g2b", "s1"):
        with pytest.raises(MethodTrackError) as ei:
            get_subject_adapter(kind)
        assert kind in str(ei.value)


def test_assert_not_subject_method_direct():
    with pytest.raises(MethodTrackError):
        assert_not_subject_method("arena")
    assert_not_subject_method("agent")  # no raise


def test_registered_subjects_exclude_methods():
    kinds = list_subject_kinds()
    report = assert_subject_kinds_exclude_methods(kinds)
    assert report["ok"] is True, report.get("errors")
    assert not (set(kinds) & METHOD_KINDS)


def test_eval_method_track_status_facade():
    from core.api.core_facade import eval_method_track_status

    st = eval_method_track_status()
    assert st["ok"] is True
    assert st["accuracy_claim"] is False
    assert st["claim_eligible"] is False
    assert st["method_kinds"] == ["arena", "g2b", "s1"]
    assert len(st["methods"]) == 3
    assert "agent" in st["subject_kinds"]
    assert st["subject_exclude_methods"]["ok"] is True
