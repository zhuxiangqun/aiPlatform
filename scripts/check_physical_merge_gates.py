#!/usr/bin/env python3
"""CI / pre-commit entry for physical merge gates (inflation + shape).

Usage:
  python3 scripts/check_physical_merge_gates.py
  python3 scripts/check_physical_merge_gates.py --base origin/main
  python3 scripts/check_physical_merge_gates.py --staged
  python3 scripts/check_physical_merge_gates.py --profile interface_field --mode warn

Exit 1 only when mode=block and findings remain after exemptions.
Warn mode always exits 0 (prints WARN). Off exits 0 silently.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ensure_path() -> None:
    core = str(ROOT / "aiPlat-core")
    if core not in sys.path:
        sys.path.insert(0, core)


def _git(*args: str) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return ""
    return r.stdout


def _resolve_base(base: str) -> str:
    if base:
        return base
    for cand in ("origin/main", "main", "master"):
        chk = subprocess.run(
            ["git", "rev-parse", "--verify", cand],
            cwd=str(ROOT),
            capture_output=True,
        )
        if chk.returncode == 0:
            return cand
    return "HEAD~1"


def main() -> int:
    ap = argparse.ArgumentParser(description="Physical merge gates (inflation + shape)")
    ap.add_argument("--base", default="", help="git base ref (default: origin/main)")
    ap.add_argument("--staged", action="store_true", help="check staged diff only")
    ap.add_argument("--profile", default="", help="force profile (business|framework|interface_field)")
    ap.add_argument("--mode", default="", help="warn|block|off (overrides config/env)")
    ap.add_argument("--json", action="store_true", help="print GateReport JSON")
    args = ap.parse_args()

    if args.mode:
        os.environ["AIPLAT_PHYSICAL_GATES_MODE"] = args.mode.strip().lower()

    _ensure_path()
    from core.harness.meta.physical_merge_gates import DiffStats, evaluate_diff

    if args.staged:
        name_status = _git("diff", "--cached", "--name-status")
        numstat = _git("diff", "--cached", "--numstat")
        unified = _git("diff", "--cached", "-U0")
    else:
        base = _resolve_base(args.base)
        merge_base = _git("merge-base", base, "HEAD").strip() or base
        name_status = _git("diff", "--name-status", f"{merge_base}...HEAD")
        numstat = _git("diff", "--numstat", f"{merge_base}...HEAD")
        unified = _git("diff", "-U0", f"{merge_base}...HEAD")

    report = evaluate_diff(
        name_status=name_status,
        numstat=numstat,
        unified_diff=unified,
        profile_name=args.profile or "",
    )
    # Production caller for DiffStats (method_verify wiring).
    if report.stats is not None and not isinstance(report.stats, DiffStats):
        print("internal error: stats type", type(report.stats), file=sys.stderr)
        return 2

    # P1 testability via CoreFacade (production caller for evaluate_diff_snippets).
    from core.api.core_facade import evaluate_testability_gate

    snippets = dict(report.stats.added_snippets) if report.stats else {}
    t_payload = evaluate_testability_gate(
        snippets=snippets,
        workspace_root=str(ROOT),
    )

    payload = report.to_dict()
    payload["testability"] = t_payload

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        stats = report.stats
        print(
            f"[physical-merge-gates] mode={report.mode} profile={report.profile} "
            f"source={report.config_source} block_after={report.block_after}"
        )
        if stats:
            print(
                f"  stats: files={stats.files_changed} net_lines={stats.net_lines} "
                f"new_deps_files={stats.new_deps_files} new_classes={stats.new_classes} "
                f"new_dirs={len(stats.new_dirs)}"
            )
        if report.exemptions_applied:
            print(f"  exemptions_applied: {', '.join(report.exemptions_applied)}")
        if not report.findings:
            print("  OK — no inflation/shape findings")
        else:
            for f in report.findings:
                loc = f" @ {f.path}" if f.path else ""
                print(f"  {f.severity.upper()} [{f.gate}/{f.code}]{loc}: {f.message}")
            if report.mode == "warn":
                print(
                    "  (warn mode — exit 0; set AIPLAT_PHYSICAL_GATES_MODE=block "
                    f"or wait until block_after={report.block_after} to fail CI)"
                )
        t_mode = str(t_payload.get("mode") or "")
        t_findings = t_payload.get("findings") or []
        print(
            f"[testability-gate] mode={t_mode} "
            f"handlers={len(t_payload.get('handlers_checked') or [])} "
            f"source={t_payload.get('config_source')}"
        )
        if not t_findings:
            print("  OK — no testability findings")
        else:
            for f in t_findings:
                loc = f" @ {f.get('path')}" if f.get("path") else ""
                print(
                    f"  {str(f.get('severity') or 'warn').upper()} "
                    f"[{f.get('code')}]{loc}: {f.get('message')}"
                )
            if t_mode == "warn":
                print(
                    "  (warn mode — exit 0; AIPLAT_TESTABILITY_GATE_MODE=block "
                    f"or block_after={t_payload.get('block_after')})"
                )

    fail = False
    if report.mode == "block" and not report.ok:
        fail = True
    if str(t_payload.get("mode") or "") == "block" and not t_payload.get("ok", True):
        fail = True
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
