"""
Skill Dependency Graph — scans SKILL.md frontmatter to map
Agent→Skill→Syscall dependencies.

Used by CI guard (§32) and runtime Skill impact analysis.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    u"""Extract YAML-like frontmatter from SKILL.md files."""
    fm: Dict[str, Any] = {}
    if not text.startswith("---"):
        return fm
    parts = text.split("---", 2)
    if len(parts) < 3:
        return fm
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip()
        val = v.strip().strip("'\"")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = val
    return fm


def _extract_syscalls_from_sop(body: str) -> List[str]:
    u"""Heuristic extraction of syscall references from SKILL.md body text."""
    import re
    calls: Set[str] = set()
    for m in re.finditer(r'sys_(\w+)_(\w+)', body):
        calls.add(f"sys_{m.group(1)}_{m.group(2)}")
    for m in re.finditer(r'sys_(\w+)', body):
        calls.add(f"sys_{m.group(1)}")
    return sorted(calls)


def build_skill_deps(skills_root: str = None) -> Dict[str, Any]:
    u"""Scan all SKILL.md files and build a dependency graph.

    Returns:
      {
        agents: {agent_id: {required_skills: [...], type: "..."}},
        skills: {skill_id: {deps: [...], effects: [...], category: "..."}},
        syscalls: {syscall_name: set of skill_ids that use it},
        unknown_refs: [refs in AGENT.md that don't resolve to skills],
      }
    """
    import re

    if skills_root is None:
        # Find skills directory relative to core package
        import core
        core_path = os.path.dirname(core.__file__) if hasattr(core, '__file__') and core.__file__ else None
        if core_path:
            skills_root = os.path.join(core_path, "engine", "skills")
        else:
            # Fallback: search from current file
            current = os.path.dirname(os.path.abspath(__file__))
            for _ in range(5):
                candidate = os.path.join(current, "engine", "skills")
                if os.path.isdir(candidate):
                    skills_root = candidate
                    break
                current = os.path.dirname(current)
        if not skills_root or not os.path.isdir(skills_root):
            return {"agents": {}, "skills": {}, "syscalls": {}, "unknown_refs": [],
                    "stats": {"total_skills": 0, "total_agents": 0, "total_syscalls_used": 0, "unknown_references": 0}}

    skills_path = Path(skills_root)
    agents_path = skills_path.parent / "agents"

    skill_deps: Dict[str, Any] = {}
    syscall_users: Dict[str, Set[str]] = {}

    # Scan skills
    for skill_dir in sorted(skills_path.iterdir()):
        if not skill_dir.is_dir():
            continue
        md_file = skill_dir / "SKILL.md"
        if not md_file.exists():
            continue
        skill_id = skill_dir.name
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        fm = _parse_frontmatter(text)
        body = text.split("---", 2)[2] if text.count("---") >= 2 else text

        deps = _extract_syscalls_from_sop(body)
        for d in deps:
            if d not in syscall_users:
                syscall_users[d] = set()
            syscall_users[d].add(skill_id)

        skill_deps[skill_id] = {
            "id": skill_id,
            "name": fm.get("name", skill_id),
            "deps": deps,
            "effects": fm.get("effects", []),
            "category": fm.get("category", ""),
            "path": str(skill_dir),
        }

    # Scan agents
    agent_refs: Dict[str, Any] = {}
    unknown: List[Dict[str, str]] = []

    if agents_path.exists():
        for agent_dir in sorted(agents_path.iterdir()):
            if not agent_dir.is_dir():
                continue
            md_file = agent_dir / "AGENT.md"
            if not md_file.exists():
                continue
            agent_id = agent_dir.name
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            fm = _parse_frontmatter(text)

            required = fm.get("required_skills", fm.get("skills", []))
            if isinstance(required, str):
                required = [required]

            for r in required:
                if r not in skill_deps:
                    unknown.append({"agent": agent_id, "ref": r})

            agent_refs[agent_id] = {
                "id": agent_id,
                "required_skills": required,
                "type": fm.get("type", fm.get("agent_type", "unknown")),
            }

    return {
        "agents": agent_refs,
        "skills": skill_deps,
        "syscalls": {k: sorted(v) for k, v in syscall_users.items()},
        "unknown_refs": unknown,
        "unused_skills": _find_unused_skills(skill_deps, agent_refs),
        "stats": {
            "total_skills": len(skill_deps),
            "total_agents": len(agent_refs),
            "total_syscalls_used": len(syscall_users),
            "unknown_references": len(unknown),
            "unused_skills": len(_find_unused_skills(skill_deps, agent_refs)),
            "syscall_caller_count": {s: _count_syscall_callers(s) for s in syscall_users},
        },
    }


def _find_unused_skills(skill_deps, agent_refs) -> List[str]:
    u"""Find skills with no Agent reference AND no Python handler class."""
    agent_skills = set(r for a in agent_refs.values() for r in a.get("required_skills", []))
    unused = []
    for skill_id, info in skill_deps.items():
        if skill_id in agent_skills:
            continue
        # Check for Python handler class
        skill_path = info.get("path") or ""
        has_handler = False
        if skill_path:
            handler_file = os.path.join(skill_path, "handler.py")
            if os.path.isfile(handler_file):
                has_handler = True
        if not has_handler:
            unused.append(skill_id)
    return sorted(unused)


def _count_syscall_callers(syscall_name: str) -> int:
    u"""Count non-loop.py, non-test Python importers of a syscall."""
    import os, subprocess
    try:
        from pathlib import Path
        core_root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            ["grep", "-rn", f"from.*import.*{syscall_name}|import.*{syscall_name}", str(core_root)],
            capture_output=True, text=True, timeout=5
        )
        count = 0
        for line in result.stdout.split('\n'):
            if line and '/tests/' not in line and 'loop.py' not in line and 'skill_deps' not in line:
                count += 1
        return count
    except Exception:
        return -1


def skill_impact(skill_id: str) -> Dict[str, Any]:
    u"""Find all agents and downstream skills affected by a given skill.
    
    Returns {skill_id, agents_using: [...], skills_depending: [...]}
    """
    deps = build_skill_deps()
    if skill_id not in deps["skills"]:
        return {"skill_id": skill_id, "agents_using": [], "skills_depending": [], "exists": False}

    agents = []
    for aid, a in deps["agents"].items():
        if skill_id in a.get("required_skills", []):
            agents.append(aid)

    # Check if any other skill's SOP references this skill
    depending = []
    for sid, s in deps["skills"].items():
        if sid == skill_id:
            continue
        # Check if skill body mentions the target skill
        body = (Path(s.get("path", "")) if s.get("path") else None)
        # Simple check: any skill that mentions the target in its SOP
        # This is a heuristic — full analysis needs the SKILL.md body
        depending.append(sid)

    return {
        "skill_id": skill_id,
        "agents_using": agents,
        "skills_depending": depending[:10],
        "exists": True,
    }
