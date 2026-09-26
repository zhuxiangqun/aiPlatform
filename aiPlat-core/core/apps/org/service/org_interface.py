"""Org Phase C1 / C1.5 — InterfaceSpec (W8): first-class allowlisted IO contract.

Authority (D7): ``AIPLAT_HOME/interfaces/{ref}.yaml`` overrides the workspace
seed yaml. ``connector.json`` → ``live`` is read-only fallback when no yaml
exists. Never write both. Never arbitrary SQL; never plaintext credentials.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_ALLOWED_ADAPTERS = frozenset({"http_json"})
_AUTH_TYPES = frozenset({"bearer_env", "shared_secret_env", "none", ""})
_PLAINTEXT_KEYS = frozenset({"token", "password", "secret", "api_key", "apikey", "key"})


def _as_list(val: Any) -> List[Any]:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def load_live_raw(domain_id: str) -> Dict[str, Any]:
    from core.apps.fde.service.abox_connector import load_connector_config

    cfg = load_connector_config(domain_id)
    live = cfg.get("live") if isinstance(cfg.get("live"), dict) else {}
    return dict(live) if live else {}


def _home_interface_dir() -> Path:
    root = Path(os.getenv("AIPLAT_HOME", str(Path.home() / ".aiplat")))
    return root / "interfaces"


def _seed_interface_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "workspace_seeds" / "interfaces"


def _safe_ref(ref: str) -> str:
    text = (ref or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$", text):
        raise ValueError("interface_ref unsafe")
    if ".." in text or "/" in text or "\\" in text:
        raise ValueError("interface_ref unsafe")
    return text


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(data) if isinstance(data, dict) else {}


def _yaml_for_domain(directory: Path, domain_id: str) -> List[Tuple[Path, Dict[str, Any]]]:
    if not directory.is_dir():
        return []
    hits: List[Tuple[Path, Dict[str, Any]]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = _load_yaml_file(path)
        except Exception:
            logger.warning("skip unreadable interface yaml %s", path, exc_info=True)
            continue
        if str(raw.get("domain_id") or "").strip() == domain_id:
            hits.append((path, raw))
    return hits


def resolve_interface_raw(domain_id: str) -> Tuple[Dict[str, Any], str, str]:
    """YAML wins. connector.live is used only when no yaml exists for the domain."""
    did = (domain_id or "").strip() or "it-ops"
    home = _yaml_for_domain(_home_interface_dir(), did)
    if home:
        path, raw = home[0]
        return raw, "interfaces.yaml", str(path)
    seed = _yaml_for_domain(_seed_interface_dir(), did)
    if seed:
        path, raw = seed[0]
        return raw, "interfaces.yaml", str(path)
    return load_live_raw(did), "connector.live", ""


def materialize_interface_yaml(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Copy the resolved spec into AIPLAT_HOME yaml if missing. Never writes connector.live."""
    did = (domain_id or "").strip() or "it-ops"
    raw, source, _path = resolve_interface_raw(did)
    spec = normalize_interface_spec(did, raw, authority_source=source)
    ref = _safe_ref(str(spec.get("interface_ref") or ""))
    dest = _home_interface_dir() / f"{ref}.yaml"
    if dest.is_file():
        return {
            "status": "exists",
            "wrote": False,
            "path": str(dest),
            "interface_ref": ref,
            "authority_source": "interfaces.yaml",
        }
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = {k: v for k, v in spec.items() if k != "authority_source"}
    import yaml

    dest.write_text(
        yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "status": "written",
        "wrote": True,
        "path": str(dest),
        "interface_ref": ref,
        "copied_from": source,
        "authority_source": "interfaces.yaml",
    }


