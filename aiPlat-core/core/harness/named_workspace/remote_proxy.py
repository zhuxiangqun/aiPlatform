"""Allowlisted proxy to a registered remote aiPlat Core profile."""
from __future__ import annotations

import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 256_000
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_S = 60.0

# Built-in Eval allowlist — registry may tighten, never expand beyond this set.
_BUILTIN_GET = (
    re.compile(r"^/core/workspace/agents(?:\?.*)?$"),
    re.compile(r"^/core/evaluation/sets(?:\?.*)?$"),
    re.compile(r"^/core/evaluation/external-targets(?:\?.*)?$"),
    re.compile(
        r"^/core/evaluation/agents/[^/]+/(?:score|history|attributable-report)(?:\?.*)?$"
    ),
)
_BUILTIN_POST = (
    re.compile(r"^/core/evaluation/exam$"),
    re.compile(r"^/core/evaluation/external-exam$"),
    re.compile(r"^/core/evaluation/external-targets$"),
)

# For registry allowed_routes tightening: method:path_prefix entries like "GET:/core/evaluation"
STRIP_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "transfer-encoding",
        "connection",
        "x-aiplat-workspace-id",
        "authorization",  # browser auth must not leak; server injects its own
    }
)


class RemoteProxyError(Exception):
    def __init__(self, message: str, *, code: str = "remote_proxy_error", http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def normalize_remote_base_url(base_url: str) -> str:
    u = (base_url or "").strip().rstrip("/")
    if not u:
        raise ValueError("base_url required for remote profile")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("remote base_url must be http(s)")
    if not parsed.hostname:
        raise ValueError("remote base_url missing host")
    assert_remote_url_allowed(u)
    return u


def assert_remote_url_allowed(url: str) -> None:
    from core.harness.execution.true_test_runtime import is_blocked_url

    allow_private = os.environ.get("AIPLAT_REMOTE_CORE_ALLOW_PRIVATE", "").strip() in (
        "1",
        "true",
        "TRUE",
        "yes",
    )
    blocked, reason = is_blocked_url(url)
    if blocked and allow_private:
        logger.warning(
            "remote_core_allow_private: would block url reason=%s (audit)",
            reason,
        )
        return
    if blocked:
        raise ValueError(f"ssrf_blocked:{reason}")


def _path_only(path: str) -> str:
    p = (path or "").strip() or "/"
    if not p.startswith("/"):
        p = "/" + p
    # Drop scheme/host if a caller mistakenly passed a full URL
    if "://" in p:
        raise RemoteProxyError("path must be relative", code="remote_path_invalid")
    return p


def is_route_allowlisted(
    method: str,
    path: str,
    *,
    allowed_routes: Optional[List[str]] = None,
) -> bool:
    m = (method or "GET").upper()
    p = _path_only(path)
    # Split query for pattern match on path part; keep query for forwarding
    path_no_q = p.split("?", 1)[0]
    patterns = _BUILTIN_GET if m == "GET" else (_BUILTIN_POST if m == "POST" else ())
    if not patterns:
        return False
    builtin_ok = any(rx.match(p) or rx.match(path_no_q) for rx in patterns)
    if not builtin_ok:
        return False
    # Registry tightening: if provided, path must also match one of the prefixes
    routes = [str(x).strip() for x in (allowed_routes or []) if str(x).strip()]
    if not routes:
        return True
    for spec in routes:
        if ":" in spec:
            sm, sp = spec.split(":", 1)
            if sm.upper() != m:
                continue
            if path_no_q.startswith(sp.strip() or "/"):
                return True
        else:
            if path_no_q.startswith(spec):
                return True
    return False


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect_forbidden:{newurl}", headers, fp
        )


def build_remote_url(base_url: str, path: str) -> str:
    base = normalize_remote_base_url(base_url)
    p = _path_only(path)
    path_part, _, query = p.partition("?")
    url = urljoin(base + "/", path_part.lstrip("/"))
    if query:
        url = f"{url}?{query}"
    bp, up = urlparse(base), urlparse(url)
    if (up.hostname or "").lower() != (bp.hostname or "").lower():
        raise RemoteProxyError("path escapes registered host", code="remote_host_escape")
    if up.scheme != bp.scheme:
        raise RemoteProxyError("scheme mismatch", code="remote_scheme_mismatch")
    assert_remote_url_allowed(url)
    return url


def proxy_request(
    *,
    profile_id: str,
    base_url: str,
    method: str,
    path: str,
    body: bytes = b"",
    content_type: str = "",
    auth_secret_env: str = "",
    allowed_routes: Optional[List[str]] = None,
    tenant_id: str = "",
    actor_id: str = "",
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Forward an allowlisted request to remote Core. Never forwards local workspace header."""
    m = (method or "GET").upper()
    if m not in ("GET", "POST"):
        raise RemoteProxyError(f"method not allowed: {m}", code="remote_method_denied")
    if not is_route_allowlisted(m, path, allowed_routes=allowed_routes):
        raise RemoteProxyError(
            f"route not allowlisted: {m} {path}",
            code="remote_route_denied",
            http_status=403,
        )
    if body and len(body) > MAX_BODY_BYTES:
        raise RemoteProxyError("request body too large", code="remote_body_too_large")

    url = build_remote_url(base_url, path)
    host = urlparse(url).hostname or ""
    logger.info(
        "remote_core_proxy audit profile_id=%s tenant=%s actor=%s method=%s path=%s host=%s",
        profile_id,
        tenant_id or "-",
        actor_id or "-",
        m,
        _path_only(path).split("?", 1)[0],
        host,
    )

    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "aiplat-remote-core-proxy/0.1",
    }
    if content_type:
        headers["Content-Type"] = content_type
    elif m == "POST" and body:
        headers["Content-Type"] = "application/json"
    env_key = (auth_secret_env or "").strip()
    if env_key:
        token = os.environ.get(env_key, "")
        if token:
            headers["Authorization"] = (
                token if token.lower().startswith("bearer ") else f"Bearer {token}"
            )

    data = body if m == "POST" else None
    req = urllib.request.Request(url, data=data, headers=headers, method=m)
    opener = urllib.request.build_opener(NoRedirectHandler)
    try:
        with opener.open(req, timeout=float(timeout_s or DEFAULT_TIMEOUT_S)) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            status = int(getattr(resp, "status", None) or resp.getcode() or 0)
            resp_ct = resp.headers.get("Content-Type") or "application/json"
    except urllib.error.HTTPError as e:
        err_body = b""
        try:
            err_body = e.read(MAX_RESPONSE_BYTES)
        except Exception:
            pass  # noqa: optional-dependency
        return {
            "ok": False,
            "status_code": int(e.code or 502),
            "content_type": e.headers.get("Content-Type") if e.headers else "application/json",
            "body": err_body,
            "url": url,
            "profile_id": profile_id,
        }
    except urllib.error.URLError as e:
        raise RemoteProxyError(
            f"remote_unreachable:{e.reason}",
            code="remote_unreachable",
            http_status=502,
        ) from e

    if len(raw) > MAX_RESPONSE_BYTES:
        raise RemoteProxyError("response too large", code="remote_response_too_large")

    return {
        "ok": status < 400,
        "status_code": status,
        "content_type": resp_ct,
        "body": raw,
        "url": url,
        "profile_id": profile_id,
        # Prove local workspace header was not forwarded
        "stripped_workspace_header": True,
    }
