"""P0-3a: artifact.security.json — schema, canonical hash, HMAC sign, publish gate.

Honesty locks:
  - authz_smoke may be ``na`` in P0-3a (P0-3b fills pass|fail for pilot types)
  - security_certification is always forced false here
  - unsigned manifests cannot publish when AIPLAT_PROFILE is production/staging
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_log = logging.getLogger(__name__)

MANIFEST_NAME = "artifact.security.json"

# Fields excluded from canonical hash (plan v2.2 §4.2)
_HASH_EXCLUDE = frozenset(
    {
        "manifest_hash",
        "signature",
        "signed_at",
        "reviewer_notes",
        "generated_at",
    }
)

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]

_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".tox",
    "dist",
    "build",
    ".aiplat",
}


def _runtime_profile() -> str:
    raw = (os.getenv("AIPLAT_PROFILE") or os.getenv("AIPLAT_ENV") or "").strip().lower()
    if raw in ("production", "prod"):
        return "production"
    if raw in ("staging", "stage", "preprod"):
        return "staging"
    if raw in ("development", "dev", "local", "test"):
        return "development"
    return raw


def canonical_manifest_bytes(data: Dict[str, Any]) -> bytes:
    """UTF-8 JSON with sorted keys, compact separators; hash-excluded fields stripped."""
    cleaned = {k: v for k, v in data.items() if k not in _HASH_EXCLUDE and not str(k).startswith("_")}
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_manifest_hash(data: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_manifest_bytes(data)).hexdigest()


def _hmac_secret() -> Optional[bytes]:
    raw = (os.getenv("AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET") or "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def sign_manifest_hash(manifest_hash: str) -> str:
    """Sign hash bytes.

    Preference: Ed25519 when key configured (P2-1), else HMAC-SHA256,
    else ``unsigned_dev``.
    """
    try:
        from builder.artifact_sbom_attest import try_ed25519_sign

        ed = try_ed25519_sign(manifest_hash)
        if ed:
            return ed
    except Exception:
        _log.debug("ed25519 sign unavailable; falling back to HMAC", exc_info=True)
    secret = _hmac_secret()
    if not secret:
        return "unsigned_dev"
    dig = hmac.new(secret, f"sha256:{manifest_hash}".encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{dig}"


def verify_manifest_signature(manifest_hash: str, signature: str) -> Tuple[bool, str]:
    sig = (signature or "").strip()
    if not sig or sig == "unsigned_dev":
        return False, "unsigned_or_missing"
    if sig.startswith("ed25519:"):
        try:
            from builder.artifact_sbom_attest import verify_ed25519_signature

            return verify_ed25519_signature(manifest_hash, sig)
        except Exception as e:
            return False, f"ed25519_verify_error:{type(e).__name__}"
    if not sig.startswith("hmac-sha256:"):
        return False, "unsupported_signature_alg"
    secret = _hmac_secret()
    if not secret:
        return False, "no_verify_key"
    expected = sign_manifest_hash(manifest_hash)
    if not hmac.compare_digest(expected, sig):
        return False, "signature_mismatch"
    return True, "ok"


def build_manifest(
    *,
    artifact_id: str,
    artifact_type: str,
    owner: str,
    platform_controls_inherited: Optional[Sequence[str]] = None,
    platform_controls_lost_on_export: Optional[Sequence[str]] = None,
    authz_smoke: Optional[Dict[str, Any]] = None,
    sast: Optional[Dict[str, Any]] = None,
    secrets_scan: Optional[Dict[str, Any]] = None,
    deps_scan: Optional[Dict[str, Any]] = None,
    claim_boundary: str = "不得超出本 manifest 与证据卡",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "type": artifact_type,
        "owner": owner,
        "platform_controls_inherited": list(platform_controls_inherited or []),
        "platform_controls_lost_on_export": list(platform_controls_lost_on_export or []),
        "authz_smoke": authz_smoke
        or {"status": "na", "evidence": "P0-3a: authz deferred to P0-3b"},
        "sast": sast or {"status": "fail", "tool": "unset"},
        "secrets_scan": secrets_scan or {"status": "fail"},
        "deps_scan": deps_scan or {"status": "fail"},
        "claim_boundary": claim_boundary,
        "security_certification": False,
    }
    if extra:
        for k, v in extra.items():
            if k not in _HASH_EXCLUDE:
                data[k] = v
    data["security_certification"] = False  # force
    h = compute_manifest_hash(data)
    data["manifest_hash"] = h
    data["signature"] = sign_manifest_hash(h)
    data["signed_at"] = datetime.now(timezone.utc).isoformat()
    return data


def write_manifest(path: Path, data: Dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_manifest_integrity(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute hash + verify signature. Tampering fails."""
    errors: List[str] = []
    stored_hash = str(data.get("manifest_hash") or "")
    recomputed = compute_manifest_hash(data)
    if not stored_hash:
        errors.append("missing_manifest_hash")
    elif stored_hash != recomputed:
        errors.append("manifest_hash_mismatch")
    sig = str(data.get("signature") or "")
    profile = _runtime_profile()
    prodish = profile in ("production", "staging")
    ok_sig, reason = verify_manifest_signature(recomputed, sig)
    if sig in ("", "unsigned_dev"):
        if prodish:
            errors.append("unsigned_not_allowed_in_prodish")
            ok_sig = False
            reason = "unsigned_not_allowed_in_prodish"
        else:
            ok_sig = True
            reason = "unsigned_dev_allowed_non_prodish"
    elif not ok_sig:
        errors.append(f"signature:{reason}")
    if data.get("security_certification") is True:
        errors.append("security_certification_must_be_false")
    return {
        "ok": not errors,
        "errors": errors,
        "recomputed_hash": recomputed,
        "stored_hash": stored_hash,
        "signature_ok": ok_sig,
        "signature_reason": reason,
        "profile": profile or "(unset)",
    }


