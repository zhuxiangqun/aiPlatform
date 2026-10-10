"""Physical merge gates (P0) — inflation + shape vetoes on git diffs.

Merge-time only (CI / pre-commit). Runtime entry fail-fast stays in
frameworks/templates — do not conflate with PolicyGate.

Config load order matches duty_board:
  AIPLAT_PHYSICAL_GATES_CONFIG → $AIPLAT_HOME/org/physical_merge_gates.yaml → seed.
"""

from __future__ import annotations

import ast
import fnmatch
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

_CLASS_DEF_RE = re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(([^)]*)\))?\s*:")
_DEP_FILE_NAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "package.json",
    "Pipfile",
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


@dataclass
class GateFinding:
    gate: str  # inflation | shape
    code: str
    message: str
    path: str = ""
    severity: str = "warn"  # warn | block


@dataclass
class DiffStats:
    files_changed: int = 0
    files_added: int = 0
    net_lines: int = 0
    insertions: int = 0
    deletions: int = 0
    new_deps_files: int = 0
    new_classes: int = 0
    new_dirs: List[str] = field(default_factory=list)
    paths: List[str] = field(default_factory=list)
    added_paths: List[str] = field(default_factory=list)
    # path → full text of newly added file (status A) or concatenated +lines for M
    added_snippets: Dict[str, str] = field(default_factory=dict)


@dataclass
class GateReport:
    ok: bool
    mode: str
    profile: str
    findings: List[GateFinding] = field(default_factory=list)
    stats: Optional[DiffStats] = None
    exemptions_applied: List[str] = field(default_factory=list)
    config_source: str = ""
    block_after: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "profile": self.profile,
            "config_source": self.config_source,
            "block_after": self.block_after,
            "exemptions_applied": list(self.exemptions_applied),
            "stats": {
                "files_changed": self.stats.files_changed if self.stats else 0,
                "files_added": self.stats.files_added if self.stats else 0,
                "net_lines": self.stats.net_lines if self.stats else 0,
                "insertions": self.stats.insertions if self.stats else 0,
                "deletions": self.stats.deletions if self.stats else 0,
                "new_deps_files": self.stats.new_deps_files if self.stats else 0,
                "new_classes": self.stats.new_classes if self.stats else 0,
                "new_dirs": list(self.stats.new_dirs) if self.stats else [],
            },
            "findings": [
                {
                    "gate": f.gate,
                    "code": f.code,
                    "message": f.message,
                    "path": f.path,
                    "severity": f.severity,
                }
                for f in self.findings
            ],
        }


def _default_seed() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "workspace_seeds"
        / "org"
        / "physical_merge_gates.yaml"
    )


