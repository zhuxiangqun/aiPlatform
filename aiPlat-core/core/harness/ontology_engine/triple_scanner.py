"""Cross-graph dependency scanner — scans AGENT.md, SKILL.md, and PipelineStageConfig
to populate the unified TripleStore with cross-graph relationships.

Reuses skill_deps.py for Skill→Syscall extraction.

Usage:
    python -m core.harness.ontology_engine.triple_scanner
    async:  await scan_and_populate()
"""

from __future__ import annotations
import logging

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .triple_store import TripleStore, get_triple_store

# ── Scan paths ─────────────────────────────────────

def _get_agent_dirs() -> List[str]:
    core_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [
        os.path.join(core_path, "core", "engine", "agents"),
        os.path.join(core_path, "core", "apps", "agents"),
        os.path.expanduser("~/.aiplat/agents"),
    ]


def _get_skill_dirs() -> List[str]:
    core_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [
        os.path.join(core_path, "core", "engine", "skills"),
        os.path.join(core_path, "core", "apps", "skills"),
        os.path.expanduser("~/.aiplat/skills"),
    ]


def _make_urn(entity_type: str, entity_id: str) -> str:
    return f"urn:aiplat:{entity_type}:{entity_id}"


def _parse_frontmatter(path: Path) -> Dict[str, Any]:
    """Parse YAML frontmatter from AGENT.md / SKILL.md."""
    try:
        content = path.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                import yaml
                fm = yaml.safe_load(parts[1])
                return fm if isinstance(fm, dict) else {}
    except Exception as e:
        logging.debug(str(e), exc_info=True)
    return {}


def _normalize_list(val: Any) -> List[str]:
    """Normalize frontmatter field that may be string or list."""
    if isinstance(val, list):
        return [str(v) for v in val]
    if isinstance(val, str):
        items = [v.strip() for v in val.strip("[]").split(",") if v.strip()]
        return items
    return []


async def scan_and_populate(store: TripleStore = None) -> Dict[str, Any]:
    """Full scan of AGENT.md, SKILL.md, skill_deps.py, and PipelineStageConfig.

    Populates the TripleStore with all discovered cross-graph dependencies.
    Returns stats dict.
    """
    if store is None:
        store = get_triple_store()

    # Clear previous auto-scan results
    store.clear_source("code_scan")

    triples: List[Tuple[str, str, str, float, str, dict]] = []

    # ── 1. Scan AGENT.md files ────────────────────────
    for root in _get_agent_dirs():
        if not os.path.isdir(root):
            continue
        for md_path in Path(root).rglob("AGENT.md"):
            fm = _parse_frontmatter(md_path)
            name = fm.get("name", "")
            if not name:
                continue
            agent_urn = _make_urn("agent", name)

            # Agent → Skill (normalize required_skills / skills)
            skills = (_normalize_list(fm.get("required_skills")) or
                      _normalize_list(fm.get("skills")))
            for sk in skills:
                triples.append((agent_urn, "uses_skill", _make_urn("skill", sk),
                               1.0, "code_scan", {}))

            # Agent → Tool
            tools = (_normalize_list(fm.get("required_tools")) or
                     _normalize_list(fm.get("tools")))
            for t in tools:
                triples.append((agent_urn, "uses_tool", _make_urn("tool", t),
                               1.0, "code_scan", {}))

            # Agent → Model
            model = fm.get("model") or (fm.get("config") or {}).get("model")
            if model:
                triples.append((agent_urn, "uses_model", str(model),
                               1.0, "code_scan", {}))

            # Agent → Phase
            phase = fm.get("phase") or (fm.get("pipeline") or {}).get("phase")
            if phase:
                triples.append((agent_urn, "member_of_phase", str(phase),
                               1.0, "code_scan", {}))

    # ── 2. Scan SKILL.md files ────────────────────────
    for root in _get_skill_dirs():
        if not os.path.isdir(root):
            continue
        for md_path in Path(root).rglob("SKILL.md"):
            fm = _parse_frontmatter(md_path)
            name = fm.get("name", "")
            if not name:
                continue
            skill_urn = _make_urn("skill", name)

            # Skill → Permission
            perms = _normalize_list(fm.get("permissions"))
            for p in perms:
                triples.append((skill_urn, "requires_permission", p,
                               1.0, "code_scan", {}))

    # ── 3. Reuse skill_deps.py for Skill→Syscall ─────
    try:
        from core.harness.knowledge.skill_deps import build_skill_deps
        deps = build_skill_deps()
        # Skill → Syscall
        for skill_id, info in deps.get("skills", {}).items():
            skill_urn = _make_urn("skill", skill_id)
            for syscall in info.get("deps", []):
                triples.append((skill_urn, "calls_syscall", str(syscall),
                               1.0, "code_scan", {}))
        # Agent → Skill (from skill_deps, which may have normalized names)
        for agent_id, info in deps.get("agents", {}).items():
            agent_urn = _make_urn("agent", agent_id)
            for skill_dep in info.get("required_skills", []):
                triples.append((agent_urn, "uses_skill",
                               _make_urn("skill", str(skill_dep)),
                               1.0, "code_scan", {}))
    except Exception as e:
        logging.debug(str(e), exc_info=True)

    # ── 4. Pipeline → Wiki (from PipelineStageConfig) ──
    # P0-A2 修复 (2026-08-19): 原实现引用不存在的 CoreFacade.get_pipeline_stages
    # （全仓无 class CoreFacade / get_pipeline_stages），属存量死路径——移除。
    # 若未来需要 pipeline→wiki 边，从 builder_project_service 的 stage 配置接入。

    # ── 4.5. Cross-domain bridges ────────────────────────
    try:
        from core.harness.knowledge.cross_domain_bridge import (
            build_wiki_to_agent_bridge,
            build_model_usage_bridge,
            build_prompt_to_agent_bridge,
        )
        triples += build_wiki_to_agent_bridge()
        triples += build_model_usage_bridge()
        triples += build_prompt_to_agent_bridge()
    except Exception:
        logging.debug("cross-domain bridge scan failed", exc_info=True)

    # ── 5. Batch write ────────────────────────────────
    if triples:
        store.add_batch(triples)

    return store.stats()


# ── CLI entry ───────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    result = asyncio.run(scan_and_populate())
    print(f"Scan complete: {result['total_triples']} triples")
    for p in result.get("by_predicate", []):
        label = "unknown"
        from .triple_store import TRIPLE_TYPES
        label = TRIPLE_TYPES.get(p["predicate"], p["predicate"])
        print(f"  {p['predicate']} ({label}): {p['count']}")
