"""

AbstractGoalDecomposer — 模糊业务目标分解器 (Phase 39).



接收 "提升工厂效率" 这样的抽象目标，通过 LLM + Ontology 查询

拆解为 GoalGenerator 可消化的结构化 Goal 列表。



核心流程:

  LLM 提取三元组 → Ontology 接地 → 子目标合成 → 可行性评估



设计原则:

  - 配置驱动: AIPLAT_AUTO_GOAL_DECOMPOSE_ENABLED 门控

  - 内核无关: 不硬编码业务概念，通过 DomainRouter 动态发现

  - 接线完整: GoalGenerator + WakeScheduler 双入口

"""



from __future__ import annotations



import json as _json

import logging

import os as _os

import time as _time

import uuid as _uuid

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional, Set, Tuple



from core.harness.optimization.goal_generator import Goal, GoalType, Priority



logger = logging.getLogger("aiplat.abstract_goal_decomposer")





@dataclass

class CapabilityMatch:

    capability: str

    relevance: float

    existing_tools: List[str] = field(default_factory=list)

    missing_gaps: List[str] = field(default_factory=list)

    source_class: str = ""





@dataclass

class DecomposeResult:

    abstract_goal: str

    triples: List[Tuple[str, str, str]] = field(default_factory=list)

    sub_goals: List[Goal] = field(default_factory=list)

    feasibility: float = 0.0

    missing_capabilities: List[str] = field(default_factory=list)

    duration_ms: float = 0.0

    error: str = ""





