"""Physical merge gates P0 — inflation + shape (merge-time veto)."""
from __future__ import annotations

from datetime import date

from core.harness.meta.physical_merge_gates import (
    DiffStats,
    assess_exemption_debt,
    collect_diff_stats,
    evaluate_diff,
    inflation_stats_for_caps,
    resolve_mode,
    select_profile,
)


def _cfg(**overrides):
    base = {
        "version": 1,
        "mode": "block",
        "block_after": "2099-01-01",
        "profiles": {
            "business": {
                "max_files": 3,
                "max_net_lines": 50,
                "max_new_deps": 0,
                "max_new_classes": 0,
                "max_new_dirs": 0,
                "max_inherit_bases": 0,
            },
            "framework": {
                "max_files": 40,
                "max_net_lines": 800,
                "max_new_deps": 2,
                "max_new_classes": 15,
                "max_new_dirs": 5,
                "max_inherit_bases": 2,
            },
        },
        "framework_globs": ["aiPlat-core/core/harness/**", "**/tests/**"],
        "banned_path_segments": ["/generic/", "/framework/"],
        "banned_new_basenames": ["event_bus.py", "observer.py", "*_scheduler.py"],
        "banned_class_substrings": ["EventBus", "ObserverTree"],
        "allowed_bases": ["object", "Exception", "ABC", "Protocol", "BaseModel"],
        "exemptions": [],
    }
    base.update(overrides)
    return base


def test_resolve_mode_block_after_escalates(monkeypatch):
    monkeypatch.delenv("AIPLAT_PHYSICAL_GATES_MODE", raising=False)
    cfg = {"mode": "warn", "block_after": "2026-01-01"}
    assert resolve_mode(cfg, now=date(2026, 11, 1)) == "block"
    assert resolve_mode(cfg, now=date(2025, 12, 1)) == "warn"


def test_select_profile_framework_when_all_match():
    cfg = _cfg()
    assert (
        select_profile(
            ["aiPlat-core/core/harness/meta/x.py", "aiPlat-core/core/harness/y.py"],
            cfg,
        )
        == "framework"
    )
    assert select_profile(["aiPlat-platform/apps/foo/api.py"], cfg) == "business"


def test_inflation_excludes_neutral_on_mixed_pr():
    cfg = _cfg(
        profile_neutral_globs=["AIPLAT_CAPABILITIES.md", "docs/**"],
    )
    stats = DiffStats(
        files_changed=10,
        paths=[
            "aiPlat-core/core/harness/meta/x.py",
            "AIPLAT_CAPABILITIES.md",
            "docs/whitepaper/volumes/01-tech-architecture.md",
            "docs/whitepaper/volumes/02-product-capability.md",
        ],
    )
    capped = inflation_stats_for_caps(stats, cfg)
    assert capped.files_changed == 1
    # Pure docs: keep full count
    docs_only = DiffStats(
        files_changed=3,
        paths=[
            "AIPLAT_CAPABILITIES.md",
            "docs/a.md",
            "docs/b.md",
        ],
    )
    assert inflation_stats_for_caps(docs_only, cfg).files_changed == 3


def test_select_profile_neutral_globs_do_not_force_business():
    cfg = _cfg(
        profile_neutral_globs=[
            "AIPLAT_CAPABILITIES.md",
            "docs/**",
            "**/capability_registry.yaml",
        ],
        framework_globs=[
            "aiPlat-core/core/harness/**",
            "aiPlat-core/core/api/core_facade.py",
            "**/tests/**",
        ],
    )
    assert (
        select_profile(
            [
                "aiPlat-core/core/harness/meta/evidence_envelope.py",
                "aiPlat-core/core/api/core_facade.py",
                "AIPLAT_CAPABILITIES.md",
                "aiPlat-core/core/capability_registry.yaml",
                "docs/architecture/system-architecture-contract.md",
            ],
            cfg,
        )
        == "framework"
    )
    # Pure sync / docs still business (tight).
    assert select_profile(["AIPLAT_CAPABILITIES.md", "docs/x.md"], cfg) == "business"
    # Platform app + docs → business.
    assert (
        select_profile(
            ["aiPlat-platform/apps/foo/api.py", "AIPLAT_CAPABILITIES.md"],
            cfg,
        )
        == "business"
    )


def test_inflation_blocks_large_diff():
    name_status = "\n".join(
        [
            "M\ta.py",
            "M\tb.py",
            "A\tc.py",
            "A\td.py",
        ]
    )
    numstat = "\n".join(
        [
            "40\t0\ta.py",
            "40\t0\tb.py",
            "40\t0\tc.py",
            "40\t0\td.py",
        ]
    )
    report = evaluate_diff(
        name_status=name_status,
        numstat=numstat,
        unified_diff="",
        config=_cfg(),
        profile_name="business",
    )
    assert report.ok is False
    codes = {f.code for f in report.findings}
    assert "inflation_files" in codes
    assert "inflation_net_lines" in codes


def test_warn_mode_exits_ok_with_findings(monkeypatch):
    monkeypatch.delenv("AIPLAT_PHYSICAL_GATES_MODE", raising=False)
    name_status = "A\ta.py\nA\tb.py\nA\tc.py\nA\td.py"
    numstat = "100\t0\ta.py\n100\t0\tb.py\n100\t0\tc.py\n100\t0\td.py"
    report = evaluate_diff(
        name_status=name_status,
        numstat=numstat,
        config=_cfg(mode="warn"),
        profile_name="business",
    )
    assert report.ok is True
    assert report.mode == "warn"
    assert report.findings
    assert all(f.severity == "warn" for f in report.findings)