def scan_secrets_in_tree(root: Path, *, max_files: int = 500) -> Dict[str, Any]:
    """Lightweight secret echo scan — not a full DLP product."""
    root = Path(root)
    hits: List[str] = []
    scanned = 0
    if not root.exists():
        return {"status": "fail", "detail": "root_missing", "hits": []}
    for p in root.rglob("*"):
        if scanned >= max_files:
            break
        if not p.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in p.parts):
            continue
        if p.suffix.lower() not in {
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".json",
            ".yml",
            ".yaml",
            ".env",
            ".md",
            ".txt",
            ".sh",
        }:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                hits.append(f"{p.relative_to(root)}:{pat.pattern[:40]}")
                break
    return {
        "status": "fail" if hits else "pass",
        "tool": "artifact_security_manifest.scan_secrets_in_tree",
        "scanned_files": scanned,
        "hits": hits[:20],
    }


def scan_deps_presence(root: Path) -> Dict[str, Any]:
    """P0-3a: require a lock/manifest file when code artifacts present; mark pass if none needed."""
    root = Path(root)
    markers = [
        "requirements.txt",
        "requirements.lock",
        "pyproject.toml",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "Cargo.lock",
        "go.sum",
    ]
    found = [m for m in markers if (root / m).exists() or any(root.rglob(m))]
    # If Python/JS sources exist without any lock/manifest → fail
    has_code = any(root.rglob("*.py")) or any(root.rglob("*.ts")) or any(root.rglob("*.js"))
    if has_code and not found:
        return {
            "status": "fail",
            "detail": "code_present_without_dependency_manifest",
            "found": [],
        }
    return {
        "status": "pass",
        "detail": "deps_manifest_present_or_no_code",
        "found": found[:10],
        "tool": "artifact_security_manifest.scan_deps_presence",
    }


