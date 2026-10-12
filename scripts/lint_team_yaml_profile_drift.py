#!/usr/bin/env python3
"""O2: optional lint — team YAML vs AGENT.md architecture_profile / execution_backend drift.

Default: WARNING only (exit 0). ``--strict``: conflict without ``# drift-ok: <reason>`` → exit 1.
Does **not** change runtime YAML-wins semantics (team_planner).

Usage:
  python3 scripts/lint_team_yaml_profile_drift.py
  python3 scripts/lint_team_yaml_profile_drift.py --team path/to/team.yaml
  python3 scripts/lint_team_yaml_profile_drift.py --strict
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent

_DRIFT_OK_RE = re.compile(r"#\s*drift-ok\s*:\s*(.+)", re.I)
_COMPARE_KEYS = ("architecture_profile", "execution_backend")


def _aiplat_home() -> Path:
    home = (os.environ.get("AIPLAT_HOME") or "").strip()
    return Path(home) if home else Path.home() / ".aiplat"


def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError:
        print("WARN: PyYAML not available — skip team YAML drift lint", file=sys.stderr)
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace")) or {}
    except Exception as exc:
        print(f"WARN: cannot parse {path}: {exc}", file=sys.stderr)
        return None


def _parse_agent_frontmatter(agent_md: Path) -> Dict[str, Any]:
    if not agent_md.is_file():
        return {}
    text = agent_md.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end]
    data = _load_yaml_str(block)
    return data if isinstance(data, dict) else {}


def _load_yaml_str(s: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(s) or {}
    except Exception:
        return {}


def _find_agent_md(agent_id: str) -> Optional[Path]:
    aid = (agent_id or "").strip()
    if not aid:
        return None
    candidates = [
        _aiplat_home() / "agents" / aid / "AGENT.md",
        WORKSPACE / "aiPlat-core" / "workspace_seeds" / "agents" / aid / "AGENT.md",
        WORKSPACE / "aiPlat-core" / "core" / "workspace_seeds" / "agents" / aid / "AGENT.md",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _stage_dicts(doc: Any) -> List[Dict[str, Any]]:
    if not isinstance(doc, dict):
        return []
    stages = doc.get("stages") or doc.get("team") or []
    if isinstance(stages, dict):
        stages = list(stages.values())
    out: List[Dict[str, Any]] = []
    for s in stages:
        if isinstance(s, dict):
            out.append(s)
    return out


def _has_drift_ok(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _DRIFT_OK_RE.search(text)
    return bool(m and (m.group(1) or "").strip())


def lint_team_file(path: Path) -> List[str]:
    """Return human-readable conflict messages (empty if none)."""
    doc = _load_yaml(path)
    if doc is None:
        return []
    msgs: List[str] = []
    for stage in _stage_dicts(doc):
        aid = str(stage.get("agent_id") or stage.get("agent") or "").strip()
        if not aid:
            continue
        agent_md = _find_agent_md(aid)
        if agent_md is None:
            continue
        fm = _parse_agent_frontmatter(agent_md)
        for key in _COMPARE_KEYS:
            yv = str(stage.get(key) or "").strip().lower()
            av = str(fm.get(key) or "").strip().lower()
            if not yv or not av:
                continue
            if yv != av:
                msgs.append(
                    f"{path}: stage agent_id={aid} {key} YAML={yv!r} vs AGENT.md={av!r} "
                    f"({agent_md})"
                )
    return msgs


def discover_team_files(extra: Optional[List[Path]] = None) -> List[Path]:
    found: List[Path] = []
    roots = [
        _aiplat_home() / "teams",
        WORKSPACE / "aiPlat-core" / "workspace_seeds",
        WORKSPACE / "aiPlat-core" / "core" / "workspace_seeds",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*.yaml"):
            if "team" in p.name.lower() or (p.parent.name == "teams"):
                found.append(p)
        for p in root.rglob("*.yml"):
            if "team" in p.name.lower() or (p.parent.name == "teams"):
                found.append(p)
    if extra:
        found.extend(extra)
    # de-dupe
    seen = set()
    out: List[Path] = []
    for p in found:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint team YAML vs AGENT.md profile drift (O2)")
    ap.add_argument("--team", action="append", type=Path, help="Team YAML path (repeatable)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 on conflicts without # drift-ok: <reason>",
    )
    args = ap.parse_args()
    files = discover_team_files(args.team)
    if not files:
        print("PASS: no team YAML files found (nothing to lint)")
        return 0

    warnings: List[str] = []
    hard: List[str] = []
    for path in files:
        msgs = lint_team_file(path)
        if not msgs:
            continue
        ok = _has_drift_ok(path)
        for m in msgs:
            if ok:
                warnings.append(f"(drift-ok) {m}")
            else:
                warnings.append(m)
                hard.append(m)

    for w in warnings:
        print(f"WARN: {w}")
    if args.strict and hard:
        print(f"FAIL: team YAML profile drift — {len(hard)} conflict(s) without # drift-ok")
        return 1
    if warnings:
        print(f"PASS (with {len(warnings)} warning(s)): YAML drift lint complete")
    else:
        print("PASS: no YAML vs AGENT.md profile drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
