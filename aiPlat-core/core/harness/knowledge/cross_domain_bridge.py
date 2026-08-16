"""Cross-Domain Bridge — 建立跨域三元组桥接边。

将 5 个孤立知识图（能力图/代码图/Wiki/技能依赖/KB）通过共享 URN
连接到统一的 TripleStore，使跨域查询（"Wiki 被哪个 Agent 引用？"等）可回答。

桥接函数:
  - build_wiki_to_agent_bridge() — Wiki 页面 → 相关 Skill → 相关 Agent
  - build_model_usage_bridge()   — Agent model 字段 → uses_model 三元组
  - build_prompt_to_agent_bridge() — Prompt 模板 → 使用该模板的 Agent

V1 准确率:
  - Wiki→Agent: 关键词匹配，60-70%
  - Model→Agent: 直接映射，100%
  - Prompt→Agent: prompt_loader 调用点分析，80%+
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.harness.ontology_engine.triple_store import _make_urn

_log = logging.getLogger("aiplat.cross_domain_bridge")


# ── Helpers ─────────────────────────────────────────────

def _get_all_agent_skills() -> Dict[str, List[str]]:
    """返回 {agent_id: [skill_id, ...]} 映射。"""
    result: Dict[str, List[str]] = {}
    for root in _get_agent_dirs():
        if not os.path.isdir(root):
            continue
        for md_path in Path(root).rglob("AGENT.md"):
            fm = _parse_frontmatter(md_path)
            name = fm.get("name", "")
            if not name:
                continue
            skills = (_normalize_list(fm.get("required_skills")) or
                      _normalize_list(fm.get("skills")))
            result[name] = skills
    return result


def _get_agent_dirs() -> list:
    try:
        from core.harness.ontology_engine.triple_scanner import _get_agent_dirs
        return _get_agent_dirs()
    except ImportError:
        return [os.path.expanduser("~/.aiplat/agents")]


def _parse_frontmatter(path: Path) -> Dict[str, Any]:
    try:
        from core.harness.ontology_engine.triple_scanner import _parse_frontmatter
        return _parse_frontmatter(path)
    except ImportError:
        return {}


def _normalize_list(val: Any) -> List[str]:
    if isinstance(val, list):
        return [str(v) for v in val if v]
    if isinstance(val, str):
        return [val]
    return []


# ── Bridge 1: Wiki → Agent ──────────────────────────────

def build_wiki_to_agent_bridge() -> List[Tuple[str, str, str, float, str, dict]]:
    """用关键词匹配建立 Wiki 页面→Agent 的三元组。

    V1: 关键词匹配，预期准确率 60-70%。
    # TODO(v2): 升级为 Embedding 余弦相似度替代关键词匹配。
    """
    triples: list = []
    urn = _make_urn

    # Get all Wiki pages from triple scanner
    try:
        from core.harness.knowledge.wiki_engine import WikiEngine
        engine = WikiEngine()
        pages = engine.list_all_pages()
    except Exception:
        _log.debug("WikiEngine unavailable for wiki→agent bridge", exc_info=True)
        return triples

    agents = _get_all_agent_skills()
    if not agents:
        return triples

    for page in pages[:50]:  # V1: sample first 50 wiki pages
        title = getattr(page, 'title', '') or ''
        summary = getattr(page, 'summary', '') or ''
        content = f"{title} {summary}".lower()
        if not content.strip():
            continue
        wiki_urn = urn("wiki", title)

        for agent_id, skills in agents.items():
            for skill_id in skills:
                if skill_id.lower() in content:
                    triples.append((wiki_urn, "used_by_agent",
                                   urn("agent", agent_id), 0.7,
                                   "wiki_agent_bridge", {}))
                    break

    _log.info("Wiki→Agent bridge: %d triples", len(triples))
    return triples


# ── Bridge 2: Model → Agent ─────────────────────────────

def build_model_usage_bridge() -> List[Tuple[str, str, str, float, str, dict]]:
    """扫描所有 Agent 的 model 字段→建立 uses_model 三元组。"""
    triples: list = []
    urn = _make_urn

    for root in _get_agent_dirs():
        if not os.path.isdir(root):
            continue
        for md_path in Path(root).rglob("AGENT.md"):
            fm = _parse_frontmatter(md_path)
            agent_id = fm.get("name", "")
            if not agent_id:
                continue
            model = fm.get("model", "") or (fm.get("config", {}) or {}).get("model", "")
            if not model or model in ("auto", "default"):
                continue  # skip auto-resolved models
            triples.append((urn("agent", agent_id), "uses_model",
                           urn("model", model), 1.0,
                           "model_usage_bridge", {}))

    _log.debug("Model→Agent bridge: %d triples", len(triples))
    return triples


# ── Bridge 3: Prompt → Agent ────────────────────────────

def build_prompt_to_agent_bridge() -> List[Tuple[str, str, str, float, str, dict]]:
    """复用 prompt_loader 调用点扫描建立 Prompt→Agent 三元组。

    V1 验收标准: 至少建立 10+ 条 template→agent 三元组。
    若不可达，降级为 V1.5（Phase 4 之后单独交付）。
    """
    triples: list = []
    urn = _make_urn

    try:
        from core.harness.utils.prompt_loader import auto_classify
        templates = auto_classify()
        if not isinstance(templates, dict):
            return triples
    except Exception:
        _log.debug("prompt_loader.auto_classify unavailable", exc_info=True)
        return triples

    agents = _get_all_agent_skills()
    if not agents:
        return triples

    # Map template sources to agents by skill name matching
    for tpl_id, source_files in templates.items():
        tpl_urn = urn("template", tpl_id)
        sources = source_files if isinstance(source_files, list) else [source_files]
        for src in sources:
            src_str = str(src).lower()
            for agent_id, skills in agents.items():
                for skill_id in skills:
                    if skill_id.lower() in src_str:
                        triples.append((tpl_urn, "used_by_agent",
                                       urn("agent", agent_id), 0.8,
                                       "prompt_agent_bridge", {}))
                        break

    # ── Fallback: scan _DEFAULT_PROMPTS for template→agent keyword matches ──
    if len(triples) < 10:
        try:
            from core.harness.utils.prompt_loader import _DEFAULT_PROMPTS
            for tpl_id, content in _DEFAULT_PROMPTS.items():
                tpl_urn = urn("template", tpl_id)
                tpl_lower = str(content).lower()[:200]  # sample first 200 chars
                for agent_id, skills in agents.items():
                    for skill_id in skills:
                        if skill_id.lower() in tpl_lower:
                            triples.append((tpl_urn, "used_by_agent",
                                           urn("agent", agent_id), 0.6,
                                           "prompt_agent_bridge", {}))
                            break
        except Exception:
            logging.getLogger(__name__).debug("swallowing non-critical exception", exc_info=True)

    _log.info("Prompt→Agent bridge: %d triples%s", len(triples),
              " (V1.5 fallback)" if len(triples) > 0 and len(triples) < 10 else "")
    return triples