def scan_sast_stub(root: Path) -> Dict[str, Any]:
    """P0-3a: prefer bandit if installed; else require explicit external result.

    Does not invent a pass without a tool — missing bandit → status fail with reason.
    """
    root = Path(root)
    try:
        import shutil
        import subprocess

        bandit = shutil.which("bandit")
        if bandit and any(root.rglob("*.py")):
            proc = subprocess.run(
                [bandit, "-q", "-r", str(root), "-f", "json", "-x", ",".join(_SKIP_DIR_NAMES)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            # bandit exit 1 means findings; parse high severity
            high = 0
            try:
                payload = json.loads(proc.stdout or "{}")
                for r in payload.get("results") or []:
                    if str(r.get("issue_severity", "")).lower() == "high":
                        high += 1
            except json.JSONDecodeError:
                high = -1
            if high > 0:
                return {"status": "fail", "tool": "bandit", "high_count": high}
            if high == 0 and proc.returncode in (0, 1):
                return {"status": "pass", "tool": "bandit", "high_count": 0}
            return {"status": "fail", "tool": "bandit", "detail": f"exit={proc.returncode}"}
    except Exception as e:
        return {"status": "fail", "tool": "bandit", "detail": f"{type(e).__name__}:{e}"}
    return {
        "status": "fail",
        "tool": "unset",
        "detail": "bandit_not_available_set_sast_via_ci_or_install_bandit",
    }


def evaluate_publish_gate(
    data: Dict[str, Any],
    *,
    require_authz: bool = False,
    require_sbom: Optional[bool] = None,
) -> Dict[str, Any]:
    """Block publish on integrity / sast / secrets / deps / P2-1 SBOM failures."""
    blockers: List[str] = []
    integrity = validate_manifest_integrity(data)
    if not integrity["ok"]:
        blockers.extend(integrity["errors"])

    for key in ("sast", "secrets_scan", "deps_scan"):
        st = ((data.get(key) or {}) if isinstance(data.get(key), dict) else {}).get("status")
        if st != "pass":
            blockers.append(f"{key}_not_pass:{st}")

    authz = data.get("authz_smoke") if isinstance(data.get("authz_smoke"), dict) else {}
    authz_st = str(authz.get("status") or "na")
    if require_authz and authz_st not in ("pass",):
        blockers.append(f"authz_smoke_required:{authz_st}")
    elif authz_st not in ("pass", "fail", "na"):
        blockers.append(f"authz_smoke_invalid:{authz_st}")

    if data.get("security_certification") is True:
        blockers.append("security_certification_true_forbidden")

    # P2-1: SBOM digest + MCP/plugin allowlist (when required)
    p21_gate: Dict[str, Any] = {"ok": True, "blockers": [], "skipped": True}
    try:
        from builder.artifact_sbom_attest import evaluate_p2_1_gate, p2_1_sbom_required

        req = p2_1_sbom_required() if require_sbom is None else bool(require_sbom)
        sbom = data.get("sbom") if isinstance(data.get("sbom"), dict) else {}
        allow = data.get("mcp_plugin_allowlist") if isinstance(data.get("mcp_plugin_allowlist"), dict) else {}
        p21_gate = evaluate_p2_1_gate(
            sbom_digest_value=str(sbom.get("digest") or ""),
            component_count=int(sbom.get("component_count") or 0),
            allowlist=allow,
            require_sbom=req,
        )
        p21_gate["skipped"] = False
        if not p21_gate.get("ok"):
            blockers.extend(f"p2_1:{b}" for b in (p21_gate.get("blockers") or []))
    except Exception as e:
        # Fail closed when SBOM explicitly required
        try:
            from builder.artifact_sbom_attest import p2_1_sbom_required as _req

            if (require_sbom is True) or (require_sbom is None and _req()):
                blockers.append(f"p2_1_gate_error:{type(e).__name__}")
                p21_gate = {"ok": False, "blockers": [type(e).__name__], "skipped": False}
        except Exception:
            _log.debug("p2_1 require_sbom probe failed after gate error", exc_info=True)

    return {
        "ok": not blockers,
        "blockers": blockers,
        "integrity": integrity,
        "authz_status": authz_st,
        "p2_1": p21_gate,
        "security_certification": False,
    }


def build_and_gate_for_dir(
    root: Path,
    *,
    artifact_id: str,
    artifact_type: str = "app",
    owner: str = "builder",
    require_authz: bool = False,
    write: bool = True,
    authz_base_url: Optional[str] = None,
    authz_sample_id: str = "",
    authz_app_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Scan tree → build signed manifest → evaluate publish gate.

    P0-3b: when ``authz_base_url`` is set (or ``AIPLAT_AUTHZ_SMOKE_URL``), run live
    authz/IDOR/SSRF smoke and record pilot sample. ``require_authz`` forces pass.
    """
    root = Path(root)
    secrets = scan_secrets_in_tree(root)
    deps = scan_deps_presence(root)
    sast = scan_sast_stub(root)
    # If no Python sources, sast N/A → pass with tool none
    if not any(root.rglob("*.py")) and sast.get("tool") == "unset":
        sast = {"status": "pass", "tool": "none", "detail": "no_python_sources"}

    inherited = ["PolicyGate", "ApprovalGate", "AuditLogger"]
    lost: List[str] = []
    if artifact_type == "pi":
        lost = ["PolicyGate", "ApprovalGate", "AuditLogger"]
        inherited = []

    authz_smoke: Dict[str, Any] = {"status": "na", "evidence": "P0-3a skeleton — no smoke URL"}
    app_type_detected = authz_app_type or "unknown"
    try:
        from builder.artifact_authz_smoke import (
            authz_required_for_type,
            classify_app_type,
            record_pilot_sample,
            run_authz_smoke,
        )

        app_type_detected = authz_app_type or classify_app_type(root)
        smoke_url = (authz_base_url or os.getenv("AIPLAT_AUTHZ_SMOKE_URL") or "").strip()
        if smoke_url and app_type_detected in ("crud", "report"):
            authz_smoke = run_authz_smoke(
                base_url=smoke_url,
                app_type=app_type_detected,
                sample_id=authz_sample_id or artifact_id,
            )
            try:
                record_pilot_sample(authz_smoke)
            except Exception:
                _log.warning("authz pilot sample persist failed", exc_info=True)
        elif smoke_url and app_type_detected == "unknown":
            authz_smoke = {
                "status": "fail",
                "evidence": "app_type_unknown_cannot_select_probe_template",
                "app_type": "unknown",
            }
        # After pilot graduation, force require_authz for crud/report
        if not require_authz and authz_required_for_type(app_type_detected):
            require_authz = True
    except Exception as e:
        authz_smoke = {
            "status": "fail" if require_authz else "na",
            "evidence": f"authz_smoke_error:{type(e).__name__}:{e}",
        }

    # P2-1: SBOM + MCP/plugin allowlist attest
    sbom_extra: Dict[str, Any] = {}
    p21_bundle: Dict[str, Any] = {}
    try:
        from builder.artifact_sbom_attest import build_sbom_attest_bundle

        p21_bundle = build_sbom_attest_bundle(
            root, artifact_id=artifact_id, write=write
        )
        sbom_extra = {
            "sbom": {
                "path": p21_bundle.get("sbom_path"),
                "digest": p21_bundle.get("sbom_digest"),
                "component_count": p21_bundle.get("component_count"),
                "format": "CycloneDX-1.5-lite",
            },
            "mcp_plugin_allowlist": p21_bundle.get("allowlist") or {},
        }
    except Exception as e:
        sbom_extra = {
            "sbom": {"digest": "", "component_count": 0, "error": type(e).__name__},
            "mcp_plugin_allowlist": {"ok": False, "detail": type(e).__name__},
        }

    manifest = build_manifest(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        owner=owner,
        platform_controls_inherited=inherited,
        platform_controls_lost_on_export=lost,
        sast=sast,
        secrets_scan={"status": secrets["status"], "tool": secrets.get("tool"), "hits": secrets.get("hits")},
        deps_scan=deps,
        authz_smoke=authz_smoke,
        extra={"app_type": app_type_detected, **sbom_extra},
    )
    out_path = root / MANIFEST_NAME
    if write:
        write_manifest(out_path, manifest)
    gate = evaluate_publish_gate(manifest, require_authz=require_authz)
    return {
        "manifest_path": str(out_path),
        "manifest": manifest,
        "gate": gate,
        "publish_allowed": bool(gate.get("ok")),
        "app_type": app_type_detected,
        "require_authz": require_authz,
        "p2_1": p21_bundle,
    }