def test_shape_bans_generic_path_and_event_bus():
    name_status = "A\taiPlat-platform/apps/foo/generic/helper.py\nA\taiPlat-platform/apps/foo/event_bus.py"
    unified = """diff --git a/aiPlat-platform/apps/foo/event_bus.py b/aiPlat-platform/apps/foo/event_bus.py
--- /dev/null
+++ b/aiPlat-platform/apps/foo/event_bus.py
@@ -0,0 +1,3 @@
+class MyEventBus:
+    pass
+
"""
    report = evaluate_diff(
        name_status=name_status,
        numstat="3\t0\taiPlat-platform/apps/foo/event_bus.py\n3\t0\taiPlat-platform/apps/foo/generic/helper.py",
        unified_diff=unified,
        config=_cfg(),
        profile_name="business",
    )
    codes = {f.code for f in report.findings}
    assert "shape_banned_path" in codes
    assert "shape_banned_basename" in codes or "shape_banned_class" in codes


def test_shape_deep_inherit():
    unified = """diff --git a/svc.py b/svc.py
--- /dev/null
+++ b/svc.py
@@ -0,0 +1,5 @@
+class BaseSvc:
+    pass
+class Deep(BaseSvc, AnotherBase):
+    pass
+
"""
    report = evaluate_diff(
        name_status="A\tsvc.py",
        numstat="5\t0\tsvc.py",
        unified_diff=unified,
        config=_cfg(),
        profile_name="business",
    )
    assert any(f.code.startswith("shape_deep_inherit") for f in report.findings)


def test_exemption_requires_expiry_and_reason():
    cfg = _cfg(
        exemptions=[
            {
                "id": "ex-ok",
                "owner": "platform-oncall",
                "reason": "migration",
                "expires": "2099-12-31",
                "gates": ["inflation", "shape"],
                "paths": ["**"],
            }
        ]
    )
    name_status = "A\ta.py\nA\tb.py\nA\tc.py\nA\td.py"
    numstat = "100\t0\ta.py\n100\t0\tb.py\n100\t0\tc.py\n100\t0\td.py"
    report = evaluate_diff(
        name_status=name_status,
        numstat=numstat,
        config=cfg,
        profile_name="business",
        now=date(2026, 10, 10),
    )
    assert report.ok is True
    assert "ex-ok" in report.exemptions_applied


def test_exemption_without_owner_not_applied():
    cfg = _cfg(
        exemptions=[
            {
                "id": "ex-no-owner",
                "reason": "migration",
                "expires": "2099-12-31",
                "gates": ["inflation", "shape"],
                "paths": ["**"],
            }
        ]
    )
    report = evaluate_diff(
        name_status="A\ta.py\nA\tb.py\nA\tc.py\nA\td.py",
        numstat="100\t0\ta.py\n100\t0\tb.py\n100\t0\tc.py\n100\t0\td.py",
        config=cfg,
        profile_name="business",
        now=date(2026, 10, 10),
    )
    assert "ex-no-owner" not in report.exemptions_applied
    assert report.ok is False
    assert any(f.code == "exemption_debt_invalid" for f in report.findings)


def test_expired_exemption_ignored():
    cfg = _cfg(
        exemptions=[
            {
                "id": "ex-old",
                "owner": "platform-oncall",
                "reason": "done",
                "expires": "2020-01-01",
                "gates": ["inflation"],
                "paths": ["**"],
            }
        ]
    )
    report = evaluate_diff(
        name_status="A\ta.py\nA\tb.py\nA\tc.py\nA\td.py",
        numstat="100\t0\ta.py\n100\t0\tb.py\n100\t0\tc.py\n100\t0\td.py",
        config=cfg,
        profile_name="business",
        now=date(2026, 10, 10),
    )
    assert report.ok is False
    assert any(f.code == "exemption_debt_expired" for f in report.findings)


def test_assess_exemption_debt_over_cap_and_expired_block():
    cfg = _cfg(
        max_active_exemptions=1,
        exemptions=[
            {
                "id": "ex-a",
                "owner": "a",
                "reason": "r1",
                "expires": "2099-01-01",
                "gates": ["inflation"],
                "paths": ["**"],
            },
            {
                "id": "ex-b",
                "owner": "b",
                "reason": "r2",
                "expires": "2099-06-01",
                "gates": ["inflation"],
                "paths": ["**"],
            },
            {
                "id": "ex-old",
                "owner": "c",
                "reason": "stale",
                "expires": "2020-01-01",
                "gates": ["inflation"],
                "paths": ["**"],
            },
        ],
    )
    debt = assess_exemption_debt(cfg, now=date(2026, 10, 10))
    assert debt["severity"] == "block"
    assert debt["over_cap"] is True
    assert len(debt["expired"]) == 1
    assert len(debt["active"]) == 1  # capped
    assert debt["active"][0]["id"] == "ex-a"  # soonest expiry kept


def test_collect_diff_stats_counts_classes():
    unified = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@ -0,0 +1,2 @@
+class A:
+    pass
+class B(Exception):
+    pass
"""
    stats = collect_diff_stats(
        name_status="M\tx.py",
        numstat="2\t0\tx.py",
        unified_diff=unified,
    )
    assert stats.new_classes == 2