def normalize_interface_spec(
    domain_id: str,
    live: Optional[Dict[str, Any]] = None,
    *,
    authority_source: str = "connector.live",
) -> Dict[str, Any]:
    """Normalize connector.live into InterfaceSpec shape (C1 field set)."""
    did = (domain_id or "").strip() or "it-ops"
    raw = dict(live) if isinstance(live, dict) else load_live_raw(did)
    ref = str(raw.get("interface_ref") or "").strip()
    if not ref:
        ref = f"{did}.live.default"
    auth = raw.get("auth") if isinstance(raw.get("auth"), dict) else {}
    retry = raw.get("retry") if isinstance(raw.get("retry"), dict) else {}
    rate = raw.get("rate_limit") if isinstance(raw.get("rate_limit"), dict) else {}
    return {
        "interface_ref": ref,
        "domain_id": str(raw.get("domain_id") or did).strip() or did,
        "version": str(raw.get("version") or "0.1.0").strip() or "0.1.0",
        "enabled": bool(raw.get("enabled")),
        "adapter": str(raw.get("adapter") or "").strip().lower(),
        "allowed_hosts": [str(h).strip() for h in _as_list(raw.get("allowed_hosts")) if str(h).strip()],
        "path_template": str(raw.get("path_template") or "/v1/entities/{entity_id}"),
        "base_url_env": str(raw.get("base_url_env") or "AIPLAT_ORG_LIVE_BASE_URL"),
        # inline base_url allowed for tests; production should prefer env
        "base_url": str(raw.get("base_url") or "").strip(),
        "input_schema": raw.get("input_schema") if isinstance(raw.get("input_schema"), dict) else {},
        "output_schema": raw.get("output_schema") if isinstance(raw.get("output_schema"), dict) else {},
        "bound_action_ids": [str(a).strip() for a in _as_list(raw.get("bound_action_ids")) if str(a).strip()],
        "timeout_sec": float(raw.get("timeout_sec") or 5),
        "retry": {
            "max_attempts": int(retry.get("max_attempts") or 0),
            "backoff_sec": float(retry.get("backoff_sec") or 0),
        },
        "rate_limit": {
            "qps": float(rate.get("qps") or 0),
            "burst": int(rate.get("burst") or 0),
        },
        "idempotency_key_path": str(raw.get("idempotency_key_path") or "").strip(),
        "auth": {
            "type": str(auth.get("type") or "none").strip().lower(),
            "env": str(auth.get("env") or "").strip(),
            "header": str(auth.get("header") or "").strip(),
        },
        "tenant_id_path": str(raw.get("tenant_id_path") or "").strip(),
        "audit_fields": [str(x).strip() for x in _as_list(raw.get("audit_fields")) if str(x).strip()],
        "error_codes": raw.get("error_codes") if isinstance(raw.get("error_codes"), dict) else {},
        "authority_source": authority_source
        if authority_source in ("connector.live", "interfaces.yaml")
        else "connector.live",
        "note": str(raw.get("note") or ""),
    }


def _auth_has_plaintext(auth: Dict[str, Any], raw_live: Dict[str, Any]) -> List[str]:
    errs: List[str] = []
    for k, v in (auth or {}).items():
        lk = str(k).lower()
        if lk in _PLAINTEXT_KEYS and str(v or "").strip():
            errs.append(f"auth.{k}: plaintext forbidden; use env ref")
    for k, v in (raw_live or {}).items():
        lk = str(k).lower()
        if lk in _PLAINTEXT_KEYS and str(v or "").strip() and lk != "path_template":
            errs.append(f"live.{k}: plaintext secret forbidden")
    # bearer without env
    at = str(auth.get("type") or "").lower()
    if at in ("bearer_env", "shared_secret_env") and not str(auth.get("env") or "").strip():
        errs.append(f"auth.type={at} requires auth.env")
    if at and at not in _AUTH_TYPES:
        errs.append(f"auth.type unsupported: {at}")
    return errs


