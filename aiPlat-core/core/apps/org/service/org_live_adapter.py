"""Org L5 W7 / Phase C1 — gated live HTTP JSON adapter (no arbitrary SQL).

Config lives in connector.json ``live`` block (= InterfaceSpec single source, D7).
Requires dual unlock (env + signed doc) before any outbound call.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def live_config(domain_id: str) -> Dict[str, Any]:
    from core.apps.org.service.org_interface import resolve_interface_raw

    raw, _source, _path = resolve_interface_raw(domain_id)
    return raw


def adapter_declared(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Whether connector declares a valid InterfaceSpec (http_json + hosts)."""
    from core.apps.org.service.org_interface import get_interface_spec

    pack = get_interface_spec(domain_id)
    spec = pack.get("spec") or {}
    val = pack.get("validation") or {}
    return {
        "domain_id": domain_id,
        "interface_ref": spec.get("interface_ref"),
        "declared": bool(val.get("declared")),
        "enabled_flag": bool(spec.get("enabled")),
        "adapter": spec.get("adapter") or None,
        "allowed_hosts": list(spec.get("allowed_hosts") or []),
        "base_url_env": str(spec.get("base_url_env") or "AIPLAT_ORG_LIVE_BASE_URL"),
        "validation_ok": bool(val.get("ok")),
        "validation_errors": list(val.get("errors") or []),
        "validation_warnings": list(val.get("warnings") or []),
        "authority_note": (
            "InterfaceSpec yaml if present, else connector.live read-compat; "
            "http_json whitelist only; never arbitrary SQL; no dual-write"
        ),
    }


def _resolve_base_url(live: Dict[str, Any]) -> str:
    env_name = str(live.get("base_url_env") or "AIPLAT_ORG_LIVE_BASE_URL")
    inline = str(live.get("base_url") or "").strip()
    from_env = (os.getenv(env_name) or "").strip()
    return from_env or inline


def _host_allowed(hostname: str, allowed: List[str]) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    for raw in allowed:
        rule = str(raw or "").strip().lower().rstrip(".")
        if not rule:
            continue
        if rule.startswith("*."):
            suffix = rule[1:]  # .example.com
            if host.endswith(suffix) or host == rule[2:]:
                return True
        elif host == rule:
            return True
    return False


def _url_allowed(url: str, allowed_hosts: List[str]) -> Tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "url_parse_error"
    if parsed.scheme not in ("http", "https"):
        return False, "scheme_not_http"
    host = (parsed.hostname or "").strip().lower()
    if not _host_allowed(host, allowed_hosts):
        return False, "host_not_allowlisted"
    if host in ("169.254.169.254", "metadata.google.internal"):
        return False, "metadata_blocked"
    return True, "ok"


def live_io_gates(domain_id: str = "it-ops") -> Dict[str, Any]:
    """Compute whether live HTTP path may run (unlock + InterfaceSpec + base URL)."""
    from core.apps.org.service.org_field_ops import evaluate_live_unlock
    from core.apps.org.service.org_interface import get_interface_spec

    intent = evaluate_live_unlock()
    pack = get_interface_spec(domain_id)
    spec = pack.get("spec") or {}
    val = pack.get("validation") or {}
    decl = adapter_declared(domain_id)
    base = _resolve_base_url(spec)
    url_ok = False
    url_reason = "no_base_url"
    hosts = list(spec.get("allowed_hosts") or [])
    if base:
        url_ok, url_reason = _url_allowed(
            base if "://" in base else f"https://{base}",
            hosts,
        )
        if not url_ok and "://" not in base:
            url_ok = _host_allowed(base, hosts)
            url_reason = "ok" if url_ok else "host_not_allowlisted"

    enabled = bool(spec.get("enabled"))
    can_call = (
        intent.get("status") == "acknowledged"
        and bool(val.get("ok"))
        and bool(val.get("declared"))
        and enabled
        and bool(base)
        and url_ok
    )
    return {
        "domain_id": domain_id,
        "interface_ref": spec.get("interface_ref"),
        "intent": intent,
        "adapter": decl,
        "validation": {"ok": val.get("ok"), "errors": val.get("errors"), "warnings": val.get("warnings")},
        "base_url_present": bool(base),
        "base_url_ok": url_ok,
        "base_url_reason": url_reason,
        "live_io_enabled": bool(can_call),
        "status": "ready" if can_call else "blocked",
        "authority_note": (
            "live_io_enabled requires: UNLOCK_STATUS signed + AIPLAT_ORG_IO_LIVE_UNLOCK "
            "+ valid InterfaceSpec + enabled + http_json allowlist + base URL; "
            "still not an M4 claim; writes remain dual-gated dry-run; no arbitrary SQL"
        ),
    }


