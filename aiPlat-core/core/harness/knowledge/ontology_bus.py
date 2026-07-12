"""
Ontology Consumpion Bus — dynamic YAML data loader.

Replaces hardcoded injection strings in registry.py with YAML-driven
rendering. Makes ai-solution.yaml the single source of truth for
solution archetypes and digital employee role mappings.

Design principle: ontology YAMLs are the config — Python code only transports.

callers: registry.py field-assessment system_parts injection
"""

from __future__ import annotations

import logging
import os as _os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_ONTOLOGY_DIR = _os.path.expanduser("~/.aiplat/ontologies")

# Hot-reload cache: { "file_name:section" → (data, mtime) }
_cache: Dict[str, tuple] = {}


def _load_yaml_section(file_name: str, section: str) -> Optional[list]:
    """Load a named list section from an ontology YAML file with mtime-based hot-reload.

    Caches the parsed data. On subsequent calls, re-reads the file only if
    its modification time has changed since the last read. This enables
    zero-restart configuration updates.
    """
    path = _os.path.join(_ONTOLOGY_DIR, file_name)
    if not _os.path.exists(path):
        return None

    cache_key = f"{file_name}:{section}"
    current_mtime = _os.path.getmtime(path)

    # Return cached data if file hasn't changed
    if cache_key in _cache:
        cached_data, cached_mtime = _cache[cache_key]
        if cached_mtime == current_mtime:
            return cached_data

    # Load fresh data
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        data = raw.get(section)
        if isinstance(data, list):
            _cache[cache_key] = (data, current_mtime)
            logger.debug("OntologyBus: hot-reload %s (mtime=%.0f)", cache_key, current_mtime)
            return data
        return None
    except Exception as e:
        logger.debug("OntologyBus: failed to load %s: %s", cache_key, str(e))
        return None


def clear_cache():
    """Force cache invalidation (useful for testing or manual refresh)."""
    _cache.clear()
    logger.debug("OntologyBus: cache cleared")


# ═══════════════════════════════════════════════════════════════
# Solution Archetypes
# ═══════════════════════════════════════════════════════════════

def load_solution_archetypes() -> List[Dict[str, Any]]:
    """Load solution archetypes from ai-solution.yaml.

    Returns a list of dicts with keys: name, category, data_maturity_min,
    cost_level, estimated_cycle_months, deployment_modes, xinchuang_compatible,
    description.
    """
    data = _load_yaml_section("ai-solution.yaml", "solution_archetypes")
    return data or []


def render_solution_table(archetypes: List[Dict[str, Any]] = None) -> str:
    """Render solution archetypes as a Markdown table for §6 injection.

    Args:
        archetypes: list from load_solution_archetypes(). If None, auto-loads.

    Returns:
        Multi-line Markdown string: header + table body + §6 rules.
    """
    if archetypes is None:
        archetypes = load_solution_archetypes()

    lines = [
        "## AI解决方案原型库（用于 §6 推荐配置参考）",
        "",
        "以下为标准化AI解决方案原型，§6推荐时必须参考其约束条件：",
        "",
        "| 方案类别 | 数据成熟度要求 | 成本等级 | 部署模式 | 预期周期 | 信创兼容 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for a in archetypes:
        name = a.get("name", "")
        dm = a.get("data_maturity_min", 0)
        dm_label = {1: "≥1 (无数据)", 2: "≥2 (部分结构化)", 3: "≥3 (完整结构化)",
                    4: "≥4 (标注数据集)", 5: "≥5 (持续标注管线)"}.get(dm, f"≥{dm}")
        cost = a.get("cost_level", "medium")
        cost_label = {"low": "低", "medium": "中", "high": "高"}.get(cost, cost)
        deploy = a.get("deployment_modes", [])
        deploy_label = "私有化" if deploy == ["on_premise"] else \
                       "云端" if deploy == ["cloud"] else \
                       "混合" if "hybrid" in deploy else \
                       "云端/私有化" if set(deploy) == {"cloud", "on_premise"} else \
                       "私有化/云端"
        cycle = a.get("estimated_cycle_months", "")
        xc = "✅" if a.get("xinchuang_compatible", False) else "部分"
        lines.append(
            f"| {name} | {dm_label} | {cost_label} | {deploy_label} | {cycle}月 | {xc} |"
        )

    lines.extend([
        "",
        "**§6 推荐强制规则**：",
        "- 若 §2 数据成熟度 < 推荐方案的 data_maturity_min → 必须先安排数据采集阶段",
        "- 若 §3 要求私有化 → 只能推荐 deployment_modes 含私有化的方案",
        "- 若 §4 要求信创 → 只能推荐 xinchuang_compatible=✅ 的方案",
        "- 若 §7 POC ≤3个月 → 只能推荐 estimated_cycle ≤3月的方案",
    ])

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Digital Employee Roles
# ═══════════════════════════════════════════════════════════════

def load_digital_employees() -> List[Dict[str, Any]]:
    """Load digital employee role mappings from ai-solution.yaml.

    Returns a list of dicts with keys: keywords, role_name, role_ability.
    """
    data = _load_yaml_section("ai-solution.yaml", "digital_employee_roles")
    return data or []


def render_digital_employee_table(roles: List[Dict[str, Any]] = None) -> str:
    """Render digital employee role mappings as a Markdown table for §6 injection.

    Args:
        roles: list from load_digital_employees(). If None, auto-loads.

    Returns:
        Multi-line Markdown string: header + instruction + table + rules.
    """
    if roles is None:
        roles = load_digital_employees()

    lines = [
        "## 数字员工角色匹配（§6 必读）",
        "",
        "请在 §6 的每个推荐方案前标注对应的数字员工角色（🤖），格式如下：",
        "> 🤖 数字员工角色：{角色名}",
        "> 该方案可承担「{角色名}」角色，自动完成{具体工作}。",
        "",
        "数字员工角色映射表（根据方案关键词匹配）：",
        "| AI方案关键词 | 数字员工角色 | 角色能力 |",
        "| :--- | :--- | :--- |",
    ]

    for r in roles:
        kw = r.get("keywords", "")
        name = r.get("role_name", "")
        ability = r.get("role_ability", "")
        lines.append(f"| {kw} | {name} | {ability} |")

    lines.extend([
        "",
        "规则：§6 每个推荐方案必须匹配一行数字员工角色。优先使用精确匹配，无匹配时使用「业务顾问」作为默认角色。",
        "角色标签写在方案名称之前，作为推荐方案的增强说明。",
    ])

    return "\n".join(lines)
