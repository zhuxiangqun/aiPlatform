"""HttpChatPullAdapter — POST chat-style external agents for eval (pull mode)."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.apps.eval.service.external_targets import (
    MAX_TIMEOUT_MS,
    build_invoke_url,
    resolve_auth_header,
)

logger = logging.getLogger(__name__)

SCHEMA_V0 = "aiplat.external_eval.chat_pull.v0"
SCHEMA_V1 = "aiplat.external_eval.chat_pull.v1"
SCHEMA = SCHEMA_V1
MAX_BODY_BYTES = 256_000
MAX_RESPONSE_BYTES = 512_000


class HttpChatPullAdapter:
    """Invoke a registered http_chat_pull target; return text + optional tool names."""

    def invoke(
        self,
        target: Dict[str, Any],
        *,
        user_input: str,
        task_id: str = "",
        set_id: str = "",
    ) -> Dict[str, Any]:
        url = build_invoke_url(
            str(target.get("base_url") or ""),
            str(target.get("path") or "/v1/chat"),
        )
        timeout_ms = int(target.get("timeout_ms") or 30_000)
        timeout_ms = max(1, min(timeout_ms, MAX_TIMEOUT_MS))
        timeout_s = timeout_ms / 1000.0
        mode = str(target.get("response_mode") or "aiplat_v0")
        tid = str(target.get("target_id") or "")

        payload = {
            "schema": SCHEMA_V1,
            "task_id": task_id,
            "user_input": user_input,
            "metadata": {
                "set_id": set_id,
                "agent_target_id": tid,
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            raise ValueError("request body too large")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/plain",
            "User-Agent": "aiplat-external-eval/0.1",
        }
        auth = resolve_auth_header(target)
        if auth:
            headers[auth[0]] = auth[1]

        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
        opener = urllib.request.build_opener(NoRedirectHandler)
        try:
            with opener.open(req, timeout=timeout_s) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
                content_type = (resp.headers.get("Content-Type") or "").lower()
                status = getattr(resp, "status", None) or resp.getcode()
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read(2000).decode("utf-8", errors="replace")
            except Exception:
                pass  # noqa: optional-dependency
            raise RuntimeError(f"external_http_{e.code}:{err_body[:200]}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"external_url_error:{e.reason}") from e

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("response too large")
        if int(status or 0) >= 400:
            raise RuntimeError(f"external_http_{status}")

        text, traj, schema_out = _extract_response(raw, content_type=content_type, mode=mode)
        return {
            "schema": schema_out,
            "output_text": text,
            "trajectory": traj,
            "tool_names": list((traj or {}).get("tool_names") or []),
            "http_status": int(status or 0),
            "url": url,
        }


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(
            req.full_url, code, f"redirect_forbidden:{newurl}", headers, fp
        )


def parse_trajectory_tool_names(trajectory: Any) -> List[str]:
    """Extract ordered tool names; malformed → empty + warning (lenient)."""
    if trajectory is None:
        return []
    if not isinstance(trajectory, dict):
        logger.warning("external_eval trajectory ignored: not an object")
        return []
    calls = trajectory.get("tool_calls")
    if calls is None:
        return []
    if not isinstance(calls, list):
        logger.warning("external_eval trajectory.tool_calls ignored: not a list")
        return []
    names: List[str] = []
    for item in calls:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
            continue
        if isinstance(item, dict):
            n = str(item.get("name") or "").strip()
            if n:
                names.append(n)
            continue
        logger.warning("external_eval trajectory tool_call entry ignored: %r", type(item))
    return names


def tool_names_to_syscall_events(names: List[str]) -> List[Dict[str, Any]]:
    """Synthetic events for EvalMetricsEngine.compute_trajectory_quality."""
    return [{"kind": "tool", "name": n, "event_type": "tool_call"} for n in names if n]


def _extract_response(
    raw: bytes,
    *,
    content_type: str,
    mode: str,
) -> tuple:
    """Return (output_text, trajectory_dict|None, schema)."""
    if mode == "plain_text" or (
        "text/plain" in content_type and "json" not in content_type
    ):
        return raw.decode("utf-8", errors="replace").strip(), None, SCHEMA_V0

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        if mode == "openai_chat":
            raise ValueError("expected JSON openai_chat response")
        return raw.decode("utf-8", errors="replace").strip(), None, SCHEMA_V0

    if not isinstance(data, dict):
        raise ValueError("response JSON must be object")

    schema_out = str(data.get("schema") or SCHEMA_V0).strip() or SCHEMA_V0
    traj_raw = data.get("trajectory")
    names = parse_trajectory_tool_names(traj_raw)
    traj: Optional[Dict[str, Any]] = None
    if names or (isinstance(traj_raw, dict) and traj_raw.get("tool_calls") is not None):
        traj = {"tool_calls": [{"name": n} for n in names], "tool_names": names}
        if not schema_out.endswith(".v1"):
            schema_out = SCHEMA_V1

    if mode == "openai_chat":
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict) and msg.get("content") is not None:
                return str(msg.get("content") or "").strip(), traj, schema_out
        raise ValueError("openai_chat missing choices[0].message.content")

    if data.get("output_text") is not None:
        return str(data.get("output_text") or "").strip(), traj, schema_out
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict) and msg.get("content") is not None:
            return str(msg.get("content") or "").strip(), traj, schema_out
    if data.get("text") is not None:
        return str(data.get("text") or "").strip(), traj, schema_out
    raise ValueError("response missing output_text")


def probe_target(target: Dict[str, Any]) -> Dict[str, Any]:
    """Dry connectivity check: POST a tiny probe (may 4xx — still proves reachability)."""
    adapter = HttpChatPullAdapter()
    try:
        out = adapter.invoke(
            target,
            user_input="__aiplat_external_eval_probe__",
            task_id="probe",
            set_id="",
        )
        return {
            "ok": True,
            "reachable": True,
            "sample_len": len(out.get("output_text") or ""),
            "url": out.get("url"),
        }
    except Exception as e:
        logger.debug("external target probe failed", exc_info=True)
        return {
            "ok": False,
            "reachable": False,
            "error": str(e)[:300],
        }
