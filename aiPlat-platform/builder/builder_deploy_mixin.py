"""Deploy/health/insight mixin for BuilderProjectService (P1-14 God Class split, 2026-08-25).

Extracted from builder_project_service.py — method bodies unchanged.
"""

from __future__ import annotations

import os  # P1-18 修复：deploy_to_app 原文件依赖模块级 import os，拆分后 Mixin 文件需自带
import time  # noqa: F401 — deploy_to_app/get_health_report 方法体使用（P1-14 拆分遗留）
from typing import Any, Dict  # P1-18 补充：签名注解 Dict/Any 需模块级导入（拆分遗留）



class BuilderDeployMixin:
    """部署 / 健康报告 / Agent 洞察 — 从 BuilderProjectService 拆出。"""
    async def deploy_to_app(self, project_id: str) -> Dict[str, Any]:
        from builder.builder_project_service import _deploy_to_app_for_project
        """Deploy pipeline output to the app layer."""
        proj = self._projects.get(project_id, {})
        # Sync pass_rate from final state if available
        _out_dir = os.path.join(os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")), "output", project_id)
        _final_path = os.path.join(_out_dir, "_final_state.json")
        if os.path.isfile(_final_path):
            import json as _json
            with open(_final_path, "r") as _fs:
                _final_state = _json.load(_fs)
            _code = _final_state.get("code", {})
            _arch = _final_state.get("architecture", {})
            _test_pr = _final_state.get("_test_pass_rate", None)
            _pr_source = "none"
            _pr_reason = ""
            if _test_pr is not None:
                _pr = _test_pr  # use real pytest results
                _pr_source = "real_pytest"
            else:
                # 估算：无真实测试结果时按产物完整度粗估（P2-4b 揭露：字数≠质量）
                _arch_ok = isinstance(_arch, dict) and len(_arch.get("raw_output", "") if isinstance(_arch, dict) else "") > 500
                _code_ok = isinstance(_code, dict) and len(_code.get("raw_output", "") if isinstance(_code, dict) else "") > 500
                _tests_ok = _final_state.get("_has_tests", False)
                if _arch_ok and _code_ok and _tests_ok:
                    _pr = 1.0
                elif _tests_ok and _code_ok:
                    _pr = 0.9
                elif _code_ok:
                    _pr = 0.7 if _arch_ok else 0.6
                elif _arch_ok:
                    _pr = 0.3
                else:
                    _pr = 0
                _pr_source = "estimated"
                _pr_reason = "no real pytest result — estimated from artifact length (arch>500/code>500/has_tests); treat as indicative only"
                # L2 (§3.8): user explicitly skipped the pytest gate → make the reason explicit
                if _final_state.get("_skip_pytest_gate"):
                    _pr_reason = ("user skipped pytest gate (L2 import mode) — "
                                  "pass_rate is estimated (LLM/artifact heuristics), NOT measured")
            if proj.get("runs"):
                proj["runs"][-1]["pass_rate"] = _pr
                proj["runs"][-1]["pass_rate_source"] = _pr_source
                if _pr_reason:
                    proj["runs"][-1]["pass_rate_estimate_reason"] = _pr_reason
                # L2 (§3.9 条件 2): Build-Log-style regenerated warning — no diff view in L2,
                # so every rewritten file must be surfaced for manual review.
                _modify = (proj.get("confirmed_prd") or {}).get("modify_files")
                if isinstance(_modify, list) and _modify:
                    _warns = [f"Warning: File {m.get('path')} has been regenerated, "
                              "please review diff manually." for m in _modify
                              if isinstance(m, dict) and m.get("path")]
                    if _warns:
                        proj["runs"][-1]["regenerated_warnings"] = _warns
                self._save_projects()
        # P1-18 证据门控（SBA 原则 10：产物完整/成功退出码 ≠ 阶段完成，2026-08-26）：
        # 真实 pytest 全失败（pass_rate=0）→ 拒绝部署，要求先修复测试。
        # 无测试证据（estimated / skip_pytest_gate）→ 放行但已标记风险（estimated 0 不阻断）。
        import logging as _log_dep
        _dl = _log_dep.getLogger("aiplat.builder")
        if _pr_source == "real_pytest" and _pr is not None and float(_pr) <= 0:
            _dl.warning("Deploy blocked by evidence gate: pass_rate=0 (real pytest all failed) project=%s",
                        project_id)
            return {"status": "error",
                    "detail": "测试证据显示 pass_rate=0（真实 pytest 全失败）——拒绝部署（证据门控）。"
                              "请先修复测试并重建，或确认后重试。"}
        deploy_dir = proj.get("deploy_dir", "") or await self.get_deploy_dir(project_id)
        return _deploy_to_app_for_project(project_id, deploy_dir or "", proj)
    async def get_agent_insight(self, agent_id: str) -> Dict[str, Any]:
        from builder.builder_project_service import _get_agent_insight_for
        """Get insight metrics for a single agent."""
        return _get_agent_insight_for(agent_id, self._projects)
    async def list_agent_insights(self) -> Dict[str, Any]:
        """Get insight metrics for all agents."""
        agent_ids: set = set()
        for pid, proj in self._projects.items():
            stages = proj.get("team_stages", []) or []
            for s in stages:
                aid = s.get("agent_id", "") if isinstance(s, dict) else getattr(s, "agent_id", "")
                if aid:
                    agent_ids.add(aid)
        insights: Dict[str, Any] = {}
        for aid in agent_ids:
            insights[aid] = await self.get_agent_insight(aid)
        return {"agents": insights, "total": len(insights)}
    async def refresh_agent_insights(self) -> Dict[str, Any]:
        """Refresh agent insight metrics."""
        result = await self.list_agent_insights()
        result["ok"] = True
        return result
    async def get_health_report(self, project_id: str) -> Dict[str, Any]:
        """Build health report from pipeline state, aggregating per-stage dimensional scores."""
        # Read from Core — single source of truth for pipeline state
        core_state = await self._get_state_via_core(project_id)
        state = (core_state.get("state", {}) if isinstance(core_state, dict) else {})
        proj = self._projects.get(project_id, {})
        stages = []
        all_dims: Dict[str, Dict] = {}
        for s in (proj.get("team_stages") or []):
            sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", "")
            hr = state.get(f"_health_report_{sid}") if sid else None
            if isinstance(hr, dict):
                stages.append(hr)
                for d in (hr.get("dimensions") or []):
                    dname = d.get("name", "")
                    if dname not in all_dims:
                        all_dims[dname] = dict(d)
                        all_dims[dname]["score"] = 0.0
                    all_dims[dname]["score"] += d.get("score", 0)
        # Average dimension scores across stages
        n = max(len(stages), 1)
        dim_list = []
        total_score = 0.0
        for d in all_dims.values():
            d["score"] = round(d["score"] / n, 1)
            total_score += d["score"] * d.get("weight", 1.0)
            dim_list.append(d)
        total_weight = sum(d.get("weight", 1.0) for d in dim_list) or 1.0
        overall = round(total_score / total_weight * 10, 1)
        # Build trend from run history
        trend = []
        for run in (proj.get("runs") or [])[-20:]:
            if isinstance(run, dict) and run.get("pass_rate"):
                trend.append({"run_id": run.get("run_id", ""), "score": round(float(run.get("pass_rate", 0)) * 100, 1),
                              "timestamp": run.get("started_at", "")})
        return {
            "project_id": project_id,
            "overall_score": overall,
            "dimensions": dim_list,
            "stages": stages,
            "trend": trend,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
