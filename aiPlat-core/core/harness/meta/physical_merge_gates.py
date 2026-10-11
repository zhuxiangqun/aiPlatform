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
    gate: str  # inflation | shape | debt
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
    exemption_debt: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "profile": self.profile,
            "config_source": self.config_source,
            "block_after": self.block_after,
            "exemptions_applied": list(self.exemptions_applied),
            "exemption_debt": dict(self.exemption_debt or {}),
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
        "block_after": "2026-10-25",
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
        "profile_neutral_globs": [
            "AIPLAT_CAPABILITIES.md",
            "docs/**",
            "**/capability_registry.yaml",
        ],
        "banned_path_segments": ["/generic/", "/framework/"],
        "banned_new_basenames": ["event_bus.py", "observer.py", "scheduler.py"],
        "banned_class_substrings": ["EventBus", "ObserverTree"],
        "allowed_bases": ["object", "Exception", "ABC", "Protocol", "BaseModel"],
        "max_active_exemptions": 3,
        "exemptions": [],
    }


def _max_active_exemptions(config: Mapping[str, Any]) -> int:
    raw = config.get("max_active_exemptions", 3)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 3
    return max(0, n)


def _exemption_row(raw: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(raw.get("id") or ""),
        "owner": str(raw.get("owner") or "").strip(),
        "reason": str(raw.get("reason") or "").strip()[:160],
        "expires": str(raw.get("expires") or "").strip()[:10],
        "gates": [str(g) for g in (raw.get("gates") or [])][:8],
        "paths": [str(p) for p in (raw.get("paths") or [])][:8],
    }


def assess_exemption_debt(
    config: Mapping[str, Any],
    now: Optional[date] = None,
) -> Dict[str, Any]:
    """Treat exemptions as debt: owner + cap + expired-unreviewed → block.

    Active exemptions without owner/reason/expires never apply (not a silent SKIP).
    Entries past ``expires`` that remain in YAML are unreviewed debt → severity block.
    Active count above ``max_active_exemptions`` → over_cap → severity block.
    """
    today = now or datetime.now(timezone.utc).date()
    max_active = _max_active_exemptions(config)
    active: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []

    for raw in config.get("exemptions") or []:
        if not isinstance(raw, dict):
            continue
        row = _exemption_row(raw)
        eid = row["id"] or row["reason"] or "exemption"
        owner = row["owner"]
        reason = row["reason"]
        exp_s = row["expires"]
        if not exp_s or not reason or not owner:
            missing = []
            if not owner:
                missing.append("owner")
            if not reason:
                missing.append("reason")
            if not exp_s:
                missing.append("expires")
            invalid.append({**row, "id": eid, "missing": missing})
            continue
        try:
            exp_d = date.fromisoformat(exp_s[:10])
        except ValueError:
            invalid.append({**row, "id": eid, "missing": ["expires"]})
            continue
        if exp_d < today:
            expired.append({**row, "id": eid})
            continue
        active.append({**row, "id": eid, "_expires_date": exp_d})

    active.sort(key=lambda r: r.get("_expires_date") or date.max)
    for r in active:
        r.pop("_expires_date", None)

    over_cap = len(active) > max_active
    capped_active = active[:max_active] if max_active >= 0 else []
    excess = active[max_active:] if over_cap else []

    reasons: List[str] = []
    severity = "go"
    if expired:
        severity = "block"
        ids = ",".join(str(x.get("id") or "?") for x in expired[:4])
        reasons.append(f"exemption_debt_expired={len(expired)} ({ids})")
    if invalid:
        severity = "block"
        ids = ",".join(str(x.get("id") or "?") for x in invalid[:4])
        reasons.append(f"exemption_debt_invalid={len(invalid)} ({ids})")
    if over_cap:
        severity = "block"
        reasons.append(
            f"exemption_debt_over_cap={len(active)}>{max_active}"
        )
    elif active and severity == "go":
        severity = "watch"
        ids = ",".join(str(x.get("id") or "?") for x in active[:4])
        reasons.append(f"exemption_debt_active={len(active)} ({ids})")

    return {
        "max_active": max_active,
        "active_count": len(active),
        "active": capped_active,
        "excess": excess,
        "invalid": invalid,
        "expired": expired,
        "over_cap": over_cap,
        "severity": severity,
        "reasons": reasons,
        "policy": "owner+reason+expires required; expired-unreviewed→block; over_cap→block",
    }


