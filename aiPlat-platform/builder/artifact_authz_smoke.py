"""P0-3b: Generated App authz / IDOR / SSRF smoke templates + pilot exit gate.

Pilot hard rules (improvement plan §1.2):
  - ≥2 app classes (default: crud, report)
  - ≥3 samples per class
  - each sample authz_smoke status must be pass|fail (never long-lived na)
  - ≥1 negative probe blocked per class
  - exit requires Security Owner approval + all above
  - 60 calendar days without exit → blocked
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# ── App type templates ───────────────────────────────────────────────────────

PILOT_APP_TYPES = ("crud", "report")
MIN_SAMPLES_PER_TYPE = 3
PILOT_MAX_DAYS = 60

# Probe: method, path, headers, body, expect_status (set), kind (positive|negative)
Probe = Dict[str, Any]


def _crud_probes() -> List[Probe]:
    return [
        {
            "id": "authz_no_token",
            "kind": "negative",
            "family": "authz",
            "method": "GET",
            "path": "/api/items",
            "headers": {},
            "expect_status": {401, 403},
        },
        {
            "id": "idor_other_tenant",
            "kind": "negative",
            "family": "idor",
            "method": "GET",
            "path": "/api/items/1",
            "headers": {
                "Authorization": "Bearer tenant-b-token",
                "X-Tenant-Id": "tenant-b",
            },
            "expect_status": {401, 403, 404},
        },
        {
            "id": "ssrf_metadata",
            "kind": "negative",
            "family": "ssrf",
            "method": "POST",
            "path": "/api/fetch",
            "headers": {"Authorization": "Bearer tenant-a-token", "Content-Type": "application/json"},
            "body": {"url": "http://169.254.169.254/latest/meta-data/"},
            "expect_status": {400, 403, 422},
        },
        {
            "id": "authz_health_ok",
            "kind": "positive",
            "family": "authz",
            "method": "GET",
            "path": "/health",
            "headers": {},
            "expect_status": {200, 204},
        },
    ]


def _report_probes() -> List[Probe]:
    return [
        {
            "id": "authz_no_token_report",
            "kind": "negative",
            "family": "authz",
            "method": "GET",
            "path": "/api/reports",
            "headers": {},
            "expect_status": {401, 403},
        },
        {
            "id": "idor_other_org_report",
            "kind": "negative",
            "family": "idor",
            "method": "GET",
            "path": "/api/reports/org-secret",
            "headers": {
                "Authorization": "Bearer other-org",
                "X-Tenant-Id": "org-b",
            },
            "expect_status": {401, 403, 404},
        },
        {
            "id": "ssrf_file_scheme",
            "kind": "negative",
            "family": "ssrf",
            "method": "POST",
            "path": "/api/reports/import",
            "headers": {"Authorization": "Bearer org-a", "Content-Type": "application/json"},
            "body": {"source": "file:///etc/passwd"},
            "expect_status": {400, 403, 422},
        },
        {
            "id": "authz_health_ok",
            "kind": "positive",
            "family": "authz",
            "method": "GET",
            "path": "/health",
            "headers": {},
            "expect_status": {200, 204},
        },
    ]


PROBE_TEMPLATES: Dict[str, List[Probe]] = {
    "crud": _crud_probes(),
    "report": _report_probes(),
}


Transport = Callable[[str, str, Optional[Dict[str, Any]], Dict[str, str]], Tuple[int, str]]


def default_http_transport(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None and "Content-Type" not in (headers or {}):
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), raw
    except Exception as e:
        raise ConnectionError(str(e)) from e


def classify_app_type(root: Path) -> str:
    """Heuristic classifier for pilot templates (crud|report|unknown)."""
    root = Path(root)
    text_bits: List[str] = []
    for pat in ("*.py", "*.ts", "*.tsx", "*.js", "*.json", "*.md"):
        for p in list(root.rglob(pat))[:80]:
            try:
                text_bits.append(p.read_text(encoding="utf-8", errors="ignore")[:4000])
            except OSError:
                continue
    blob = "\n".join(text_bits).lower()
    report_hits = len(re.findall(r"\b(report|dashboard|analytics|报表|图表)\b", blob))
    crud_hits = len(re.findall(r"\b(crud|create|update|delete|/api/items|repository)\b", blob))
    if report_hits >= 2 and report_hits > crud_hits:
        return "report"
    if crud_hits >= 2:
        return "crud"
    # Explicit marker file
    marker = root / "artifact.app_type"
    if marker.is_file():
        t = marker.read_text(encoding="utf-8").strip().lower()
        if t in PROBE_TEMPLATES:
            return t
    return "unknown"


def run_authz_smoke(
    *,
    base_url: str,
    app_type: str,
    transport: Optional[Transport] = None,
    sample_id: str = "",
) -> Dict[str, Any]:
    """Run template probes against a live (or faked) HTTP app.

    Returns authz_smoke-shaped dict: status pass|fail, evidence, probe results.
    Unreachable → fail (not na).
    """
    app_type = (app_type or "").strip().lower()
    if app_type not in PROBE_TEMPLATES:
        return {
            "status": "fail",
            "evidence": f"unsupported_app_type:{app_type or 'empty'}",
            "app_type": app_type or "unknown",
            "sample_id": sample_id,
            "probes": [],
        }
    probes = PROBE_TEMPLATES[app_type]
    xport = transport or default_http_transport
    results: List[Dict[str, Any]] = []
    base = base_url.rstrip("/")
    unreachable = False
    for probe in probes:
        url = f"{base}{probe['path']}"
        try:
            status, body = xport(
                str(probe["method"]),
                url,
                probe.get("body"),
                dict(probe.get("headers") or {}),
            )
            expect = set(probe.get("expect_status") or [])
            ok = status in expect
            results.append(
                {
                    "id": probe["id"],
                    "kind": probe["kind"],
                    "family": probe["family"],
                    "status": status,
                    "ok": ok,
                    "expect": sorted(expect),
                    "body_snip": (body or "")[:120],
                }
            )
        except Exception as e:
            unreachable = True
            results.append(
                {
                    "id": probe["id"],
                    "kind": probe["kind"],
                    "family": probe["family"],
                    "ok": False,
                    "error": str(e)[:200],
                }
            )

    negatives = [r for r in results if r.get("kind") == "negative"]
    negatives_blocked = all(r.get("ok") for r in negatives) and bool(negatives)
    all_ok = all(r.get("ok") for r in results) and not unreachable
    status = "pass" if all_ok and negatives_blocked else "fail"
    return {
        "status": status,
        "evidence": (
            f"app_type={app_type} sample={sample_id or '-'} "
            f"probes={len(results)} negatives_blocked={negatives_blocked} "
            f"unreachable={unreachable}"
        ),
        "app_type": app_type,
        "sample_id": sample_id,
        "probes": results,
        "negatives_blocked": negatives_blocked,
        "tool": "artifact_authz_smoke.run_authz_smoke",
    }


# ── Pilot ledger ─────────────────────────────────────────────────────────────

@dataclass
class PilotSample:
    sample_id: str
    app_type: str
    authz_status: str  # pass|fail
    negatives_blocked: bool
    evidence: str = ""
    recorded_at: str = ""


@dataclass
class PilotState:
    started_at: str
    samples: List[PilotSample] = field(default_factory=list)
    owner_approval: Optional[str] = None  # ISO date or note
    owner_name: str = ""
    status: str = "in_progress"  # in_progress|passed|blocked


def _pilot_path() -> Path:
    override = (os.getenv("AIPLAT_AUTHZ_PILOT_PATH") or "").strip()
    if override:
        return Path(override)
    home = os.getenv("AIPLAT_HOME") or str(Path.home() / ".aiplat")
    return Path(home) / "builder" / "authz_pilot.json"


def load_pilot_state(path: Optional[Path] = None) -> PilotState:
    p = path or _pilot_path()
    if not p.is_file():
        return PilotState(started_at=datetime.now(timezone.utc).date().isoformat())
    raw = json.loads(p.read_text(encoding="utf-8"))
    samples = [
        PilotSample(
            sample_id=str(s.get("sample_id") or ""),
            app_type=str(s.get("app_type") or ""),
            authz_status=str(s.get("authz_status") or "fail"),
            negatives_blocked=bool(s.get("negatives_blocked")),
            evidence=str(s.get("evidence") or ""),
            recorded_at=str(s.get("recorded_at") or ""),
        )
        for s in (raw.get("samples") or [])
        if isinstance(s, dict)
    ]
    return PilotState(
        started_at=str(raw.get("started_at") or datetime.now(timezone.utc).date().isoformat()),
        samples=samples,
        owner_approval=raw.get("owner_approval"),
        owner_name=str(raw.get("owner_name") or ""),
        status=str(raw.get("status") or "in_progress"),
    )


def save_pilot_state(state: PilotState, path: Optional[Path] = None) -> Path:
    p = path or _pilot_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "started_at": state.started_at,
        "samples": [
            {
                "sample_id": s.sample_id,
                "app_type": s.app_type,
                "authz_status": s.authz_status,
                "negatives_blocked": s.negatives_blocked,
                "evidence": s.evidence,
                "recorded_at": s.recorded_at,
            }
            for s in state.samples
        ],
        "owner_approval": state.owner_approval,
        "owner_name": state.owner_name,
        "status": state.status,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def record_pilot_sample(
    smoke: Dict[str, Any],
    *,
    path: Optional[Path] = None,
) -> PilotState:
    state = load_pilot_state(path)
    sid = str(smoke.get("sample_id") or f"sample-{len(state.samples)+1}")
    # replace same sample_id
    state.samples = [s for s in state.samples if s.sample_id != sid]
    state.samples.append(
        PilotSample(
            sample_id=sid,
            app_type=str(smoke.get("app_type") or "unknown"),
            authz_status=str(smoke.get("status") or "fail"),
            negatives_blocked=bool(smoke.get("negatives_blocked")),
            evidence=str(smoke.get("evidence") or ""),
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    state.status = evaluate_pilot_exit(state)["status"]
    save_pilot_state(state, path)
    return state


def evaluate_pilot_exit(state: PilotState, *, today: Optional[date] = None) -> Dict[str, Any]:
    """Hard exit criteria from plan §1.2."""
    today = today or datetime.now(timezone.utc).date()
    try:
        started = date.fromisoformat(state.started_at[:10])
    except ValueError:
        started = today
    age_days = (today - started).days
    timed_out = age_days > PILOT_MAX_DAYS

    by_type: Dict[str, List[PilotSample]] = {t: [] for t in PILOT_APP_TYPES}
    for s in state.samples:
        if s.app_type in by_type:
            by_type[s.app_type].append(s)

    type_ok: Dict[str, bool] = {}
    details: Dict[str, Any] = {}
    for t, samples in by_type.items():
        pass_samples = [s for s in samples if s.authz_status == "pass"]
        unique_pass: Dict[str, PilotSample] = {}
        for s in pass_samples:
            if s.sample_id not in unique_pass:
                unique_pass[s.sample_id] = s
        n_pass = len(unique_pass)
        neg_ok = any(s.negatives_blocked for s in pass_samples)
        ok = n_pass >= MIN_SAMPLES_PER_TYPE and neg_ok
        type_ok[t] = ok
        details[t] = {
            "pass_samples": n_pass,
            "required": MIN_SAMPLES_PER_TYPE,
            "negatives_blocked": neg_ok,
            "ok": ok,
        }

    types_ready = all(type_ok.values())
    owner_ok = bool(state.owner_approval and str(state.owner_approval).strip())
    if timed_out and not (types_ready and owner_ok):
        status = "blocked"
    elif types_ready and owner_ok:
        status = "passed"
    else:
        status = "in_progress"

    return {
        "status": status,
        "age_days": age_days,
        "timed_out": timed_out,
        "types": details,
        "types_ready": types_ready,
        "owner_approval": bool(owner_ok),
        "require_authz_on_publish": status == "passed",
        "message": (
            "pilot passed — authz gate mandatory for crud/report"
            if status == "passed"
            else (
                "pilot blocked — 60d without exit"
                if status == "blocked"
                else "pilot in progress — need 2 types × ≥3 pass + negatives + owner approval"
            )
        ),
    }


def approve_pilot_exit(
    *,
    owner_name: str,
    note: str = "",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    state = load_pilot_state(path)
    state.owner_name = owner_name
    state.owner_approval = (
        f"{datetime.now(timezone.utc).date().isoformat()} {owner_name}: {note}".strip()
    )
    result = evaluate_pilot_exit(state)
    state.status = result["status"]
    save_pilot_state(state, path)
    result["owner_name"] = owner_name
    return result


def authz_required_for_type(app_type: str, path: Optional[Path] = None) -> bool:
    """After pilot exit, crud/report publishes must have authz pass."""
    st = evaluate_pilot_exit(load_pilot_state(path))
    if st.get("status") != "passed":
        return False
    return (app_type or "").strip().lower() in PILOT_APP_TYPES
