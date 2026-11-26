"""FDE Extended F07–F09 契约测量。"""
from __future__ import annotations

from pathlib import Path

from core.apps.fde.service.extended_contracts import (
    fde_optional_process_contract,
    fde_slice_report_binding_policy,
    fde_workbench_signoff_surface,
)


def test_f07_slice_binding_policy():
    p = fde_slice_report_binding_policy()
    assert p["policy_id"] == "F07"
    assert "validate_slice_signoff_reports" in p["canonical_validator"]
    assert "signoff" in p["http_entry"]


def test_f08_workbench_surface():
    s = fde_workbench_signoff_surface()
    assert s["surface_id"] == "F08"
    assert s["no_parallel_signoff_api"] is True
    root = Path(__file__).resolve().parents[5]
    dash = root / "aiPlat-management/frontend/src/pages/Diagnostics/FdeDashboard.tsx"
    assert dash.is_file()
    txt = dash.read_text(encoding="utf-8")
    assert "AcceptTab" in txt
    assert "acceptance/signoff" in txt


def test_f09_optional_process_scripts_exist():
    c = fde_optional_process_contract()
    assert c["contract_id"] == "F09"
    assert c["compose_long_running_authorized"] is False
    assert c["process_split_authorized"] is False
    assert c["scripts_exist"] is True
