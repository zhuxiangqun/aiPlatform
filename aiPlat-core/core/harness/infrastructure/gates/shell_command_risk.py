"""Shell command risk analysis — OpenWorker-inspired escalation heuristics.

Even when a tool is allowlisted by *prefix* (e.g. ``find``), opaque constructs,
arg-executors, and dangerous finder flags must still escalate to a hard floor.
The analyser only *classifies*; ApprovalGate decides allow / ask / deny.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

# Constructs whose *contents* we cannot evaluate → never prefix-auto-run.
_OPAQUE_CONSTRUCTS: Tuple[str, ...] = ("`", "$(", "${", ">", "<", "|")

# Separators that chain several commands — each segment checked independently.
_SEPARATORS: Tuple[str, ...] = ("&&", "||", ";", "|&", "|", "&", "\n", "\r")

# Outer programs that run *another* program named in args — prefix never vouches.
_ARG_EXECUTORS = frozenset(
    {
        "xargs",
        "env",
        "nohup",
        "nice",
        "stdbuf",
        "timeout",
        "watch",
        "sudo",
        "doas",
        "ssh",
        "docker",
        "podman",
        "kubectl",
        "npx",
        "pnpx",
        "bunx",
        "uvx",
    }
)

_INLINE_CODE_FLAGS = frozenset(
    {"-c", "-e", "--eval", "--command", "-Command", "-EncodedCommand"}
)
_INTERPRETERS = frozenset(
    {
        "sh",
        "bash",
        "zsh",
        "dash",
        "ksh",
        "fish",
        "powershell",
        "pwsh",
        "cmd",
        "python",
        "python3",
        "node",
        "deno",
        "bun",
        "ruby",
        "perl",
        "php",
    }
)

# find/locate family flags that turn list into exec/delete/write.
_DANGEROUS_FLAGS = frozenset(
    {
        "-exec",
        "-execdir",
        "-delete",
        "-ok",
        "-okdir",
        "-fprintf",
        "-fprint",
        "-fprint0",
        "-fls",
    }
)

_SHELL_TOOL_NAMES = frozenset({"shell_exec", "code_execution", "process", "bash", "shell"})


@dataclass(frozen=True)
class ShellRiskReport:
    forces_hard_floor: bool
    reasons: List[str] = field(default_factory=list)
    segments: List[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.reasons:
            return ""
        return "; ".join(self.reasons)


def extract_command_text(tool_args: Optional[dict]) -> str:
    """Pull a command/script string from common tool arg shapes."""
    if not isinstance(tool_args, dict):
        return ""
    for key in ("command", "cmd", "script", "code", "shell", "argv"):
        val = tool_args.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, (list, tuple)) and val:
            return " ".join(str(x) for x in val)
    return ""


def split_command_segments(command: str) -> List[str]:
    """Split on shell separators (longest first). Quoted separators are *not*
    respected — deliberate over-split toward caution (OpenWorker parity)."""
    text = str(command or "").strip()
    if not text:
        return []
    segs = [text]
    for sep in sorted(_SEPARATORS, key=len, reverse=True):
        next_segs: List[str] = []
        for part in segs:
            pieces = part.split(sep)
            next_segs.extend(p.strip() for p in pieces if p and p.strip())
        segs = next_segs or segs
    return segs


def _tokens(segment: str) -> List[str]:
    # Lightweight tokenize — shlex can fail on unbalanced quotes; fall back to split.
    try:
        import shlex

        return [t for t in shlex.split(segment, posix=True) if t]
    except ValueError:
        return segment.split()


def analyze_shell_command(command: str) -> ShellRiskReport:
    """Return whether *command* must escalate past any prefix allowlist."""
    text = str(command or "").strip()
    if not text:
        return ShellRiskReport(forces_hard_floor=False)

    reasons: List[str] = []
    # Whole-string opaque constructs (redirection / substitution / pipe).
    for token in _OPAQUE_CONSTRUCTS:
        if token in text:
            reasons.append(f"opaque construct {token!r}")
            break

    segments = split_command_segments(text)
    for seg in segments:
        toks = _tokens(seg)
        if not toks:
            continue
        prog = toks[0].rsplit("/", 1)[-1].lower()
        if prog in _ARG_EXECUTORS:
            reasons.append(f"arg-executor {prog!r}")
        if prog in _INTERPRETERS:
            for t in toks[1:]:
                if t in _INLINE_CODE_FLAGS:
                    reasons.append(f"inline code via {prog} {t}")
                    break
        for t in toks[1:]:
            if t in _DANGEROUS_FLAGS or t.lower() in _DANGEROUS_FLAGS:
                reasons.append(f"dangerous flag {t}")
                break

    # Deduplicate while preserving order.
    seen = set()
    uniq: List[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            uniq.append(r)

    return ShellRiskReport(
        forces_hard_floor=bool(uniq),
        reasons=uniq,
        segments=segments,
    )


def shell_tool_needs_command_check(tool_name: str) -> bool:
    name = str(tool_name or "").strip().lower()
    return name in _SHELL_TOOL_NAMES or name.endswith("_shell")


def evaluate_tool_shell_risk(
    tool_name: str,
    tool_args: Optional[dict] = None,
) -> Optional[ShellRiskReport]:
    """If tool carries a shell/code command that escalates, return the report."""
    if not shell_tool_needs_command_check(tool_name):
        return None
    cmd = extract_command_text(tool_args)
    if not cmd:
        return None
    report = analyze_shell_command(cmd)
    return report if report.forces_hard_floor else None
