"""P1.3 case-packs HTTP routes registered on compat router."""
from __future__ import annotations

from core.api.routers import compat


def test_case_pack_routes_registered():
    paths = {
        getattr(r, "path", None)
        for r in compat.router.routes
        if hasattr(r, "path")
    }
    for p in (
        "/evaluation/case-packs/draft",
        "/evaluation/case-packs/enqueue-review",
        "/evaluation/case-packs/review-queue",
        "/evaluation/case-packs/review",
        "/evaluation/case-packs/freeze",
    ):
        assert p in paths


def test_case_pack_http_error_shapes_value_error():
    out = compat._case_pack_http_error(ValueError("boom"))
    assert out["ok"] is False
    assert out["accuracy_claim"] is False
    assert "boom" in out["error"]
