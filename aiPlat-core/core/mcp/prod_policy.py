from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def runtime_env() -> str:
    """Runtime environment string for policy gates (dev/staging/prod)."""
    env = (os.environ.get("AIPLAT_ENV") or os.environ.get("APP_ENV") or os.environ.get("ENV") or "dev").strip().lower()
    if env in {"production"}:
        env = "prod"
    return env


def prod_stdio_policy_check(
    *,
    server_name: str,
    transport: str,
    command: str | None,
    args: List[str] | None,
    metadata: Dict[str, Any] | None,
) -> Tuple[bool, str]:
    """
    Policy: allow stdio MCP in prod only when explicitly allowlisted.

    Requirements (all must pass) when AIPLAT_ENV=prod and transport=stdio:
    1) server metadata contains prod_allowed=true
    2) server_name is in AIPLAT_PROD_STDIO_MCP_ALLOWLIST (comma-separated)
    3) command path is absolute and starts with one of AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES
       - prefixes separated by os.pathsep (:) or comma
    4) basic hardening:
       - deny risky interpreter basenames in prod (configurable)
       - command exists and is executable (best-effort)
       - args count/length sanity (avoid abuse)
    5) optional hardening (recommended):
       - force launcher in prod (AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD=true)
    """
    if runtime_env() != "prod":
        return True, ""
    if (transport or "").strip().lower() != "stdio":
        return True, ""

    meta = metadata or {}
    if not bool(meta.get("prod_allowed", False)):
        return False, "metadata.prod_allowed is not true"

    allowlist_raw = os.environ.get("AIPLAT_PROD_STDIO_MCP_ALLOWLIST", "")
    allowlist = {x.strip() for x in allowlist_raw.split(",") if x.strip()}
    if not allowlist or server_name not in allowlist:
        return False, f"server_name '{server_name}' not in AIPLAT_PROD_STDIO_MCP_ALLOWLIST"

    if not command or not str(command).strip():
        return False, "missing stdio command"
    cmd = str(command).strip()
    if not cmd.startswith("/"):
        return False, "stdio command must be an absolute path"

    # optional: force a single controlled launcher in prod
    force_launcher = (os.environ.get("AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    if force_launcher:
        launcher = (os.environ.get("AIPLAT_STDIO_PROD_LAUNCHER") or "").strip()
        if not launcher:
            return False, "AIPLAT_STDIO_FORCE_LAUNCHER_IN_PROD is true but AIPLAT_STDIO_PROD_LAUNCHER is empty"
        if not launcher.startswith("/"):
            return False, "AIPLAT_STDIO_PROD_LAUNCHER must be an absolute path"
        if cmd != launcher:
            return False, "command must equal AIPLAT_STDIO_PROD_LAUNCHER when launcher enforcement is enabled"

    # deny risky basenames (configurable; defaults to common shells)
    deny_raw = os.environ.get("AIPLAT_STDIO_DENY_COMMAND_BASENAMES", "bash,sh,zsh")
    deny = {x.strip().lower() for x in deny_raw.split(",") if x.strip()}
    base = os.path.basename(cmd).lower()
    if base in deny:
        return False, f"command basename '{base}' is denied by policy"

    # command prefix allowlist
    prefixes_raw = os.environ.get("AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES", "")
    parts: List[str] = []
    for chunk in prefixes_raw.split(os.pathsep):
        parts.extend([x.strip() for x in chunk.split(",") if x.strip()])
    prefixes = [p if p.endswith("/") else (p + "/") for p in parts]
    if not prefixes:
        return False, "AIPLAT_STDIO_ALLOWED_COMMAND_PREFIXES is empty"
    if not any(cmd.startswith(p) or cmd == p.rstrip("/") for p in prefixes):
        return False, "command path not in allowed prefixes"

    # best-effort executable check
    if not (os.path.exists(cmd) and os.access(cmd, os.X_OK)):
        return False, "command is not an executable file on this host"

    # args sanity
    a = list(args or [])
    max_args = int(os.environ.get("AIPLAT_STDIO_MAX_ARGS", "32") or 32)
    max_arg_len = int(os.environ.get("AIPLAT_STDIO_MAX_ARG_LENGTH", "512") or 512)
    if len(a) > max_args:
        return False, f"too many args (>{max_args})"
    for one in a:
        s = str(one)
        if "\n" in s or "\r" in s or "\x00" in s:
            return False, "args contain illegal control characters"
        if len(s) > max_arg_len:
            return False, f"arg too long (>{max_arg_len})"

    return True, ""

