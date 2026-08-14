"""本体驱动健康检查 — 发现孤儿实体、未使用资源、跨域不一致。

在 TripleStore 统一知识网络上运行 7 条检查规则：
  1. 孤儿 Skill — 无 Agent 绑定 + 无 Pipeline 使用
  2. 孤儿 Tool — 无 Agent/Skill 调用
  3. 孤儿 Agent — 从未被 Pipeline 引用
  4. 废弃模型被使用
  5. 孤立 Wiki 页面（V1 info 级别，V2 升级为 warn）
  6. 跨域不一致（V2 预留）
  7. 未使用 Prompt 模板
"""

from typing import Any, Dict, List


async def check_ontology_health() -> Dict[str, Any]:
    """本体驱动的健康检查——扫描 TripleStore 发现异常。"""
    from core.harness.ontology_engine.triple_store import get_triple_store

    store = get_triple_store()
    issues: List[Dict[str, Any]] = []

    # ── 1. 孤儿 Skill ──
    skills = store.get_by_predicate("uses_skill")
    skill_urns = {r["object"] for r in skills}
    for skill_urn in list(skill_urns)[:30]:
        upstream = store.get_upstream(skill_urn, depth=1)
        if not upstream:
            issues.append({
                "entity": skill_urn, "issue": "orphan_skill",
                "severity": "warn",
                "detail": "0 Agent bindings + 0 Pipeline usage",
            })

    # ── 2. 孤儿 Tool ──
    tools = store.get_by_predicate("uses_tool")
    tool_urns = {r["object"] for r in tools}
    for tool_urn in list(tool_urns)[:20]:
        upstream = store.get_upstream(tool_urn, depth=1)
        if not upstream:
            issues.append({
                "entity": tool_urn, "issue": "orphan_tool",
                "severity": "warn",
                "detail": "0 Agent/Skill callers",
            })

    # ── 3. 孤儿 Agent ──
    agents = store.get_by_predicate("uses_skill")
    agent_urns = {r["subject"] for r in agents}
    for agent_urn in list(agent_urns)[:30]:
        upstream = store.get_upstream(agent_urn, depth=1)
        if not upstream:
            issues.append({
                "entity": agent_urn, "issue": "orphan_agent",
                "severity": "info",
                "detail": "0 Pipeline references",
            })

    # ── 4. 废弃模型被使用 ──
    for r in store.get_by_predicate("uses_model"):
        obj = r.get("object", "")
        if "deprecated" in str(obj).lower() or "gpt-3" in str(obj).lower():
            issues.append({
                "entity": r["subject"], "issue": "uses_deprecated_model",
                "severity": "warn", "detail": obj,
            })

    # ── 5. 孤立 Wiki 页面 ──
    # TODO(v2): 增加检索次数判断再升级为 warn，当前 info 级别避免误报
    wiki_triples = store.get_by_predicate("depends_on_kb")
    if wiki_triples:
        wiki_urns = {r["subject"] for r in wiki_triples if "wiki" in r.get("subject", "")}
        for wiki_urn in list(wiki_urns)[:20]:
            d_count = len(store.get_downstream(wiki_urn, 1))
            u_count = len(store.get_upstream(wiki_urn, 1))
            if d_count + u_count == 0:
                issues.append({
                    "entity": wiki_urn, "issue": "isolated_wiki",
                    "severity": "info",
                    "detail": "0 incoming + 0 outgoing relations",
                })

    # ── 6. 跨域不一致（V2 预留）──
    # TODO(v2): Agent 声明的 Skill 不在 SkillRegistry 中

    # ── 7. 未使用 Prompt 模板 ──
    used_by = store.get_by_predicate("used_by_agent")
    used_template_urns = {r["subject"] for r in used_by if "template" in r.get("subject", "")}
    # Only flag if we have at least some template data
    if len(used_template_urns) > 0:
        all_template_urns = {r["subject"] for r in store.get_by_predicate("used_by_agent")
                            if "template" in r.get("subject", "")}
        unused = all_template_urns - {r["object"] for r in used_by}
        for tpl_urn in list(unused)[:10]:
            issues.append({
                "entity": tpl_urn, "issue": "unused_template",
                "severity": "info",
            })

    total = store.stats()["total_triples"]
    if issues:
        return {
            "status": "warn",
            "total_triples": total,
            "issue_count": len(issues),
            "issues": issues[:20],
        }
    return {"status": "pass", "total_triples": total, "issue_count": 0}
