"""Offline: platform approvals lazy store without KernelRuntime.

Must not leak stubbed modules into sys.modules (breaks later platform tests).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


def test_lazy_store_without_kernel_runtime():
    saved = {}
    stub_names = [
        "core.api.core_facade",
        "auth.deps",
        "core.api.deps",
        "core.api.utils.governance",
        "core.api.utils.run_contract",
        "core.api.facades.runtime_facade",
        "api.schemas_response",
        "approvals_lazy_under_test",
    ]
    for name in stub_names:
        saved[name] = sys.modules.get(name)

    try:
        cf = types.ModuleType("core.api.core_facade")

        class FakeStore:
            async def list_approval_requests(self, **kw):
                return {"items": [], "total": 0}

            async def get_change_linkages_for_approval_request_ids(self, ids):
                return {}

        class FakeMgr:
            def __init__(self, execution_store=None):
                self.execution_store = execution_store

            def get_pending_requests(self, user_id=None):
                return []

        cf.ApprovalManager = FakeMgr
        cf.get_execution_store = lambda: FakeStore()
        sys.modules["core.api.core_facade"] = cf

        for name in [
            "auth.deps",
            "core.api.deps",
            "core.api.utils.governance",
            "core.api.utils.run_contract",
            "core.api.facades.runtime_facade",
            "api.schemas_response",
        ]:
            if name not in sys.modules or name in stub_names:
                sys.modules[name] = types.ModuleType(name)

        sys.modules["auth.deps"].require_auth = lambda: "dev"
        sys.modules["core.api.deps"].actor_from_http = None
        sys.modules["core.api.deps"].rbac_guard = None
        sys.modules["core.api.utils.governance"].change_links = lambda *a, **k: {}
        sys.modules["core.api.utils.governance"].gate_error_envelope = None
        sys.modules["core.api.utils.governance"].ui_url = lambda x: x
        sys.modules["core.api.utils.run_contract"].wrap_execution_result_as_run_summary = None
        sys.modules["core.api.facades.runtime_facade"].get_kernel_runtime = lambda: None
        for n in ("ApprovalListResponse", "ApprovalActionResponse", "StatusResponse"):
            setattr(sys.modules["api.schemas_response"], n, dict)

        path = Path(__file__).resolve().parents[1] / "api" / "routers" / "approvals.py"
        spec = importlib.util.spec_from_file_location("approvals_lazy_under_test", path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod._store() is not None
        assert mod._approval_mgr() is not None
        res = asyncio.run(mod.list_pending_approvals())
        assert res.get("total") == 0
        assert res.get("items") == []

        # Store may return float epochs — normalize to ISO strings for response_model
        raw = {
            "items": [
                {
                    "request_id": "a1",
                    "status": "pending",
                    "created_at": 1790698319.20875,
                    "updated_at": 1790698319.208757,
                    "expires_at": None,
                }
            ],
            "total": 1,
        }
        norm = mod._normalize_approval_list_response(raw)
        assert isinstance(norm["items"][0]["created_at"], str)
        assert "T" in norm["items"][0]["created_at"]
        assert norm["items"][0]["expires_at"] is None
    finally:
        for name, prev in saved.items():
            if prev is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prev
