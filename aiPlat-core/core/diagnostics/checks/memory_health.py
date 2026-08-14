"""Memory 四层分层健康检测。

扩展原有 _check_memory_compression() 为四层各自独立指标：
  - Working Memory: 当前 token 使用占比
  - Episodic Memory: 摘要命中率
  - Semantic Memory: FTS5 检索命中率 + 动态续期率
  - Task Skills: 晶体化通过率
"""

from typing import Any, Dict, Optional


async def check_memory_health() -> Dict[str, Any]:
    layers: Dict[str, Dict] = {}
    issues = []

    try:
        from core.harness.memory.manager import MemoryManager
        mgr = MemoryManager()

        # Layer 1: Working Memory — token usage ratio
        if hasattr(mgr, '_working') and mgr._working is not None:
            wm = mgr._working
            usage = getattr(wm, 'current_tokens', 0)
            limit = getattr(wm, 'max_tokens', 30000)
            ratio = usage / limit if limit > 0 else 0
            layers["working_memory"] = {"tokens": usage, "limit": limit, "ratio": round(ratio, 2)}
            if ratio > 0.9:
                issues.append({"layer": "working_memory", "severity": "warn",
                              "reason": f"token usage {ratio:.0%} exceeds 90%"})
        else:
            layers["working_memory"] = {"status": "unavailable"}

        # Layer 2: Episodic Memory — summary hit rate
        if hasattr(mgr, '_episodic') and mgr._episodic is not None:
            ep = mgr._episodic
            hits = getattr(ep, 'summary_hits', 0)
            misses = getattr(ep, 'summary_misses', 0)
            total = hits + misses
            hit_rate = hits / total if total > 0 else 0
            layers["episodic_memory"] = {"hits": hits, "misses": misses, "hit_rate": round(hit_rate, 2)}
        else:
            layers["episodic_memory"] = {"status": "unavailable"}

        # Layer 3: Semantic Memory — FTS5 hit rate
        if hasattr(mgr, '_semantic') and mgr._semantic is not None:
            sm = mgr._semantic
            searches = getattr(sm, 'total_searches', 0)
            hits_sm = getattr(sm, 'total_hits', 0)
            hit_rate_sm = hits_sm / searches if searches > 0 else 0
            layers["semantic_memory"] = {"searches": searches, "hits": hits_sm,
                                         "hit_rate": round(hit_rate_sm, 2)}
        else:
            layers["semantic_memory"] = {"status": "unavailable"}

        # Layer 4: Task Skills — crystallization pass rate
        try:
            from core.harness.memory.manager import TaskSkill
            skills = getattr(mgr, '_task_skills', [])
            if skills:
                crystallized = [s for s in skills if getattr(s, 'crystallized', False)]
                layers["task_skills"] = {"total": len(skills), "crystallized": len(crystallized)}
            else:
                layers["task_skills"] = {"total": 0, "note": "no task skills yet"}
        except ImportError:
            layers["task_skills"] = {"status": "unavailable"}

    except Exception as e:
        return {"status": "warn", "reason": f"MemoryManager access failed: {str(e)[:150]}"}

    if issues:
        return {"status": "warn", "layers": layers, "issues": issues}
    return {"status": "pass", "layers": layers}