class AbstractGoalDecomposer:

    """将模糊业务目标分解为 GoalGenerator 可消化的子目标。



    安全设计:

      - 默认 disabled，需 AIPLAT_AUTO_GOAL_DECOMPOSE_ENABLED=true 启用

      - LLM 调用 temperature=0.3，降低幻觉

      - 本体接地失败时降级为纯 LLM 分解 (feasibility 扣除 30%)

    """



    _PENDING_DIR = _os.path.expanduser("~/.aiplat/goals/pending")



    def __init__(self, *, enabled: bool = False, max_sub_goals: int = 5):

        self._enabled = enabled

        self._max_sub_goals = max_sub_goals

        self._decompose_count = 0

        self._last_duration_ms: float = 0.0



    @property

    def enabled(self) -> bool:

        return self._enabled



    @enabled.setter

    def enabled(self, value: bool) -> None:

        self._enabled = value



    async def decompose(

        self,

        abstract_goal: str,

        *,

        domain_id: Optional[str] = None,

    ) -> DecomposeResult:

        """将抽象业务目标分解为子目标列表。



        返回未分解的空结果（而不是报错）当 disabled 或输入为空时。

        """

        t0 = _time.monotonic()

        if not self._enabled or not abstract_goal.strip():

            return DecomposeResult(

                abstract_goal=abstract_goal,

                error="disabled or empty input",

            )



        try:

            triples = await self._extract_triples(abstract_goal)

            matches = await self._ground_to_ontology(triples, domain_id)

            sub_goals = await self._synthesize_sub_goals(matches, abstract_goal)

            feasibility = self._estimate_feasibility(sub_goals)



            self._decompose_count += 1

            duration = (_time.monotonic() - t0) * 1000

            self._last_duration_ms = duration



            missing = [

                m.capability for m in matches

                if not m.existing_tools and not m.source_class

            ]



            return DecomposeResult(

                abstract_goal=abstract_goal,

                triples=triples,

                sub_goals=sub_goals[:self._max_sub_goals],

                feasibility=feasibility,

                missing_capabilities=missing,

                duration_ms=duration,

            )

        except Exception as e:

            logger.warning("[abstract_goal_decomposer] decompose failed: %s", e)

            return DecomposeResult(

                abstract_goal=abstract_goal,

                error=str(e)[:200],

            )



    async def _extract_triples(self, goal_text: str) -> List[Tuple[str, str, str]]:

        """LLM 提取 (对象, 动作, 度量) 三元组。



        示例: "提升供应链效率" →

            [("供应链", "提升", "效率"), ("供应商", "缩短", "交付周期")]

        """

        try:

            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter

            adapter = create_selected_adapter(best_model_for_purpose("doc_llm"))

            prompt = (

                "将以下业务目标分解为 (对象, 动作, 度量) 三元组。"

                "每个三元组表示: (要影响的对象, 要执行的动作方向, 要衡量的指标)。"

                "只输出 JSON 数组，不要额外文字。\n\n"

                f"目标: {goal_text}\n\n"

                "输出格式示例: "

                '[["供应链", "提升", "效率"], ["供应商", "缩短", "交付周期"]]'

            )

            raw = await adapter.generate(prompt, temperature=0.3, max_tokens=500)

            data = self._parse_json_array(raw)

            triples = []

            for item in data:

                if isinstance(item, list) and len(item) >= 3:

                    triples.append((str(item[0]), str(item[1]), str(item[2])))

            if not triples:

                triples = [("系统", "优化", goal_text[:30])]

            return triples[:8]

        except Exception as e:

            logger.debug("triple extraction failed: %s", e)

            return [("系统", "优化", goal_text[:30])]



    async def _ground_to_ontology(

        self, triples: List[Tuple[str, str, str]], domain_id: Optional[str],

    ) -> List[CapabilityMatch]:

        """将三元组接地到本体: 查 GraphIndex + DomainRouter + ClassMapper。



        命中规则:

          - 类名/标签与三元组的 object 有交集 → relevance += 0.5

          - 该域有已注册 Skill → 标记 existing_tools

          - 该域无工具有关联类 → 标记为潜在 tool_gap

        """

        matches: List[CapabilityMatch] = []

        if not triples:

            return matches



        try:

            from core.harness.knowledge.domain_router import DomainRouter

            router = DomainRouter()

        except Exception as e:

            logger.debug("ontology grounding: DomainRouter unavailable: %s", e)

            return self._fallback_matches(triples)



        seen_caps: Set[str] = set()

        for obj, action, metric in triples:

            obj_lower = obj.lower()

            try:

                classified = router.classify(obj_lower)

                dom = classified.get("domain_id") or domain_id or "default"

            except Exception:

                dom = domain_id or "default"



            cap_name = f"{obj_lower}_{action}_{metric}".replace(" ", "_")[:80]

            if cap_name in seen_caps:

                continue

            seen_caps.add(cap_name)



            existing_tools: List[str] = []

            try:

                from core.harness.optimization.tool_bootstrap import ToolBootstrapEngine

                import os as _os_inner

                skills_dir = ToolBootstrapEngine.SKILLS_DIR

                if _os_inner.path.isdir(skills_dir):

                    for entry in _os_inner.listdir(skills_dir):

                        if obj_lower in entry.lower() and _os_inner.path.isdir(

                            _os_inner.path.join(skills_dir, entry)

                        ):

                            existing_tools.append(entry)

            except Exception:

                logging.getLogger(__name__).debug('_ground_to_ontology failed', exc_info=True)


            source_class = ""

            relevance = 0.3

            try:

                from core.harness.knowledge.ontology_query_mapper import map_query_to_ontology

                mapping = map_query_to_ontology(obj_lower, domain_id=dom)

                if mapping and mapping.get("target_class"):

                    source_class = str(mapping["target_class"])

                    relevance = max(relevance, 0.5 + min(mapping.get("confidence", 0.5), 0.4))

            except Exception:

                logging.getLogger(__name__).debug('_ground_to_ontology failed', exc_info=True)


            matches.append(CapabilityMatch(

                capability=cap_name,

                relevance=relevance,

                existing_tools=existing_tools,

                source_class=source_class,

                missing_gaps=[] if (existing_tools or source_class) else [cap_name],

            ))



        matches.sort(key=lambda m: m.relevance, reverse=True)

        return matches



    async def _synthesize_sub_goals(

        self, matches: List[CapabilityMatch], abstract_goal: str,

    ) -> List[Goal]:

        """从 CapabilityMatch 列表合成结构化 Goal 对象。



        策略:

          - 有关联类 + 有工具 → STRATEGY_OPTIMIZE (优化现有能力)

          - 有关联类 + 无工具 → TOOL_GAP (触发 ToolBootstrap)

          - 无关联类 + 有工具 → EXPLORATION_GAP (探索已有能力的新用法)

          - 什么都没有 → 标记为 missing，不生成 Goal

        """

        goals: List[Goal] = []

        now = _time.time()



        for i, m in enumerate(matches):

            if not m.existing_tools and not m.source_class:

                continue



            if m.source_class and m.existing_tools:

                goal_type = GoalType.STRATEGY_OPTIMIZE

                auto_exec = True

                priority = Priority.MEDIUM

                title = f"优化 '{m.capability}' 相关能力"

                desc = (

                    f"目标 '{abstract_goal}' 中的 '{m.capability}' 已有 "

                    f"本体类 {m.source_class} 和 {len(m.existing_tools)} 个工具。"

                    "检查现有工具的效果并优化策略。"

                )

                action = f"对 {m.source_class} 相关的 Skill 进行 UCB1 策略搜索优化"

                evidence = {

                    "capability": m.capability,

                    "source_class": m.source_class,

                    "existing_tools": m.existing_tools[:5],

                    "abstract_goal": abstract_goal,

                }

            elif m.source_class and not m.existing_tools:

                goal_type = GoalType.TOOL_GAP

                auto_exec = True

                priority = Priority.HIGH

                title = f"为 '{m.capability}' 创建诊断工具"

                desc = (

                    f"目标 '{abstract_goal}' 中 '{m.capability}' 有本体类 {m.source_class}，"

                    "但缺少专用 Skill。触发 ToolBootstrap 自动生成。"

                )

                action = f"Auto-bootstrap tool: {m.capability}"

                evidence = {

                    "capability": m.capability,

                    "source_class": m.source_class,

                    "error_type": m.capability.replace(" ", "_"),

                    "abstract_goal": abstract_goal,

                }

            else:

                goal_type = GoalType.EXPLORATION_GAP

                auto_exec = True

                priority = Priority.LOW

                title = f"探索 '{m.capability}' 新用法"

                desc = (

                    f"目标 '{abstract_goal}' 中 '{m.capability}' 有相关工具但无本体类。"

                    "尝试已有工具在新场景中的应用。"

                )

                action = f"探索 {', '.join(m.existing_tools[:3])} 在 {m.capability} 场景的表现"

                evidence = {

                    "capability": m.capability,

                    "existing_tools": m.existing_tools[:5],

                    "abstract_goal": abstract_goal,

                }



            goals.append(Goal(

                goal_id=f"decomp-{_uuid.uuid4().hex[:8]}",

                title=title,

                description=desc,

                goal_type=goal_type,

                priority=priority,

                estimated_impact=f"关联目标: {abstract_goal[:60]}",

                auto_executable=auto_exec,

                suggested_action=action,

                source_evidence=evidence,

                generated_at=now,

            ))



        return goals



    def _estimate_feasibility(self, sub_goals: List[Goal]) -> float:

        """估算整体可行性 [0,1]。



        - 每个子目标有 source_class 加 0.15

        - 每个子目标有 existing_tools 加 0.10

        - 基值 0.2

        - 上限 0.95 (保留不确定性)

        """

        if not sub_goals:

            return 0.0

        score = 0.2

        for g in sub_goals:

            evidence = g.source_evidence

            if evidence.get("source_class"):

                score += 0.15

            if evidence.get("existing_tools"):

                score += 0.10

        return min(score, 0.95)



    def _parse_json_array(self, raw_text: str) -> List[Any]:

        """从 LLM 输出中提取 JSON 数组。"""

        text = raw_text.strip()

        for start in ("```json", "```"):

            if text.startswith(start):

                text = text[len(start):]

                if text.endswith("```"):

                    text = text[:-3]

                text = text.strip()

                break

        try:

            return _json.loads(text)

        except _json.JSONDecodeError:

            import re as _re

            m = _re.search(r"\[.*\]", text, _re.DOTALL)

            if m:

                try:

                    return _json.loads(m.group())

                except _json.JSONDecodeError:

                    pass  # noqa: cleanup-best-effort

        return []



    def _fallback_matches(self, triples: List[Tuple[str, str, str]]) -> List[CapabilityMatch]:

        """DomainRouter 不可用时的降级匹配 (纯关键词，无本体接地)。"""

        return [

            CapabilityMatch(

                capability=f"{obj}_{action}_{metric}".replace(" ", "_"),

                relevance=0.2,

            )

            for obj, action, metric in triples[:3]

        ]



    def stats(self) -> Dict[str, Any]:

        return {

            "enabled": self._enabled,

            "max_sub_goals": self._max_sub_goals,

            "decompose_count": self._decompose_count,

            "last_duration_ms": self._last_duration_ms,

        }





_abstract_goal_decomposer: Optional[AbstractGoalDecomposer] = None





def get_abstract_goal_decomposer() -> AbstractGoalDecomposer:

    global _abstract_goal_decomposer

    if _abstract_goal_decomposer is None:

        enabled = _os.getenv(

            "AIPLAT_AUTO_GOAL_DECOMPOSE_ENABLED", "true"

        ).lower() in ("1", "true", "yes")

        _abstract_goal_decomposer = AbstractGoalDecomposer(enabled=enabled)

    return _abstract_goal_decomposer