def fetch_live_http(
    domain_id: str,
    entity_id: str,
    *,
    purpose: str = "org_live",
    action_id: str = "",
) -> Dict[str, Any]:
    """GET JSON from allowlisted customer sandbox / staging HTTP endpoint."""
    from core.apps.org.service.org_interface import assert_action_bound, get_interface_spec

    did = (domain_id or "").strip() or "it-ops"
    eid = (entity_id or "").strip()
    gates = live_io_gates(did)
    if not gates.get("live_io_enabled"):
        return {
            "status": "live_blocked",
            "domain_id": did,
            "entity_id": eid,
            "interface_ref": gates.get("interface_ref"),
            "gates": gates,
            "authority_note": gates.get("authority_note"),
        }

    if action_id:
        bound = assert_action_bound(did, action_id)
        if not bound.get("allowed"):
            return {
                "status": "action_not_bound",
                "domain_id": did,
                "entity_id": eid,
                "action_id": action_id,
                "interface_ref": bound.get("interface_ref"),
                "authority_note": "Action must be listed in InterfaceSpec.bound_action_ids",
            }

    pack = get_interface_spec(did)
    live = pack.get("spec") or {}
    base = _resolve_base_url(live).rstrip("/")
    path_tmpl = str(live.get("path_template") or "/v1/entities/{entity_id}")
    path = path_tmpl.replace("{entity_id}", eid).replace("{domain_id}", did)
    if not path.startswith("/"):
        path = "/" + path
    url = base + path if "://" in base else f"https://{base}{path}"

    ok, reason = _url_allowed(url, list(live.get("allowed_hosts") or []))
    if not ok:
        return {
            "status": "url_rejected",
            "domain_id": did,
            "entity_id": eid,
            "interface_ref": live.get("interface_ref"),
            "reason": reason,
            "authority_note": "SSRF guard: host must be on InterfaceSpec.allowed_hosts",
        }

    headers = {"Accept": "application/json", "User-Agent": "aiPlat-org-live-adapter/1.0"}
    auth = live.get("auth") if isinstance(live.get("auth"), dict) else {}
    if str(auth.get("type") or "") == "bearer_env":
        tok = (os.getenv(str(auth.get("env") or "AIPLAT_ORG_LIVE_TOKEN")) or "").strip()
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

    timeout = float(live.get("timeout_sec") or 5)
    try:
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — host allowlisted above
            raw = resp.read(512 * 1024)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            status_code = getattr(resp, "status", None) or resp.getcode()
        body: Any
        try:
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            body = {"raw_text": raw.decode("utf-8", errors="replace")[:2000]}
        # soft schema presence (C1 warn path — do not fail fetch)
        out_schema = live.get("output_schema") or {}
        schema_note = "output_schema present" if out_schema else "output_schema empty (warn)"
        return {
            "status": "ok",
            "domain_id": did,
            "entity_id": eid,
            "purpose": purpose,
            "interface_ref": live.get("interface_ref"),
            "mode": "live_http",
            "sandbox_tier": "customer_http",
            "http": {
                "url_host": urlparse(url).hostname,
                "status_code": status_code,
                "content_type": ctype,
            },
            "payload": body if isinstance(body, dict) else {"value": body},
            "schema_note": schema_note,
            "authority_note": (
                "live http_json via InterfaceSpec; allowlisted host only; "
                "not arbitrary SQL; M4 claim still requires human field sign-off"
            ),
        }
    except HTTPError as e:
        logger.warning("org live http HTTPError", exc_info=True)
        return {
            "status": "http_error",
            "domain_id": did,
            "entity_id": eid,
            "interface_ref": live.get("interface_ref"),
            "http_status": e.code,
            "error": type(e).__name__,
        }
    except (URLError, socket.timeout, TimeoutError, OSError) as e:
        logger.warning("org live http transport error", exc_info=True)
        return {
            "status": "transport_error",
            "domain_id": did,
            "entity_id": eid,
            "interface_ref": live.get("interface_ref"),
            "error": type(e).__name__,
            "detail": str(e)[:200],
        }
    except Exception as e:
        logger.warning("org live http unexpected", exc_info=True)
        return {
            "status": "error",
            "domain_id": did,
            "entity_id": eid,
            "interface_ref": live.get("interface_ref"),
            "error": type(e).__name__,
        }