def debt_findings_from_ledger(debt: Mapping[str, Any]) -> List[GateFinding]:
    """Convert exemption debt ledger into non-exemptable GateFindings."""
    out: List[GateFinding] = []
    for row in debt.get("expired") or []:
        eid = str(row.get("id") or "?")
        out.append(
            GateFinding(
                gate="debt",
                code="exemption_debt_expired",
                message=(
                    f"exemption {eid!r} expired {row.get('expires')}; "
                    "remove or renew with owner+reason+expires (unreviewed debt→block)"
                ),
                severity="block",
            )
        )
    for row in debt.get("invalid") or []:
        eid = str(row.get("id") or "?")
        missing = ",".join(str(m) for m in (row.get("missing") or [])) or "fields"
        out.append(
            GateFinding(
                gate="debt",
                code="exemption_debt_invalid",
                message=f"exemption {eid!r} missing {missing} (not applied; debt→block)",
                severity="block",
            )
        )
    if debt.get("over_cap"):
        out.append(
            GateFinding(
                gate="debt",
                code="exemption_debt_over_cap",
                message=(
                    f"active exemptions {debt.get('active_count')} > "
                    f"max_active_exemptions={debt.get('max_active')} "
                    "(excess not applied)"
                ),
                severity="block",
            )
        )
    return out


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
    neutral = list(config.get("profile_neutral_globs") or [])
    # Docs / CAPABILITIES / registry sync must not force business profile —
    # those files are required by workspace sync rules alongside harness changes.
    scored = [
        p
        for p in paths
        if p
        and not (
            neutral and any(_match_glob(p, g) for g in neutral)
        )
    ]
    if not scored:
        # Pure docs/sync PR — still use business (tight) so docs-only bloat is visible.
        return "business"
    if globs and all(any(_match_glob(p, g) for g in globs) for p in scored):
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
    """Return apply-able exemptions: owner+reason+expires, not expired, within cap.

    Sorted by soonest expiry; entries beyond ``max_active_exemptions`` are dropped
    (see ``assess_exemption_debt`` / over_cap findings).
    """
    debt = assess_exemption_debt(config, now=now)
    # Map capped active rows back to original dicts (preserve paths/gates for matching).
    allowed_ids = {
        str(r.get("id") or r.get("reason") or "")
        for r in (debt.get("active") or [])
    }
    today = now or datetime.now(timezone.utc).date()
    out: List[Dict[str, Any]] = []
    for raw in config.get("exemptions") or []:
        if not isinstance(raw, dict):
            continue
        if not str(raw.get("owner") or "").strip():
            continue
        if not str(raw.get("reason") or "").strip():
            continue
        exp = str(raw.get("expires") or "").strip()
        if not exp:
            continue
        try:
            if date.fromisoformat(exp[:10]) < today:
                continue
        except ValueError:
            continue
        eid = str(raw.get("id") or raw.get("reason") or "")
        if eid not in allowed_ids:
            continue
        out.append(raw)
    # Preserve soonest-expiry order from debt.ledger
    order = {str(r.get("id") or r.get("reason") or ""): i for i, r in enumerate(debt.get("active") or [])}
    out.sort(key=lambda r: order.get(str(r.get("id") or r.get("reason") or ""), 999))
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

        # AST pass on added/changed .py snippets (not only brand-new paths)
        if text.strip():
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
    debt = assess_exemption_debt(cfg, now=now)
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

    # Debt findings are never exemptable (cap/owner/expiry governance).
    for f in debt_findings_from_ledger(debt):
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
        exemption_debt=debt,
    )
