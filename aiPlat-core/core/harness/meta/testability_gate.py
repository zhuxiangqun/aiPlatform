"""Testability gate (P1) — pure I/O unit tests required for core handlers.

Merge-time + done_verify. Integration-only tests do **not** count as complete.
Runtime entry fail-fast remains separate (frameworks/templates).

Config: AIPLAT_TESTABILITY_GATE_MODE=off|warn|block (default warn until
block_after in YAML; done_verify uses require_testability overlay).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

# I/O that makes a test "not pure" (DB / network / broker / container).
_IMPURE_RES: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bsqlite3\s*\.\s*connect\b",
        r"\bpsycopg2?\b",
        r"\basyncpg\b",
        r"\bpymongo\b",
        r"\bmotor\b",
        r"\bcreate_engine\s*\(",
        r"\bredis\s*\.\s*(?:Redis|from_url)\b",
        r"\baioredis\b",
        r"\brequests\s*\.\s*(?:get|post|put|delete|patch|request)\b",
        r"\bhttpx\s*\.\s*(?:get|post|put|delete|patch|request|Client|AsyncClient)\b",
        r"\baiohttp\b",
        r"\burllib\.request\b",
        r"\bboto3\b",
        r"\bcelery\b",
        r"\bkafka\b",
        r"\bpika\b",
        r"\bdocker\s*\.\s*from_env\b",
        r"\bplaywright\b",
        r"\bselenium\b",
    )
)
_INTEGRATION_MARK = re.compile(
    r"pytest\.mark\.integration|@pytest\.mark\.integration",
    re.IGNORECASE,
)
_ASSERT_RE = re.compile(r"\bassert\b|self\.assert\w+\s*\(")
_HANDLER_STEMS = frozenset({"handler.py", "handlers.py"})
_LOGIC_DEF = re.compile(
    r"^\s*(?:async\s+)?def\s+(?:execute|handle|run|main)\s*\(|"
    r"^\s*class\s+\w*(?:Handler|Service|Executor)\b",
    re.MULTILINE,
)


@dataclass
class TestabilityFinding:
    code: str
    message: str
    path: str = ""
    severity: str = "warn"  # warn | block


@dataclass
class TestabilityReport:
    ok: bool
    mode: str
    findings: List[TestabilityFinding] = field(default_factory=list)
    handlers_checked: List[str] = field(default_factory=list)
    config_source: str = ""
    block_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "config_source": self.config_source,
            "block_after": self.block_after,
            "handlers_checked": list(self.handlers_checked),
            "findings": [
                {
                    "code": f.code,
                    "message": f.message,
                    "path": f.path,
                    "severity": f.severity,
                }
                for f in self.findings
            ],
        }


def _default_seed() -> Path:
    # meta → harness → core → aiPlat-core
    return (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "org"
        / "testability_gate.yaml"
    )


def load_testability_config(override: Optional[Mapping[str, Any]] = None) -> Tuple[Dict[str, Any], str]:
    if isinstance(override, Mapping) and override:
        return dict(override), "override"

    env_path = (os.getenv("AIPLAT_TESTABILITY_GATES_CONFIG") or "").strip()
    candidates: List[Tuple[Path, str]] = []
    if env_path:
        candidates.append((Path(env_path), "AIPLAT_TESTABILITY_GATES_CONFIG"))
    home = (os.getenv("AIPLAT_HOME") or "").strip()
    if home:
        candidates.append((Path(home) / "org" / "testability_gate.yaml", "$AIPLAT_HOME/org"))
    candidates.append((_default_seed(), "workspace_seed"))

    for path, src in candidates:
        if not path.is_file() or yaml is None:
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(data, dict):
                return data, src
        except Exception:
            continue
    return _default_config(), "builtin_defaults"


def _default_config() -> Dict[str, Any]:
    return {
        "mode": "warn",
        "block_after": "2026-11-15",
        "handler_basenames": ["handler.py", "handlers.py"],
        "require_assert": True,
    }


def resolve_mode(cfg: Mapping[str, Any], *, now: Optional[date] = None) -> str:
    env = (os.getenv("AIPLAT_TESTABILITY_GATE_MODE") or "").strip().lower()
    if env in ("off", "warn", "block"):
        base = env
    else:
        base = str(cfg.get("mode") or "warn").strip().lower()
        if base not in ("off", "warn", "block"):
            base = "warn"
    if base == "off":
        return "off"
    ba = str(cfg.get("block_after") or "").strip()
    if not ba or base == "block":
        return base
    try:
        cutoff = date.fromisoformat(ba[:10])
    except ValueError:
        return base
    today = now or datetime.now(timezone.utc).date()
    if today >= cutoff and base == "warn":
        return "block"
    return base


def is_impure_test(content: str) -> bool:
    text = str(content or "")
    return any(rx.search(text) for rx in _IMPURE_RES)


def is_integration_marked(content: str) -> bool:
    return bool(_INTEGRATION_MARK.search(str(content or "")))


def has_assertion(content: str) -> bool:
    return bool(_ASSERT_RE.search(str(content or "")))


def _norm_path(p: str) -> str:
    return str(p or "").replace("\\", "/").lstrip("./")


def _is_test_path(path: str) -> bool:
    p = _norm_path(path)
    name = Path(p).name
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    parts = p.split("/")
    return "tests" in parts or "test" in parts


def _is_handler_path(path: str, basenames: Sequence[str]) -> bool:
    p = _norm_path(path)
    if _is_test_path(p):
        return False
    name = Path(p).name.lower()
    want = {str(b).lower() for b in basenames} or set(_HANDLER_STEMS)
    return name in want


def _looks_like_logic(content: str) -> bool:
    return bool(_LOGIC_DEF.search(str(content or "")))


def _stem_key(path: str) -> str:
    return Path(_norm_path(path)).stem.lower()


def _test_covers_handler(test_path: str, test_content: str, handler_path: str) -> bool:
    hp = _norm_path(handler_path)
    stem = Path(hp).stem
    parent = Path(hp).parent.name
    text = str(test_content or "")
    # Import / path / name references (content + test filename)
    needles = [
        stem,
        parent,
        hp.replace("/", ".").rstrip(".py"),
        f"/{stem}",
        f"import {stem}",
        f"from {stem}",
    ]
    hay = f"{_norm_path(test_path)}\n{text}".lower()
    return any(n and n.lower() in hay for n in needles if n)


def collect_files_from_context(context: Mapping[str, Any]) -> Dict[str, str]:
    """Gather path→content from done_verify / pipeline context."""
    out: Dict[str, str] = {}
    ctx = context if isinstance(context, Mapping) else {}

    for key in ("_written_files", "written_files", "_sandbox_files", "files"):
        raw = ctx.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, Mapping):
                    p = _norm_path(str(item.get("path") or item.get("name") or ""))
                    c = item.get("content")
                    if p and isinstance(c, str):
                        out[p] = c
                elif isinstance(item, str) and item.strip():
                    # path-only; try read from cwd
                    out.setdefault(_norm_path(item), "")
        elif isinstance(raw, Mapping):
            for k, v in raw.items():
                if isinstance(v, str):
                    out[_norm_path(str(k))] = v

    # Artifact dicts commonly nest files=
    for key in ("output", "artifact", "last_artifact"):
        art = ctx.get(key)
        if isinstance(art, str) and art.strip().startswith("{"):
            try:
                import json

                art = json.loads(art)
            except Exception:
                art = None
        if isinstance(art, Mapping):
            fl = art.get("files")
            if isinstance(fl, list):
                for item in fl:
                    if isinstance(item, Mapping):
                        p = _norm_path(str(item.get("path") or item.get("name") or ""))
                        c = item.get("content")
                        if p and isinstance(c, str):
                            out[p] = c

    # Fill empty content from disk when cwd known
    cwd = Path(str(ctx.get("cwd") or ctx.get("workdir") or "") or ".")
    for p, c in list(out.items()):
        if c:
            continue
        fp = cwd / p
        if fp.is_file():
            try:
                out[p] = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:  # noqa: best-effort read of optional cwd file
                continue
    return out


def evaluate_files(
    files: Mapping[str, str],
    *,
    config: Optional[Mapping[str, Any]] = None,
    mode_override: str = "",
) -> TestabilityReport:
    """Evaluate path→content map for handler pure-test coverage."""
    cfg, source = load_testability_config(override=config)
    mode = (mode_override or "").strip().lower()
    if mode not in ("off", "warn", "block"):
        mode = resolve_mode(cfg)
    if mode == "off":
        return TestabilityReport(ok=True, mode="off", config_source=source)

    basenames = [
        str(x).strip()
        for x in (cfg.get("handler_basenames") or list(_HANDLER_STEMS))
        if str(x).strip()
    ]
    require_assert = bool(cfg.get("require_assert", True))
    sev = "block" if mode == "block" else "warn"

    handlers: List[Tuple[str, str]] = []
    tests: List[Tuple[str, str]] = []
    for path, content in (files or {}).items():
        p = _norm_path(path)
        c = str(content or "")
        if _is_test_path(p):
            tests.append((p, c))
        elif _is_handler_path(p, basenames):
            # Basename handler.py is always in-scope when present in the file set.
            handlers.append((p, c))

    findings: List[TestabilityFinding] = []
    checked: List[str] = []

    for hp, hc in handlers:
        checked.append(hp)
        if hc.strip() and not _looks_like_logic(hc) and "def " not in hc:
            # Empty / stub handler — still require a test once non-trivial
            if len(hc.strip()) < 40:
                continue

        covering_pure = False
        covering_integration_only = False
        for tp, tc in tests:
            if not _test_covers_handler(tp, tc, hp):
                continue
            impure = is_impure_test(tc)
            integ = is_integration_marked(tc)
            if impure or integ:
                covering_integration_only = True
                continue
            if require_assert and not has_assertion(tc):
                findings.append(
                    TestabilityFinding(
                        code="testability_no_assert",
                        message=f"unit test for {hp} has no assert (not completion)",
                        path=tp,
                        severity=sev,
                    )
                )
                continue
            covering_pure = True
            break

        if covering_pure:
            continue
        if covering_integration_only:
            findings.append(
                TestabilityFinding(
                    code="testability_integration_only",
                    message=(
                        f"handler {hp} only covered by integration/impure tests — "
                        "pure unit test required (ms-assertable, no DB/network/broker)"
                    ),
                    path=hp,
                    severity=sev,
                )
            )
        else:
            findings.append(
                TestabilityFinding(
                    code="testability_missing_pure_test",
                    message=(
                        f"handler {hp} lacks a pure unit test — "
                        "add test_*.py with asserts, no DB/network/message queue"
                    ),
                    path=hp,
                    severity=sev,
                )
            )

    # Standalone impure unit tests claiming to be unit (not marked integration)
    for tp, tc in tests:
        if is_impure_test(tc) and not is_integration_marked(tc):
            findings.append(
                TestabilityFinding(
                    code="testability_impure_unmarked",
                    message=(
                        f"{tp} uses DB/network/broker but is not marked "
                        "@pytest.mark.integration — mark it or purify"
                    ),
                    path=tp,
                    severity=sev,
                )
            )

    ok = True
    if mode == "block" and findings:
        ok = False
    return TestabilityReport(
        ok=ok,
        mode=mode,
        findings=findings,
        handlers_checked=checked,
        config_source=source,
        block_after=str(cfg.get("block_after") or ""),
    )


def enrich_files_from_workspace(
    files: Mapping[str, str],
    root: Path,
    *,
    basenames: Optional[Sequence[str]] = None,
) -> Dict[str, str]:
    """Merge-time: pull existing pure tests from disk so handler edits aren't false-positives.

    Only loads test_*.py / *_test.py under the same package tree or ``**/tests/**``
    that reference the handler stem/parent name (bounded walk).
    """
    out: Dict[str, str] = {_norm_path(k): str(v or "") for k, v in (files or {}).items()}
    root = Path(root)
    if not root.is_dir():
        return out
    names = list(basenames) if basenames else list(_HANDLER_STEMS)
    handlers = [p for p in out if _is_handler_path(p, names)]
    if not handlers:
        return out

    # Collect candidate test files once (cap walk).
    candidates: List[Path] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip heavy / irrelevant trees
            base = Path(dirpath).name
            if base in (".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"):
                dirnames[:] = []
                continue
            rel_parts = Path(dirpath).relative_to(root).parts
            if any(x in (".git", "node_modules", ".venv") for x in rel_parts):
                continue
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                if fn.startswith("test_") or fn.endswith("_test.py"):
                    candidates.append(Path(dirpath) / fn)
            if len(candidates) > 4000:
                break
    except OSError:  # noqa: best-effort workspace walk
        return out

    for hp in handlers:
        stem = Path(hp).stem.lower()
        parent = Path(hp).parent.name.lower()
        for tp in candidates:
            try:
                rel = str(tp.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            if rel in out and out[rel]:
                continue
            name_l = tp.name.lower()
            # Filename hint: stem/parent/handler; otherwise skip (content import checked elsewhere)
            if stem not in name_l and parent not in name_l and "handler" not in name_l:
                continue
            try:
                text = tp.read_text(encoding="utf-8", errors="replace")
            except OSError:  # noqa: unreadable test file
                continue
            if _test_covers_handler(rel, text, hp):
                out[rel] = text
    return out


def evaluate_diff_snippets(
    added_snippets: Mapping[str, str],
    *,
    config: Optional[Mapping[str, Any]] = None,
    mode_override: str = "",
    workspace_root: Optional[Path] = None,
) -> TestabilityReport:
    """Merge-time helper: snippets from physical_merge_gates DiffStats (+ disk tests)."""
    files = dict(added_snippets or {})
    if workspace_root is not None:
        cfg, _ = load_testability_config(override=config)
        basenames = [
            str(x).strip()
            for x in (cfg.get("handler_basenames") or list(_HANDLER_STEMS))
            if str(x).strip()
        ]
        files = enrich_files_from_workspace(files, Path(workspace_root), basenames=basenames)
    return evaluate_files(
        files,
        config=config,
        mode_override=mode_override,
    )


def veto_reason_from_report(report: TestabilityReport) -> Optional[str]:
    """For done_verify: return veto string when mode=block and findings exist."""
    if report.mode == "off":
        return None
    if not report.findings:
        return None
    if report.mode != "block":
        return None  # warn: surface via report only
    top = report.findings[0]
    return f"done_verify: testability {top.code}: {top.message}"[:240]
