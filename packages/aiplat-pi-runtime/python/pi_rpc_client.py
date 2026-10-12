"""Minimal Pi JSONL RPC client (factory-in experiment, way 4).

Does **not** implement PolicyGate. Callers must authorize the working
directory and wrap any production use with aiPlat gates + sandbox.

Protocol: https://github.com/earendil-works/pi (docs/rpc.md)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


class PiRpcError(RuntimeError):
    pass


@dataclass
class PiRpcResult:
    ok: bool
    text: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    elapsed_ms: int = 0
    model: str = ""
    cwd: str = ""


def resolve_pi_bin() -> str:
    env = (os.environ.get("AIPLAT_PI_BIN") or "").strip()
    if env and os.path.isfile(env):
        return env
    found = shutil.which("pi")
    if not found:
        raise PiRpcError("pi CLI not found (set AIPLAT_PI_BIN or install @earendil-works/pi-coding-agent)")
    return found


class PiRpcSession:
    """Long-lived `pi --mode rpc` subprocess with JSONL framing."""

    def __init__(
        self,
        *,
        cwd: str,
        model: str = "",
        extra_args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.cwd = os.path.abspath(cwd)
        self.model = (model or os.environ.get("AIPLAT_PI_MODEL") or "").strip()
        self._extra = list(extra_args or [])
        self._env = {**os.environ, **(env or {})}
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._proc is not None:
            return
        cmd = [resolve_pi_bin(), "--mode", "rpc", "--no-session"]
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.extend(self._extra)
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
            env=self._env,
        )

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
        self._proc = None

    def __enter__(self) -> "PiRpcSession":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _write(self, obj: Dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n"
        self._proc.stdin.write(raw)
        self._proc.stdin.flush()

    def _readlines(self) -> Iterator[Dict[str, Any]]:
        assert self._proc and self._proc.stdout
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise PiRpcError("pi RPC stdout closed unexpectedly")
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise PiRpcError(f"bad JSONL from pi: {e}: {line[:200]!r}") from e

    def command(self, payload: Dict[str, Any], *, timeout_s: float = 30.0) -> Dict[str, Any]:
        """Send one command and wait for its `response` (by id)."""
        self.start()
        req_id = str(payload.get("id") or uuid.uuid4())
        body = {**payload, "id": req_id}
        self._write(body)
        deadline = time.monotonic() + timeout_s
        for rec in self._readlines():
            if time.monotonic() > deadline:
                raise PiRpcError(f"timeout waiting for response id={req_id}")
            if rec.get("type") == "response" and rec.get("id") == req_id:
                if not rec.get("success"):
                    raise PiRpcError(str(rec.get("error") or rec))
                return rec
        raise PiRpcError("no response")

    def prompt_and_wait(
        self,
        message: str,
        *,
        timeout_s: float = 180.0,
        collect_events: bool = True,
    ) -> PiRpcResult:
        """prompt → wait until agent_settled (or handled with no run)."""
        t0 = time.monotonic()
        events: List[Dict[str, Any]] = []
        text_parts: List[str] = []
        self.start()
        req_id = f"prompt-{uuid.uuid4().hex[:8]}"
        self._write({"id": req_id, "type": "prompt", "message": message})
        deadline = time.monotonic() + timeout_s
        disposition = ""
        saw_response = False

        for rec in self._readlines():
            if time.monotonic() > deadline:
                return PiRpcResult(
                    ok=False,
                    text="".join(text_parts),
                    events=events,
                    error=f"timeout after {timeout_s}s",
                    elapsed_ms=int((time.monotonic() - t0) * 1000),
                    model=self.model,
                    cwd=self.cwd,
                )
            if collect_events:
                events.append(rec)
            rtype = rec.get("type")
            if rtype == "response" and rec.get("id") == req_id:
                saw_response = True
                if not rec.get("success"):
                    return PiRpcResult(
                        ok=False,
                        error=str(rec.get("error") or "prompt rejected"),
                        events=events,
                        elapsed_ms=int((time.monotonic() - t0) * 1000),
                        model=self.model,
                        cwd=self.cwd,
                    )
                data = rec.get("data") if isinstance(rec.get("data"), dict) else {}
                disposition = str(data.get("disposition") or "")
                if disposition == "handled":
                    break
                continue
            if rtype == "message_update":
                ev = rec.get("assistantMessageEvent") or {}
                if ev.get("type") == "text_delta":
                    text_parts.append(str(ev.get("delta") or ""))
            if rtype == "agent_settled" and saw_response:
                break

        return PiRpcResult(
            ok=True,
            text="".join(text_parts),
            events=events,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            model=self.model,
            cwd=self.cwd,
        )


def assert_sandbox_cwd(cwd: str) -> str:
    """Refuse host workspace unless AIPLAT_PI_CODING_ALLOW_HOST=1.

    Production must run under an isolated cwd (temp dir / container mount).
    """
    abs_cwd = os.path.abspath(cwd)
    if os.environ.get("AIPLAT_PI_CODING_ALLOW_HOST", "").strip() == "1":
        return abs_cwd
    allow_prefixes = []
    tmp = os.environ.get("TMPDIR") or "/tmp"
    allow_prefixes.append(os.path.abspath(tmp))
    allow_prefixes.append("/tmp")
    allow_prefixes.append("/var/tmp")
    # Explicit experiment sandbox root
    root = (os.environ.get("AIPLAT_PI_CODING_SANDBOX_ROOT") or "").strip()
    if root:
        allow_prefixes.append(os.path.abspath(root))
    for p in allow_prefixes:
        try:
            if abs_cwd == p or abs_cwd.startswith(p.rstrip("/") + "/"):
                return abs_cwd
        except Exception:
            continue
    raise PiRpcError(
        "cwd not under sandbox; set AIPLAT_PI_CODING_SANDBOX_ROOT or "
        "AIPLAT_PI_CODING_ALLOW_HOST=1 (dev only). cwd=" + abs_cwd
    )