def load_physical_gates_config(
    override: Optional[Mapping[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Return (config_dict, source_label)."""
    if override is not None:
        return dict(override), "override"

    env_path = (os.environ.get("AIPLAT_PHYSICAL_GATES_CONFIG") or "").strip()
    candidates: List[Tuple[Path, str]] = []
    if env_path:
        candidates.append((Path(env_path), "AIPLAT_PHYSICAL_GATES_CONFIG"))
    home = (os.environ.get("AIPLAT_HOME") or "").strip()
    if home:
        candidates.append(
            (Path(home) / "org" / "physical_merge_gates.yaml", "$AIPLAT_HOME/org")
        )
    candidates.append((_default_seed(), "workspace_seed"))

    if yaml is None:
        return _builtin_fallback(), "builtin_no_yaml"

    for path, label in candidates:
        try:
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    return data, f"{label}:{path}"
        except Exception:
            # Unreadable/invalid YAML candidate — try next path.
            continue  # noqa: intentional skip bad config file
    return _builtin_fallback(), "builtin_fallback"


def _builtin_fallback() -> Dict[str, Any]:
    return {
        "version": 1,
        "mode": "warn",
        "block_after": "2026-11-01",
        "profiles": {
            "business": {
                "max_files": 8,
                "max_net_lines": 200,
                "max_new_deps": 0,
                "max_new_classes": 3,
                "max_new_dirs": 2,
                "max_inherit_bases": 1,
            },
            "framework": {
                "max_files": 40,
                "max_net_lines": 800,
                "max_new_deps": 2,
                "max_new_classes": 15,
                "max_new_dirs": 5,
                "max_inherit_bases": 2,
            },
        },
        "framework_globs": ["**/tests/**", "scripts/**"],
        "banned_path_segments": ["/generic/", "/framework/"],
        "banned_new_basenames": ["event_bus.py", "observer.py", "scheduler.py"],
        "banned_class_substrings": ["EventBus", "ObserverTree"],
        "allowed_bases": ["object", "Exception", "ABC", "Protocol", "BaseModel"],
        "exemptions": [],
    }


def _match_glob(path: str, pattern: str) -> bool:
    p = path.replace("\\", "/")
    pat = pattern.replace("\\", "/")
    if "**" in pat:
        # fnmatch does not treat ** as recursive; approximate
        rx = (
            re.escape(pat)
            .replace(r"\*\*", ".*")
            .replace(r"\*", "[^/]*")
            .replace(r"\?", ".")
        )
        return re.search(f"^{rx}$", p) is not None or fnmatch.fnmatch(p, pat)
    return fnmatch.fnmatch(p, pat)


def select_profile(paths: Sequence[str], config: Mapping[str, Any], forced: str = "") -> str:
    if forced:
        return forced
    globs = list(config.get("framework_globs") or [])
    if paths and globs and all(
        any(_match_glob(p, g) for g in globs) for p in paths
    ):
        return "framework"
    return "business"


def resolve_mode(config: Mapping[str, Any], now: Optional[date] = None) -> str:
    env = (os.environ.get("AIPLAT_PHYSICAL_GATES_MODE") or "").strip().lower()
    if env in ("warn", "block", "off"):
        return env
    mode = str(config.get("mode") or "warn").strip().lower()
    if mode not in ("warn", "block", "off"):
        mode = "warn"
    block_after = str(config.get("block_after") or "").strip()
    if mode == "warn" and block_after:
        try:
            ba = date.fromisoformat(block_after[:10])
            today = now or datetime.now(timezone.utc).date()
            if today >= ba:
                return "block"
        except ValueError:
            # Invalid block_after date → keep configured warn/block mode.
            return mode
    return mode


def _parse_name_status(name_status: str) -> Tuple[List[str], List[str], List[str]]:
    """Return (all_paths, added_paths, new_dirs)."""
    all_paths: List[str] = []
    added: List[str] = []
    new_dirs: List[str] = []
    seen_dirs: set = set()
    for line in (name_status or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        # renames: R100\told\tnew
        if status.startswith("R") and len(parts) >= 3:
            path = parts[-1]
        path = path.strip()
        if not path:
            continue
        all_paths.append(path)
        if status.startswith("A"):
            added.append(path)
            parent = str(Path(path).parent).replace("\\", "/")
            if parent and parent not in (".", "") and parent not in seen_dirs:
                # only count dir if this is the first file under a brand-new path segment
                # heuristic: directory of an added file counts as new_dir candidate
                seen_dirs.add(parent)
                new_dirs.append(parent)
    return all_paths, added, new_dirs


def _parse_numstat(numstat: str) -> Tuple[int, int, int]:
    ins = dels = 0
    files = 0
    for line in (numstat or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, b = parts[0], parts[1]
        if a == "-" or b == "-":
            # binary
            files += 1
            continue
        try:
            ins += int(a)
            dels += int(b)
            files += 1
        except ValueError:
            continue
    return files, ins, dels


def _extract_plus_snippets(unified_diff: str) -> Dict[str, str]:
    """Map path → concatenated added source lines (no + prefix)."""
    out: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []
    for line in (unified_diff or "").splitlines():
        if line.startswith("diff --git "):
            if current is not None:
                out[current] = "\n".join(buf)
            buf = []
            current = None
            continue
        if line.startswith("+++ b/"):
            current = line[6:].strip()
            if current == "/dev/null":
                current = None
            continue
        if current is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            buf.append(line[1:])
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def _count_new_classes(snippets: Mapping[str, str]) -> int:
    n = 0
    for text in snippets.values():
        for line in text.splitlines():
            if _CLASS_DEF_RE.match(line):
                n += 1
    return n


def collect_diff_stats(
    *,
    name_status: str = "",
    numstat: str = "",
    unified_diff: str = "",
) -> DiffStats:
    paths, added, new_dirs = _parse_name_status(name_status)
    n_files, ins, dels = _parse_numstat(numstat)
    snippets = _extract_plus_snippets(unified_diff)
    dep_hits = 0
    for p in paths:
        base = Path(p).name
        if base in _DEP_FILE_NAMES or base.startswith("requirements"):
            # count only if file has net additions
            sn = snippets.get(p, "")
            if sn.strip() or p in added:
                dep_hits += 1
    return DiffStats(
        files_changed=n_files or len(paths),
        files_added=len(added),
        net_lines=ins - dels,
        insertions=ins,
        deletions=dels,
        new_deps_files=dep_hits,
        new_classes=_count_new_classes(snippets),
        new_dirs=new_dirs,
        paths=paths,
        added_paths=added,
        added_snippets=snippets,
    )


def _active_exemptions(
    config: Mapping[str, Any],
    now: Optional[date] = None,
) -> List[Dict[str, Any]]:
    today = now or datetime.now(timezone.utc).date()
    out: List[Dict[str, Any]] = []
    for raw in config.get("exemptions") or []:
        if not isinstance(raw, dict):
            continue
        exp = str(raw.get("expires") or "").strip()
        if not exp:
            continue  # no expiry → reject (must not be a silent backdoor)
        try:
            if date.fromisoformat(exp[:10]) < today:
                continue
        except ValueError:
            continue
        if not str(raw.get("reason") or "").strip():
            continue
        out.append(raw)
    return out


def _exempted(
    finding: GateFinding,
    exemptions: Sequence[Mapping[str, Any]],
    applied: List[str],
) -> bool:
    for ex in exemptions:
        gates = ex.get("gates") or ["inflation", "shape"]
        if finding.gate not in gates:
            continue
        paths = ex.get("paths") or ["**"]
        path = finding.path or ""
        if path and not any(_match_glob(path, str(g)) for g in paths):
            # path-scoped exemption: finding without path matches only if paths is **
            if not any(str(g) in ("**", "*") for g in paths):
                continue
        elif not path and not any(str(g) in ("**", "*") for g in paths):
            continue
        eid = str(ex.get("id") or ex.get("reason") or "exemption")
        if eid not in applied:
            applied.append(eid)
        return True
    return False


def check_inflation(
    stats: DiffStats,
    profile: Mapping[str, Any],
) -> List[GateFinding]:
    findings: List[GateFinding] = []
    checks = [
        ("max_files", stats.files_changed, "files_changed", "inflation_files"),
        ("max_net_lines", stats.net_lines, "net_lines", "inflation_net_lines"),
        ("max_new_deps", stats.new_deps_files, "new_deps_files", "inflation_new_deps"),
        ("max_new_classes", stats.new_classes, "new_classes", "inflation_new_classes"),
        ("max_new_dirs", len(stats.new_dirs), "new_dirs", "inflation_new_dirs"),
    ]
    for key, value, label, code in checks:
        limit = profile.get(key)
        if limit is None:
            continue
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            continue
        if value > lim:
            findings.append(
                GateFinding(
                    gate="inflation",
                    code=code,
                    message=f"{label}={value} exceeds {key}={lim}",
                    severity="block",
                )
            )
    return findings


def _basename_banned(name: str, patterns: Sequence[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name.lower(), pat.lower()):
            return True
    return False


def check_shape(
    stats: DiffStats,
    config: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> List[GateFinding]:
    findings: List[GateFinding] = []
    segments = [str(s) for s in (config.get("banned_path_segments") or [])]
    ban_bases = [str(s) for s in (config.get("banned_new_basenames") or [])]
    ban_cls = [str(s) for s in (config.get("banned_class_substrings") or [])]
    allowed = {str(x) for x in (config.get("allowed_bases") or [])}
    try:
        max_bases = int(profile.get("max_inherit_bases", 1))
    except (TypeError, ValueError):
        max_bases = 1

    for path in stats.added_paths:
        norm = "/" + path.replace("\\", "/").lstrip("/")
        for seg in segments:
            if seg in norm:
                findings.append(
                    GateFinding(
                        gate="shape",
                        code="shape_banned_path",
                        message=f"new path contains banned segment {seg!r}",
                        path=path,
                        severity="block",
                    )
                )
        base = Path(path).name
        if _basename_banned(base, ban_bases):
            findings.append(
                GateFinding(
                    gate="shape",
                    code="shape_banned_basename",
                    message=f"new file basename banned: {base}",
                    path=path,
                    severity="block",
                )
            )

    for path, text in (stats.added_snippets or {}).items():
        if not path.endswith(".py"):
            continue
        for line in text.splitlines():
            m = _CLASS_DEF_RE.match(line)
            if not m:
                continue
            cname = m.group(1)
            for sub in ban_cls:
                if sub and sub in cname:
                    findings.append(
                        GateFinding(
                            gate="shape",
                            code="shape_banned_class",
                            message=f"banned class name pattern {sub!r}: {cname}",
                            path=path,
                            severity="block",
                        )
                    )
            bases_raw = (m.group(2) or "").strip()
            if not bases_raw:
                continue
            # strip generics Foo[Bar] → Foo for counting
            base_names = []
            for part in bases_raw.split(","):
                part = part.strip()
                if not part:
                    continue
                name = part.split("[", 1)[0].split(".", 1)[-1].strip()
                if name and name not in allowed:
                    base_names.append(name)
            if len(base_names) > max_bases:
                findings.append(
                    GateFinding(
                        gate="shape",
                        code="shape_deep_inherit",
                        message=(
                            f"class {cname} adds {len(base_names)} non-allowed bases "
                            f"{base_names} (max_inherit_bases={max_bases})"
                        ),
                        path=path,
                        severity="block",
                    )
                )

        # AST pass on new files for nested inheritance signals
        if path in stats.added_paths and text.strip():
            findings.extend(_ast_shape_findings(path, text, allowed, max_bases, ban_cls))

    return findings


def _ast_shape_findings(
    path: str,
    text: str,
    allowed: set,
    max_bases: int,
    ban_cls: Sequence[str],
) -> List[GateFinding]:
    out: List[GateFinding] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for sub in ban_cls:
            if sub and sub in node.name:
                out.append(
                    GateFinding(
                        gate="shape",
                        code="shape_banned_class_ast",
                        message=f"banned class {node.name!r} (pattern {sub!r})",
                        path=path,
                        severity="block",
                    )
                )
        nontrivial = []
        for b in node.bases:
            name = _ast_name(b)
            if name and name not in allowed:
                nontrivial.append(name)
        if len(nontrivial) > max_bases:
            out.append(
                GateFinding(
                    gate="shape",
                    code="shape_deep_inherit_ast",
                    message=(
                        f"class {node.name} nontrivial bases {nontrivial} "
                        f"> max_inherit_bases={max_bases}"
                    ),
                    path=path,
                    severity="block",
                )
            )
    return out


def _ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _ast_name(node.value)
    return ""


def evaluate_diff(
    *,
    name_status: str = "",
    numstat: str = "",
    unified_diff: str = "",
    config: Optional[Mapping[str, Any]] = None,
    profile_name: str = "",
    now: Optional[date] = None,
) -> GateReport:
    cfg, source = load_physical_gates_config(override=config)
    stats = collect_diff_stats(
        name_status=name_status, numstat=numstat, unified_diff=unified_diff
    )
    mode = resolve_mode(cfg, now=now)
    if mode == "off":
        return GateReport(
            ok=True,
            mode=mode,
            profile="off",
            stats=stats,
            config_source=source,
            block_after=str(cfg.get("block_after") or ""),
        )

    prof_name = select_profile(stats.paths, cfg, forced=profile_name)
    profiles = cfg.get("profiles") or {}
    profile = dict(profiles.get(prof_name) or profiles.get("business") or {})

    raw = check_inflation(stats, profile) + check_shape(stats, cfg, profile)
    exemptions = _active_exemptions(cfg, now=now)
    applied: List[str] = []
    findings: List[GateFinding] = []
    for f in raw:
        if _exempted(f, exemptions, applied):
            continue
        # In warn mode, keep severity as warn for reporting; block mode keeps block.
        if mode == "warn" and f.severity == "block":
            f = GateFinding(
                gate=f.gate,
                code=f.code,
                message=f.message,
                path=f.path,
                severity="warn",
            )
        findings.append(f)

    blocking = [f for f in findings if f.severity == "block"]
    ok = True
    if mode == "block" and blocking:
        ok = False
    # warn mode always ok for exit code; callers still print findings

    return GateReport(
        ok=ok,
        mode=mode,
        profile=prof_name,
        findings=findings,
        stats=stats,
        exemptions_applied=applied,
        config_source=source,
        block_after=str(cfg.get("block_after") or ""),
    )
