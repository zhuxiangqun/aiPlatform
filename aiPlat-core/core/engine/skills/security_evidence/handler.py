"""Phase C security_evidence handler — mocked behavioral asserts only.

Default OFF. No exploit PoCs. No live SSH / network. Writes regression_evidence JSON.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MAX_FINDINGS = 5


def _artifact(params: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = params.get(key)
    return v if isinstance(v, dict) else {}


def _phase_c_enabled(params: Dict[str, Any]) -> bool:
    if params.get("enabled") is True:
        return True
    env = (os.getenv("AIPLAT_SECURITY_PHASE_C") or "").strip().lower()
    return env in {"1", "true", "yes", "on"}


def _evidence_dir() -> Path:
    try:
        from core.harness.utils.paths import get_aiplat_home

        root = Path(get_aiplat_home())
    except Exception:
        root = Path.home() / ".aiplat"
    d = root / "cache" / "security_evidence"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_evidence(path_id: str, payload: Dict[str, Any]) -> str:
    ts = time.strftime("%Y%m%dT%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in path_id)[:80]
    name = f"regression_evidence_{safe}_{ts}.json"
    try:
        fp = _evidence_dir() / name
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(fp)
    except OSError:
        # Fallback when ~/.aiplat is not writable (CI sandbox, etc.)
        fallback = Path.cwd() / "tmp" / "security_evidence"
        fallback.mkdir(parents=True, exist_ok=True)
        fp = fallback / name
        fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(fp)


def _sink_kind(sink_id: str) -> str:
    parts = str(sink_id or "").split(":")
    return parts[1] if len(parts) >= 2 else ""


def _sink_file(sink_id: str) -> str:
    parts = str(sink_id or "").split(":", 2)
    return parts[2] if len(parts) >= 3 else ""


async def _assert_ssrf_block() -> Dict[str, Any]:
    from core.harness.execution.true_test_runtime import is_blocked_url

    fixtures = [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
    ]
    evidence: List[str] = []
    all_blocked = True
    for url in fixtures:
        blocked, reason = is_blocked_url(url)
        evidence.append(f"{url} -> blocked={blocked} reason={reason}")
        if not blocked:
            all_blocked = False
    return {
        "assert_id": "ssrf_fixture_block",
        "pass": all_blocked,
        "evidence": evidence,
        # Platform SSRF helper works → network_egress finding often mitigated at platform layer
        "disposition_if_pass": "refuted",
        "disposition_if_fail": "confirmed",
        "note": "Fixture URL block via is_blocked_url (no live egress)",
    }


async def _assert_ssh_driver_rejects_dangerous() -> Dict[str, Any]:
    """Behavioral: SSHExecDriver must reject eval/exec before spawning ssh."""
    from core.apps.exec_drivers.ssh import SSHExecDriver

    driver = SSHExecDriver()
    # Ensure host check does not short-circuit before pattern reject
    driver._build_target = lambda: "phasec@invalid.example"  # type: ignore[method-assign]

    spawned = {"called": False}

    async def _no_spawn(*_a, **_k):
        spawned["called"] = True
        raise RuntimeError("subprocess_must_not_be_called")

    import asyncio

    orig = asyncio.create_subprocess_exec
    asyncio.create_subprocess_exec = _no_spawn  # type: ignore[assignment]
    evidence: List[str] = []
    try:
        payloads = ["eval('1')", "exec('x')", "import os\nos.system('id')"]
        rejects = 0
        for code in payloads:
            res = await driver.run_code(language="python", code=code, timeout_s=1.0)
            ok_reject = (
                not res.ok
                and "ssh_exec_driver_rejected_dangerous_pattern" in str(res.error or "")
            )
            evidence.append(f"code={code!r} error={res.error} reject={ok_reject}")
            if ok_reject:
                rejects += 1
        passed = rejects == len(payloads) and not spawned["called"]
        evidence.append(f"subprocess_spawned={spawned['called']}")
        return {
            "assert_id": "ssh_driver_rejects_dangerous_patterns",
            "pass": passed,
            "evidence": evidence,
            # Mitigation present → import-reachability finding is not exploitable via driver API
            "disposition_if_pass": "refuted",
            "disposition_if_fail": "confirmed",
            "note": "Mocked: no real SSH; assert reject-before-spawn",
        }
    finally:
        asyncio.create_subprocess_exec = orig  # type: ignore[assignment]


async def _assert_for_finding(finding: Dict[str, Any]) -> Dict[str, Any]:
    cat = str(finding.get("category") or "")
    sink_id = str(finding.get("sink_id") or "")
    kind = _sink_kind(sink_id)
    sfile = _sink_file(sink_id)

    if cat in ("ssrf",) or kind == "network_egress":
        return await _assert_ssrf_block()
    if kind == "eval_exec" and "exec_drivers/ssh.py" in sfile.replace("\\", "/"):
        return await _assert_ssh_driver_rejects_dangerous()
    if cat == "rce" and "exec_drivers/ssh.py" in sfile.replace("\\", "/"):
        return await _assert_ssh_driver_rejects_dangerous()

    return {
        "assert_id": "unmapped",
        "pass": False,
        "evidence": [f"no Phase C assert mapped for category={cat} kind={kind}"],
        "disposition_if_pass": "inconclusive",
        "disposition_if_fail": "inconclusive",
        "note": "No mapped behavioral assert",
    }


def _disposition(assert_res: Dict[str, Any]) -> str:
    if assert_res.get("assert_id") == "unmapped":
        return "inconclusive"
    if assert_res.get("pass"):
        return str(assert_res.get("disposition_if_pass") or "inconclusive")
    return str(assert_res.get("disposition_if_fail") or "inconclusive")


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    if not _phase_c_enabled(params):
        return {
            "phase": "C",
            "enabled": False,
            "results": [],
            "notes": [
                "Phase C skipped (default OFF). Set enabled=true or AIPLAT_SECURITY_PHASE_C=1"
            ],
        }

    report = _artifact(params, "security_report")
    critique = _artifact(params, "security_critique")
    findings = list(report.get("findings") or critique.get("findings") or [])
    max_n = int(params.get("max_findings") or DEFAULT_MAX_FINDINGS)

    candidates = [
        f
        for f in findings
        if isinstance(f, dict) and str(f.get("severity") or "") == "candidate"
    ][:max_n]

    results: List[Dict[str, Any]] = []
    for f in candidates:
        path_id = str(f.get("path_id") or "")
        assert_res = await _assert_for_finding(f)
        disp = _disposition(assert_res)
        blob = {
            "schema": "regression_evidence.v1",
            "path_id": path_id,
            "prior_severity": "candidate",
            "disposition": disp,
            "assert": assert_res,
            "finding": {
                "sink_id": f.get("sink_id"),
                "entry_id": f.get("entry_id"),
                "category": f.get("category"),
            },
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "physical_evidence": True,
        }
        evidence_path = _write_evidence(path_id or "unknown", blob)
        results.append(
            {
                "path_id": path_id,
                "prior_severity": "candidate",
                "disposition": disp,
                "physical_evidence": True,
                "evidence_path": evidence_path,
                "assert_id": assert_res.get("assert_id"),
                "assert_pass": bool(assert_res.get("pass")),
                "evidence": list(assert_res.get("evidence") or [])[:12],
                "note": assert_res.get("note"),
            }
        )

    return {
        "phase": "C",
        "enabled": True,
        "results": results,
        "counts": {
            "candidates": len(candidates),
            "confirmed": sum(1 for r in results if r["disposition"] == "confirmed"),
            "refuted": sum(1 for r in results if r["disposition"] == "refuted"),
            "inconclusive": sum(1 for r in results if r["disposition"] == "inconclusive"),
        },
        "notes": [
            "Phase C: mocked behavioral asserts only; no exploit PoC; no live SSH/network",
        ],
    }


def merge_evidence_into_report(
    report: Dict[str, Any],
    evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply Phase C dispositions onto a Phase B report (non-destructive copy)."""
    out = dict(report or {})
    header = dict(out.get("header") or {})
    header["phase"] = "C" if evidence.get("enabled") else header.get("phase", "B")
    header["phase_c_enabled"] = bool(evidence.get("enabled"))
    header["phase_c_counts"] = dict(evidence.get("counts") or {})
    by_id = {
        str(r.get("path_id")): r
        for r in (evidence.get("results") or [])
        if isinstance(r, dict)
    }
    findings = []
    for f in out.get("findings") or []:
        if not isinstance(f, dict):
            continue
        row = dict(f)
        ev = by_id.get(str(row.get("path_id") or ""))
        if ev:
            disp = str(ev.get("disposition") or "inconclusive")
            row["phase_c_disposition"] = disp
            row["physical_evidence"] = bool(ev.get("physical_evidence"))
            row["evidence_path"] = ev.get("evidence_path")
            if disp == "confirmed":
                row["severity"] = "confirmed"
            elif disp == "refuted":
                row["severity"] = "refuted"
            # inconclusive keeps candidate
        findings.append(row)
    out["findings"] = findings
    out["refuted"] = list(out.get("refuted") or []) + [
        {
            "path_id": r.get("path_id"),
            "reason": f"phase_c:{r.get('disposition')}",
            "evidence_path": r.get("evidence_path"),
        }
        for r in (evidence.get("results") or [])
        if isinstance(r, dict) and r.get("disposition") == "refuted"
    ]
    out["phase_c"] = {
        "enabled": bool(evidence.get("enabled")),
        "results": evidence.get("results") or [],
        "counts": evidence.get("counts") or {},
    }
    out["header"] = header
    return out
