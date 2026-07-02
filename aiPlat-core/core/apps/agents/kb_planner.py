"""
KB Planner Agent — multi-step KB task execution.

Handles complex queries like "summarize this week's documents and generate a report"
by decomposing into sub-tasks: retrieve → analyze → summarize → format.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.harness.interfaces import AgentConfig, AgentContext, AgentResult, AgentStatus
from core.harness.knowledge.cost_estimator import estimate_query_cost


class KBPlannerAgent:
    """KB multi-step planning agent. Wraps the PlanExecuteAgent pattern
    with KB-specific tools: sys_kb_retrieve, sys_llm_generate, classify, summarize.
    """

    def __init__(self, config: AgentConfig, **kwargs):
        self._config = config
        self._model = kwargs.get("model")
        self._status = AgentStatus.IDLE

    async def execute(self, context: AgentContext) -> AgentResult:
        try:
            vars0 = dict(context.variables or {})
            scope = dict(vars0.get("scope") or {})
            tenant_id = str(vars0.get("tenant_id") or "default")
            task = ""
            if context.messages:
                task = str(context.messages[-1].get("content") or "").strip()
            if not task:
                task = str(vars0.get("message") or "").strip()
            if not task:
                return AgentResult(success=False, error="task_required")

            doc_ids = [str(x).strip() for x in (scope.get("doc_ids") or []) if str(x).strip()]

            # Phase C6: Cost-aware routing via shared core capability
            _cost = estimate_query_cost(task, {"doc_ids": doc_ids})

            # Step 1: Plan decomposition via LLM
            plan = await self._decompose_task(task, doc_ids, tenant_id)

            # Step 2: Execute each step sequentially
            results: List[Dict[str, Any]] = []
            for step in plan.get("steps", []):
                step_result = await self._execute_step(step, doc_ids, tenant_id, results)
                results.append({"step": step.get("action", "?"), "result": step_result})

            # Step 3: Aggregate and format final answer
            answer = await self._aggregate_results(task, plan, results, tenant_id, doc_ids)

            return AgentResult(
                success=True,
                output={"answer": answer, "plan": plan, "steps": results, "scope": scope},
                metadata={"agent": "kb_planner", "plan_steps": len(plan.get("steps", []))},
            )
        except Exception as e:
            self._status = AgentStatus.ERROR
            return AgentResult(success=False, error=str(e), metadata={"exception": type(e).__name__})
        finally:
            if self._status != AgentStatus.ERROR:
                self._status = AgentStatus.COMPLETED

    async def _decompose_task(self, task: str, doc_ids: List[str], tenant_id: str) -> Dict[str, Any]:
        """LLM decomposes task into steps."""
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.prompt_loader import _sync_resolve
        prompt = _sync_resolve("kb-planner",
            tools_desc=f"retrieve(查询词) — 从 {len(doc_ids)} 个文档检索；"
                       f"summarize(内容) — 总结；analyze(内容) — 分析；generate(内容) — 生成。",
            task=task,
        )
        resp = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("chat"), temperature=0.1, max_tokens=500,
        )
        import json, re
        raw = getattr(resp, "content", "") or str(resp)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"steps": [{"action": "retrieve", "query": task}]}

    async def _execute_step(self, step: dict, doc_ids: List[str], tenant_id: str, prev: list) -> str:
        action = str(step.get("action", "retrieve")).lower()
        if action in ("retrieve", "search"):
            query = str(step.get("query", "相关文档"))
            from core.api.facades.kb_facade import kb_retrieve
            results = kb_retrieve(query=query, doc_ids=doc_ids, tenant_id=tenant_id, top_k=5)
            return "\n\n---\n\n".join(r["text"] for r in results) if results else "[无匹配内容]"
        elif action in ("analyze", "summarize", "generate"):
            content = str(step.get("content", "\n".join(p.get("result", "") for p in prev[-3:])))
            from core.harness.knowledge.doc_compressor import compress_retrieved_docs
            content = compress_retrieved_docs(content, model_name=best_model_for_purpose("chat"))
            from core.harness.syscalls.llm import sys_llm_generate
            resp = await sys_llm_generate(
                None, [{"role": "user", "content": f"请{action}以下内容：\n{content}"}],
                model_name=best_model_for_purpose("chat"), temperature=0.3, max_tokens=1000,
            )
            return getattr(resp, "content", "") or str(resp)
        return str(step)

    async def _aggregate_results(self, task: str, plan: dict, results: list, tenant_id: str, doc_ids: list) -> str:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.knowledge.doc_compressor import compress_retrieved_docs
        steps_text = "\n".join(f"Step: {r['step']}\nResult: {r['result'][:500]}" for r in results)
        steps_text = compress_retrieved_docs(steps_text, model_name=best_model_for_purpose("chat"))
        resp = await sys_llm_generate(
            None, [{"role": "user", "content": f"基于以下中间结果，完成原始任务。\n\n任务：{task}\n\n中间结果：\n{steps_text}\n\n请给出最终答案："}],
            model_name=best_model_for_purpose("chat"), temperature=0.3, max_tokens=2000,
        )
        return getattr(resp, "content", "") or str(resp)
