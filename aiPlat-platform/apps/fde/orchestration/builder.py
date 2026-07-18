"""FDE Builder Orchestrator — conversational Agent construction for FDE field work.

Matches 3Chat Builder's "chat with customer → auto-build Agent" pattern:
  1. _clarify() multi-turn needs clarification
  2. DomainRouter.classify() domain routing
  3. SkillRegistry + auto_fill agent configuration
  4. Builder.create_project() → Pipeline → deploy
  5. Only surfacing conflicts (skill overlap, domain mismatch) for FDE review

Usage:
  orchestrator = FDEBuilderOrchestrator(session_id)
  result = await orchestrator.run(requirement="客户需要售后问答Agent")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aiplat.fde.builder")


@dataclass
class BuilderSession:
    """State for a single FDE Builder session."""
    session_id: str
    requirement: str = ""
    domain_id: str = ""
    domain_confidence: float = 0.0
    suggested_skills: List[str] = field(default_factory=list)
    suggested_tools: List[str] = field(default_factory=list)
    agent_config: Dict[str, Any] = field(default_factory=dict)
    conflicts: List[Dict[str, str]] = field(default_factory=list)
    project_id: str = ""
    status: str = "init"  # init → clarifying → classified → configured → building → done


class FDEBuilderOrchestrator:
    """Orchestrates the full FDE Builder workflow.

    Takes natural language requirements from FDE-customer interaction,
    routes them through domain classification, auto-configures agents,
    and launches pipeline execution. Only surfaces conflict items for
    manual review — "FDE审核异常，不审核全部"。
    """

    def __init__(self, session_id: str):
        self.session = BuilderSession(session_id=session_id)

    # ── Step 1: Clarify requirements ──

    async def clarify(self, requirement: str, fde_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Use existing FDE clarification engine to understand customer needs.

        Returns structured clarification with questions and knowledge gaps.
        """
        try:
            from apps.fde.api.fde import _clarify
            from apps.fde.api.fde import _CLARIFY_CONTEXTS

            history = (fde_context or {}).get("history", [])
            result = await _clarify(
                context="builder_requirements",
                text=requirement[:2000],
                history=history,
            )

            self.session.requirement = requirement
            self.session.status = "clarifying"

            # Extract knowledge gaps from clarify result
            gaps = []
            if isinstance(result, dict) and result.get("knowledge_gaps"):
                for g in result["knowledge_gaps"][:5]:
                    gaps.append({
                        "concept": g.get("concept", ""),
                        "type": g.get("type", "missing_class"),
                        "detail": g.get("detail", ""),
                    })

            return {
                "status": "clarifying",
                "questions": result.get("questions", []),
                "next": result.get("next", "done"),
                "knowledge_gaps": gaps,
            }

        except Exception as e:
            logger.warning("clarify step failed: %s, proceeding with raw requirement", e)
            self.session.status = "clarifying"
            return {
                "status": "clarifying",
                "questions": [],
                "next": "done",
                "note": f"Clarification skipped: {e}",
            }

    # ── Step 2: Domain classification ──

    async def classify_domain(self) -> Dict[str, Any]:
        """Route customer requirement to the right knowledge domain."""
        try:
            from core.api.core_facade import DomainRouter  # via facade per CLAUDE.md §5.7

            router = DomainRouter()
            result = router.classify(self.session.requirement)
            self.session.domain_id = result.get("domain_id", "default")
            self.session.domain_confidence = result.get("confidence", 0.0)
            self.session.status = "classified"

            return {
                "status": "classified",
                "domain_id": self.session.domain_id,
                "confidence": self.session.domain_confidence,
                "tier": result.get("tier", "unknown"),
            }

        except Exception as e:
            logger.warning("domain classification failed: %s", e)
            self.session.domain_id = "default"
            self.session.domain_confidence = 0.0
            self.session.status = "classified"
            return {"status": "classified", "domain_id": "default", "confidence": 0, "note": str(e)}

    # ── Step 3: Suggest skills and auto-configure agent ──

    async def configure_agent(self, builder_svc=None) -> Dict[str, Any]:
        """Auto-suggest skills and build initial agent configuration.

        Returns agent config with conflict items (skill overlap, unresolved refs)
        that should be surfaced to FDE for review.
         """
        try:
            from core.api.core_facade import capability_health_report, build_capability_graph  # via facade per CLAUDE.md §5.7

            cg = build_capability_graph()
            ch = capability_health_report(cg)

            # Get top skills by usage in this domain
            used_skills = ch.get("signals", {}).get("used_skills", 0)
            all_skills = ch.get("signals", {}).get("skills", 0)

            # Suggested skills based on domain
            domain_key = self.session.domain_id.replace("-", "_")
            skills_by_domain = ch.get("issues", {}).get("skills_by_domain", {})
            self.session.suggested_skills = skills_by_domain.get(domain_key, [])[:8]

            # Top-used tools from capability graph
            tools_by_domain = ch.get("issues", {}).get("tools_by_domain", {})
            self.session.suggested_tools = tools_by_domain.get(domain_key, [])[:5]

            self.session.status = "configured"

            return {
                "status": "configured",
                "skills": self.session.suggested_skills,
                "tools": self.session.suggested_tools,
                "stats": {"total_skills": all_skills, "used_skills": used_skills},
            }

        except Exception as e:
            logger.warning("agent configuration failed: %s", e)
            self.session.status = "configured"
            return {"status": "configured", "skills": [], "tools": [], "note": str(e)}

    # ── Step 4: Auto-fill and detect conflicts ──

    async def auto_fill_and_review(self, previous_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Auto-fill agent config and produce a diff for FDE review.

        Only surfaces conflicts — FDE clicks "Apply" for each change.
        """
        try:
            import copy

            # Start with previous config or empty
            base = copy.deepcopy(previous_config or {})
            base.setdefault("skills", [])
            base.setdefault("tools", [])

            # Merge suggested skills/tools
            new_config = copy.deepcopy(base)
            for skill in self.session.suggested_skills:
                if skill not in new_config["skills"]:
                    new_config["skills"].append(skill)
            for tool in self.session.suggested_tools:
                if tool not in new_config["tools"]:
                    new_config["tools"].append(tool)
            new_config["domain_id"] = self.session.domain_id
            new_config["domain_confidence"] = self.session.domain_confidence

            # Detect conflicts (skill overlap with existing agent bindings)
            self.session.conflicts = []
            existing_skills = set(base.get("skills", []))

            # Check for skill overlap (two skills with similar names)
            all_skills = set(new_config.get("skills", []))
            for s1 in all_skills:
                for s2 in all_skills:
                    if s1 < s2 and self._is_overlap(s1, s2):
                        self.session.conflicts.append({
                            "type": "skill_overlap",
                            "detail": f"Skill '{s1}' 和 '{s2}' 职责可能重叠",
                            "a": s1,
                            "b": s2,
                        })

            # Check for new additions vs previous config
            added_skills = set(new_config.get("skills", [])) - existing_skills
            if added_skills:
                for sk in added_skills:
                    self.session.conflicts.append({
                        "type": "skill_added",
                        "detail": f"新增 Skill: {sk}",
                        "skill": sk,
                        "action": "review",
                    })

            self.session.agent_config = new_config

            return {
                "status": "review_ready",
                "config": new_config,
                "changes": {
                    "added_skills": list(added_skills),
                    "added_tools": list(set(new_config.get("tools", [])) - set(base.get("tools", []))),
                },
                "conflicts": [{"type": c["type"], "detail": c["detail"]} for c in self.session.conflicts],
                "conflict_count": len(self.session.conflicts),
            }

        except Exception as e:
            logger.warning("auto_fill failed: %s", e)
            return {"status": "error", "error": str(e)}

    # ── Step 5: Build and deploy via Platform Builder ──

    async def build_and_deploy(self) -> Dict[str, Any]:
        """Create project via Builder, start pipeline, and register as Studio app."""
        try:
            from builder.builder_project_service import _get_project_service
            from core.schemas_builder import ProjectCreateRequest

            svc = _get_project_service()
            proj = await svc.create_project(ProjectCreateRequest(
                name=f"FDE-{self.session.domain_id}-{self.session.session_id[:8]}",
                description=self.session.requirement[:500],
            ))
            self.session.project_id = proj.id
            self.session.status = "building"

            # Start pipeline in background
            await svc.start_pipeline(self.session.project_id)
            self.session.status = "done"

            return {
                "status": "done",
                "project_id": proj.id,
                "message": f"项目 {proj.id} 已创建，流水线已启动",
            }

        except Exception as e:
            logger.warning("build_and_deploy failed: %s", e)
            self.session.status = "error"
            return {"status": "error", "error": str(e)[:300]}

    # ── Full pipeline ──

    async def run(self, requirement: str, fde_context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run the full FDE Builder pipeline.

        Returns intermediate results at each step.
        """
        result = {"session_id": self.session.session_id, "steps": {}}

        # Step 1-2: Clarify and classify
        clarify = await self.clarify(requirement, fde_context)
        result["steps"]["clarify"] = clarify

        if clarify.get("next") != "done" and clarify.get("questions"):
            # Still clarifying — return questions to FDE
            result["status"] = "needs_clarification"
            return result

        # Step 3: Classify domain
        classify = await self.classify_domain()
        result["steps"]["classify"] = classify

        # Step 4: Configure agent
        config = await self.configure_agent()
        result["steps"]["configure"] = config

        # Step 5: Auto-fill and review
        review = await self.auto_fill_and_review()
        result["steps"]["review"] = review
        result["status"] = review["status"]
        result["config"] = review.get("config", {})
        result["conflicts"] = review.get("conflicts", [])
        result["conflict_count"] = review.get("conflict_count", 0)

        return result

    # ── Helpers ──

    @staticmethod
    def _is_overlap(a: str, b: str) -> bool:
        """Check if two skill names overlap semantically (simple substring check)."""
        a_lower = a.lower().replace("_", " ").replace("-", " ")
        b_lower = b.lower().replace("_", " ").replace("-", " ")
        if a_lower in b_lower or b_lower in a_lower:
            return True
        # Shared prefix check for compound names
        a_parts = set(a_lower.split())
        b_parts = set(b_lower.split())
        common = a_parts & b_parts
        return len(common) >= 2


__all__ = ["FDEBuilderOrchestrator", "BuilderSession"]
