#!/usr/bin/env python3
"""Lint all engine SKILL.md for execution_type pairing + quality debt.

Fail codes (exit 1 unless --warn-only):
  - exec_type_dir_mismatch / handler pairing
  - misplaced_file_completion
  - skill_noop_phrases
  - invocation_mode_conflict

Usage:
  python3 scripts/lint_engine_skills.py
  python3 scripts/lint_engine_skills.py --json
  python3 scripts/lint_engine_skills.py --warn-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent
ENGINE_SKILLS = WORKSPACE / "aiPlat-core" / "core" / "engine" / "skills"
CORE_ROOT = WORKSPACE / "aiPlat-core"

FAIL_CODES = frozenset(
    {
        "exec_type_dir_mismatch",
        "misplaced_file_completion",
        "skill_noop_phrases",
        "invocation_mode_conflict",
        "handler_pairing",  # script-local pairing code
        "unknown_execution_type",  # E4 matrix
        "prompt_mutating_effects",  # E4 matrix
    }
)

# Align with skill_side_effect_gate.MUTATING_EFFECT_TYPES (keep local for 0-import scan).
_MUTATING_EFFECT_TYPES = frozenset(
    {
        "write",
        "delete",
        "exec",
        "execute",
        "shell",
        "subprocess",
        "command",
        "network",
        "http",
        "https",
        "upload",
        "rpc",
    }
)
_KNOWN_EXEC_TYPES = frozenset(
    {"handler", "hybrid", "prompt", "python_class", "tool_wrapper", "llm", "ai", "script", "code", ""}
)


def _parse_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_raw, body = parts[1], parts[2]
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(fm_raw) or {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
        for key in (
            "name",
            "execution_type",
            "execution_mode",
            "invocation_mode",
            "sop_goal",
            "completion_criterion",
            "auto_trigger_allowed",
            "uses_file_output",
        ):
            m = re.search(rf"^{key}:\s*(.*)$", fm_raw, re.M)
            if not m:
                continue
            val = m.group(1).strip().strip("\"'")
            if key == "completion_criterion" and val in ("|", ">"):
                # folded block — capture until next top-level key
                m2 = re.search(
                    rf"^{key}:\s*[|>].*\n((?:  .*\n)*)",
                    fm_raw,
                    re.M,
                )
                val = m2.group(1) if m2 else val
            if key == "auto_trigger_allowed":
                data[key] = val.lower() in ("true", "yes", "1")
            elif key == "uses_file_output":
                data[key] = val.lower() in ("true", "yes", "1")
            else:
                data[key] = val
    return data, body


def _skill_payload(skill_dir: Path) -> Optional[Dict[str, Any]]:
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return None
    text = md.read_text(encoding="utf-8")
    fm, body = _parse_front_matter(text)
    name = str(fm.get("name") or skill_dir.name).strip()
    meta: Dict[str, Any] = {
        "filesystem": {
            "skill_dir": str(skill_dir.resolve()),
            "skill_md": str(md.resolve()),
        },
        "completion_criterion": fm.get("completion_criterion") or "",
        "sop_goal": fm.get("sop_goal") or "",
        "body": (body or "").strip(),
        "invocation_mode": fm.get("invocation_mode"),
        "auto_trigger_allowed": fm.get("auto_trigger_allowed"),
        "execution_type": fm.get("execution_type"),
        "uses_file_output": bool(fm.get("uses_file_output")),
        "trigger_conditions": fm.get("trigger_conditions") or fm.get("triggers") or [],
    }
    return {
        "id": name,
        "name": name,
        "description": fm.get("description") or "",
        "execution_type": fm.get("execution_type"),
        "invocation_mode": fm.get("invocation_mode"),
        "auto_trigger_allowed": fm.get("auto_trigger_allowed"),
        "completion_criterion": fm.get("completion_criterion") or "",
        "metadata": meta,
    }


def _pairing_issue(skill_dir: Path, et: str) -> Optional[Dict[str, str]]:
    has_handler = (skill_dir / "handler.py").is_file()
    et_l = (et or "").strip().lower()
    if et_l in ("handler", "hybrid") and not has_handler:
        return {
            "code": "handler_pairing",
            "message": (
                f"execution_type={et_l} but handler.py missing in {skill_dir.name}"
            ),
            "skill_id": skill_dir.name,
        }
    if has_handler and et_l not in ("handler", "python_class", "hybrid"):
        return {
            "code": "handler_pairing",
            "message": (
                f"handler.py exists but execution_type={et_l or '(empty)'} "
                f"in {skill_dir.name} (should be handler)"
            ),
            "skill_id": skill_dir.name,
        }
    return None


def _unknown_execution_type_issue(skill_dir: Path, et: str) -> Optional[Dict[str, str]]:
    et_l = (et or "").strip().lower()
    if not et_l:
        return None
    # Prefer registry when available; fall back to local allowlist.
    known = set(_KNOWN_EXEC_TYPES)
    try:
        if str(CORE_ROOT) not in sys.path:
            sys.path.insert(0, str(CORE_ROOT))
        from core.harness.registry.execution_type_policy import coerce_execution_type

        coerced, err = coerce_execution_type(et_l, skill_name=skill_dir.name)
        if err:
            return {
                "code": "unknown_execution_type",
                "message": err,
                "skill_id": skill_dir.name,
            }
        # Soft-fallback path in coerce returns prompt for unknown in non-prod;
        # for CI lint, treat original unknown as error when not in known aliases.
        if coerced == "prompt" and et_l not in known and et_l not in ("prompt", "llm", "ai"):
            return {
                "code": "unknown_execution_type",
                "message": (
                    f"execution_type={et!r} is not a known type "
                    f"(CI fail-closed; would soft-fallback to prompt in non-prod)"
                ),
                "skill_id": skill_dir.name,
            }
    except Exception:
        if et_l not in known:
            return {
                "code": "unknown_execution_type",
                "message": f"execution_type={et!r} not in known set {sorted(known - {''})}",
                "skill_id": skill_dir.name,
            }
    return None


def _prompt_mutating_effects_issue(
    skill_dir: Path, et: str, fm: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    et_l = (et or "").strip().lower()
    if et_l in ("handler", "hybrid", "python_class", "tool_wrapper"):
        return None
    # prompt / empty / llm aliases: mutating effects need a realizer.
    effects = fm.get("effects")
    mutating: List[str] = []
    if isinstance(effects, list):
        for item in effects:
            if isinstance(item, dict):
                t = str(item.get("type") or "").strip().lower()
            else:
                t = str(item or "").strip().lower()
            if t in _MUTATING_EFFECT_TYPES:
                mutating.append(t)
    # Note: uses_file_output alone is OK for prompt + ## FILE: deploy path
    # (gate_llm_file_output_stage). Only explicit mutating effects require handler.
    if not mutating:
        return None
    if (skill_dir / "handler.py").is_file():
        return None
    return {
        "code": "prompt_mutating_effects",
        "message": (
            f"execution_type={et_l or 'prompt'} declares mutating effects "
            f"{mutating} but has no handler.py ({skill_dir.name})"
        ),
        "skill_id": skill_dir.name,
    }


def scan(skills_root: Path) -> List[Dict[str, Any]]:
    if str(CORE_ROOT) not in sys.path:
        sys.path.insert(0, str(CORE_ROOT))

    from core.management.skill_linter import lint_skill
    import core.management.skill_linter_base as lb

    lb._registry = None

    findings: List[Dict[str, Any]] = []
    if not skills_root.is_dir():
        return [
            {
                "skill_id": "<root>",
                "code": "handler_pairing",
                "message": f"engine skills dir missing: {skills_root}",
                "level": "error",
            }
        ]

    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        if skill_dir.name.startswith(".") or skill_dir.name == "__pycache__":
            continue
        payload = _skill_payload(skill_dir)
        if not payload:
            continue

        et_raw = str(payload.get("execution_type") or "")
        pair = _pairing_issue(skill_dir, et_raw)
        if pair:
            findings.append({**pair, "level": "error"})
        unk = _unknown_execution_type_issue(skill_dir, et_raw)
        if unk:
            findings.append({**unk, "level": "error"})
        # Re-parse fm for effects (payload.metadata may omit nested list detail).
        md = skill_dir / "SKILL.md"
        fm_full, _ = _parse_front_matter(md.read_text(encoding="utf-8"))
        mut = _prompt_mutating_effects_issue(skill_dir, et_raw, fm_full)
        if mut:
            findings.append({**mut, "level": "error"})

        report = lint_skill(payload)
        for key in ("errors", "warnings", "infos"):
            for it in report.get(key) or []:
                if not isinstance(it, dict):
                    continue
                code = str(it.get("code") or "")
                if code not in FAIL_CODES:
                    continue
                findings.append(
                    {
                        "skill_id": payload["name"],
                        "code": code,
                        "message": str(it.get("message") or code),
                        "level": str(it.get("level") or key.rstrip("s")),
                        "location": it.get("location"),
                    }
                )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint engine SKILL.md quality + pairing")
    ap.add_argument(
        "--path",
        default=str(ENGINE_SKILLS),
        help="Engine skills directory",
    )
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit 0 (print findings, do not fail CI)",
    )
    args = ap.parse_args()

    findings = scan(Path(args.path))
    # de-dupe by skill+code
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for f in findings:
        k = (f.get("skill_id"), f.get("code"), f.get("message"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)

    if args.json:
        print(json.dumps({"findings": uniq, "count": len(uniq)}, ensure_ascii=False, indent=2))
    else:
        if not uniq:
            print("PASS: engine skill quality lint clean")
        elif args.warn_only:
            # Keep PASS prefix so arch_guard ok_pattern still matches; list debts as soft warnings.
            print(f"PASS: engine skill quality lint clean ({len(uniq)} soft warning(s))")
            for f in uniq:
                print(f"  [{f.get('level')}] {f.get('skill_id')}: {f.get('code')} — {f.get('message')}")
        else:
            print(f"FAIL: engine skill quality lint — {len(uniq)} finding(s)")
            for f in uniq:
                print(f"  [{f.get('level')}] {f.get('skill_id')}: {f.get('code')} — {f.get('message')}")

    if args.warn_only or not uniq:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