def validate_interface_spec(
    spec: Dict[str, Any],
    *,
    raw_live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Hard errors block outbound; warnings are soft (schema completeness)."""
    errors: List[str] = []
    warnings: List[str] = []

    ref = str(spec.get("interface_ref") or "").strip()
    if not ref:
        errors.append("interface_ref required")
    elif not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._:-]{1,127}$", ref):
        errors.append("interface_ref invalid charset/length")

    did = str(spec.get("domain_id") or "").strip()
    if not did:
        errors.append("domain_id required")

    ver = str(spec.get("version") or "").strip()
    if not ver:
        errors.append("version required")

    adapter = str(spec.get("adapter") or "").strip().lower()
    if adapter and adapter not in _ALLOWED_ADAPTERS:
        errors.append(f"adapter must be http_json, got {adapter!r}")
    if not adapter:
        errors.append("adapter required (http_json only)")

    hosts = spec.get("allowed_hosts") or []
    if not isinstance(hosts, list):
        errors.append("allowed_hosts must be list")
        hosts = []

    enabled = bool(spec.get("enabled"))
    if enabled and not hosts:
        errors.append("enabled=true requires non-empty allowed_hosts")

    # declared readiness (for outbound): adapter + hosts
    declared = adapter in _ALLOWED_ADAPTERS and len(hosts) > 0

    auth = spec.get("auth") if isinstance(spec.get("auth"), dict) else {}
    errors.extend(_auth_has_plaintext(auth, raw_live or {}))

    if not isinstance(spec.get("input_schema"), dict) or not spec.get("input_schema"):
        warnings.append("input_schema empty (C1 warn)")
    if not isinstance(spec.get("output_schema"), dict) or not spec.get("output_schema"):
        warnings.append("output_schema empty (C1 warn)")
    if not (spec.get("bound_action_ids") or []):
        warnings.append("bound_action_ids empty (C1 warn)")
    if not (spec.get("audit_fields") or []):
        warnings.append("audit_fields empty (C1 warn)")

    try:
        timeout = float(spec.get("timeout_sec") or 0)
        if timeout <= 0 or timeout > 120:
            errors.append("timeout_sec must be in (0, 120]")
    except (TypeError, ValueError):
        errors.append("timeout_sec invalid")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "declared": declared and ok,
        "enabled": enabled,
        "interface_ref": ref,
        "domain_id": did,
    }


def get_interface_spec(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Load + validate InterfaceSpec. YAML if present, else connector.live read-compat."""
    did = (domain_id or "").strip() or "it-ops"
    raw, source, path = resolve_interface_raw(did)
    spec = normalize_interface_spec(did, raw, authority_source=source)
    validation = validate_interface_spec(spec, raw_live=raw)
    note = (
        "C1.5 InterfaceSpec from interfaces yaml; connector.live not merged"
        if source == "interfaces.yaml"
        else "C1.5 read-compat: connector.live used because no interfaces yaml"
    )
    return {
        "status": "ok" if validation["ok"] else "invalid",
        "spec": spec,
        "validation": validation,
        "authority_source": source,
        "authority_path": path,
        "compat_live": source == "connector.live",
        "authority_note": note + "; no dual-write",
    }


def list_interface_specs(domain_id: str = "") -> Dict[str, Any]:
    """List InterfaceSpecs. Empty domain_id → pilot domains with live blocks."""
    domains: List[str]
    if (domain_id or "").strip():
        domains = [(domain_id or "").strip()]
    else:
        domains = ["it-ops"]
        try:
            from core.apps.fde.service.abox_connector import _workspace_connector_seed
            import json

            # data-gov thin slice if seed has live
            for did in ("data-gov",):
                p = _workspace_connector_seed(did)
                if p.is_file():
                    data = json.loads(p.read_text(encoding="utf-8") or "{}")
                    if isinstance(data.get("live"), dict):
                        domains.append(did)
        except Exception:
            logger.debug("list_interface_specs seed scan failed", exc_info=True)

    for directory in (_home_interface_dir(), _seed_interface_dir()):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            try:
                raw = _load_yaml_file(path)
            except Exception:
                continue
            extra = str(raw.get("domain_id") or "").strip()
            if extra and extra not in domains:
                domains.append(extra)
    items = [get_interface_spec(d) for d in domains]
    sources = {str((item.get("spec") or {}).get("authority_source") or "") for item in items}
    return {
        "status": "ok",
        "count": len(items),
        "items": items,
        "authority_source": next(iter(sources)) if len(sources) == 1 else "mixed",
    }


def assert_action_bound(domain_id: str, action_id: str) -> Dict[str, Any]:
    """Whether action_id is allowed to use domain Interface (bound_action_ids).

    Empty whitelist → deny when interface enabled (fail-closed for live);
    when disabled, return unbound_ok for sandbox paths.
    """
    did = (domain_id or "").strip() or "it-ops"
    aid = (action_id or "").strip()
    pack = get_interface_spec(did)
    spec = pack.get("spec") or {}
    bounds = list(spec.get("bound_action_ids") or [])
    enabled = bool(spec.get("enabled"))
    if not aid:
        return {
            "allowed": False,
            "status": "need_action_id",
            "interface_ref": spec.get("interface_ref"),
        }
    if not bounds:
        # C1: empty list warns; live enabled → deny action-bound outbound
        return {
            "allowed": not enabled,
            "status": "no_bindings" if enabled else "unbound_sandbox_ok",
            "interface_ref": spec.get("interface_ref"),
            "bound_action_ids": bounds,
            "authority_note": "empty bound_action_ids: deny when enabled; sandbox ok when disabled",
        }
    allowed = aid in bounds
    return {
        "allowed": allowed,
        "status": "ok" if allowed else "action_not_bound",
        "interface_ref": spec.get("interface_ref"),
        "action_id": aid,
        "bound_action_ids": bounds,
    }


def interface_ready_for_outbound(domain_id: str = "it-ops") -> Tuple[bool, Dict[str, Any]]:
    """Hard gate used by live_io_gates: valid spec + declared + enabled."""
    pack = get_interface_spec(domain_id)
    val = pack.get("validation") or {}
    ready = bool(val.get("ok")) and bool(val.get("declared")) and bool(val.get("enabled"))
    return ready, pack
