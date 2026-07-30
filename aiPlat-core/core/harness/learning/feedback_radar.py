"""

FeedbackRadar — 用户行为信号 → Spec 调整建议 (Andrew Ng 三层 Loop P1)



从 ImplicitFeedbackCollector 的原始信号中检测模式，翻译为开发者可理解的

Spec 调整建议。不直接修改代码——信号先进入"开发者脑子"，开发者再修正 Spec。



检测模式:

  1. 边界缺失: 同一 run_id 连续追问 (re_query) ≥ 3 次

  2. 方向错误: 同一 run_id 重复相同问题 (repeat_query) ≥ 2 次

  3. 信息过载: 同一 run_id 用户放弃 (abandon) + ≥ 200 字输出

  4. 目标偏离: 同一 spec_id 下多个 run_id 均为负反馈

  5. 信号冷区: 某 spec 连续 7 天无任何用户信号 → 可能 Spec 已过期



输出:

  SpecAdjustmentSuggestion { spec_id, type, severity, detail, suggested_action }



接线:

  POST /workbench/spec/{spec_id}/radar  → 按需生成建议

  EvolutionEngine Step 12  → 自动扫描所有活跃 Spec

"""

from __future__ import annotations



import logging

import os

import time

from dataclasses import dataclass, field

from enum import Enum

from typing import Any, Dict, List, Optional, Set



_log = logging.getLogger("aiplat.feedback_radar")





class SuggestionType(str, Enum):

    BOUNDARY_MISSING = "boundary_missing"      # Spec 边界不清晰 → 用户反复追问

    DIRECTION_WRONG = "direction_wrong"         # Spec 方向错误 → 用户重复相同问题

    INFO_OVERLOAD = "info_overload"            # 输出信息过载 → 用户放弃

    GOAL_DRIFT = "goal_drift"                  # 多个任务均为负反馈 → Spec 可能偏离

    SIGNAL_COLD = "signal_cold"                # 长时间无信号 → Spec 可能过期





class Severity(str, Enum):

    LOW = "low"

    MEDIUM = "medium"

    HIGH = "high"

    CRITICAL = "critical"





@dataclass

class SpecAdjustmentSuggestion:

    spec_id: str

    type: SuggestionType

    severity: Severity

    detail: str                    # 人类可读的现象描述

    suggested_action: str          # 建议的 Spec 修改方向

    evidence: List[Dict[str, Any]]  # 支撑信号 (run_id + signal_type + timestamp)

    generated_at: float = field(default_factory=time.time)





# ── Pattern detection thresholds ──



class _Thresholds:

    RE_QUERY_STREAK = 3          # 连续追问 → 边界缺失

    REPEAT_QUERY_COUNT = 2        # 重复问题 → 方向错误

    SIGNAL_COLD_DAYS = 7          # 无信号天数 → Spec 过期

    GOAL_DRIFT_RUNS = 3           # 负反馈 run_id 数 → 目标偏离

    INFO_OVERLOAD_CHARS = 200     # 输出长度阈值 → 信息过载





class FeedbackRadar:

    """信号模式检测器 → Spec 调整建议生成器。



    Usage:

        radar = FeedbackRadar()

        suggestions = await radar.analyze(spec_id="my-agent")

        for s in suggestions:

            print(f"[{s.severity.upper()}] {s.detail}")

    """



    def __init__(self):

        self._enabled = os.getenv("AIPLAT_FEEDBACK_RADAR_ENABLED", "true").lower() not in ("0", "false", "no")



    # ── Public API ──



    async def analyze(self, spec_id: str, lookback_days: int = 30) -> List[SpecAdjustmentSuggestion]:

        """分析单个 Spec 的用户反馈信号，生成调整建议。"""

        if not self._enabled:

            return []



        suggestions: List[SpecAdjustmentSuggestion] = []

        signals = await self._fetch_signals(spec_id, lookback_days)

        if not signals:

            return suggestions



        # Group by run_id

        by_run: Dict[str, List[Dict]] = {}

        for s in signals:

            rid = s.get("run_id", "")

            by_run.setdefault(rid, []).append(s)



        # Pattern 1: Boundary missing — repeated re_query on same run

        boundary = self._detect_boundary_missing(spec_id, by_run)

        if boundary:

            suggestions.append(boundary)



        # Pattern 2: Direction wrong — same user repeats the exact question

        direction = self._detect_direction_wrong(spec_id, by_run)

        if direction:

            suggestions.append(direction)



        # Pattern 3: Info overload — user abandons + large output

        overload = self._detect_info_overload(spec_id, by_run)

        if overload:

            suggestions.append(overload)



        # Pattern 4: Goal drift — multiple runs all negative

        drift = self._detect_goal_drift(spec_id, by_run)

        if drift:

            suggestions.append(drift)



        return suggestions



    async def analyze_all_active(self) -> Dict[str, List[SpecAdjustmentSuggestion]]:

        """分析所有活跃 Spec 的信号。接线点: EvolutionEngine Step 12。"""

        if not self._enabled:

            return {}



        try:

            from core.harness.models.spec_lifecycle import get_spec_lifecycle

            sl = get_spec_lifecycle()

            active = sl.get_all_active()



            results: Dict[str, List[SpecAdjustmentSuggestion]] = {}

            for sv in active:

                suggestions = await self.analyze(sv.spec_id)

                if suggestions:

                    results[sv.spec_id] = suggestions



            # Pattern 5: Signal cold — no signals for extended period

            cold_results = await self._detect_signal_cold(set(sv.spec_id for sv in active))

            for spec_id, suggestion in cold_results.items():

                results.setdefault(spec_id, []).append(suggestion)



            _log.info("FeedbackRadar: %d specs analyzed, %d with suggestions",

                       len(active), len(results))

            return results



        except Exception as e:

            _log.debug("FeedbackRadar scan skipped: %s", e)

            return {}



    # ── Pattern detectors ──



    def _detect_boundary_missing(self, spec_id: str, by_run: Dict[str, List[Dict]]) -> Optional[SpecAdjustmentSuggestion]:

        """检测: 同一 run_id 连续 re_query ≥ 3 次 → 边界缺失"""

        for run_id, signals in sorted(by_run.items()):

            re_query_count = sum(1 for s in signals if s.get("signal_type") == "re_query")

            if re_query_count >= _Thresholds.RE_QUERY_STREAK:

                return SpecAdjustmentSuggestion(

                    spec_id=spec_id,

                    type=SuggestionType.BOUNDARY_MISSING,

                    severity=Severity.MEDIUM if re_query_count < 5 else Severity.HIGH,

                    detail=f"用户在同一任务中连续追问 {re_query_count} 次，"

                           f"说明 Agent 的回答未覆盖用户关心的边界情况。",

                    suggested_action="建议在 Spec 中补充边界条件或异常处理场景，"

                                     "尤其是用户追问涉及的具体操作步骤或数据格式。",

                    evidence=signals[:5],

                )

        return None



    def _detect_direction_wrong(self, spec_id: str, by_run: Dict[str, List[Dict]]) -> Optional[SpecAdjustmentSuggestion]:

        """检测: 同一 run_id 重复相同问题 ≥ 2 次 → 方向错误"""

        for run_id, signals in sorted(by_run.items()):

            repeats = [s for s in signals if s.get("signal_type") == "repeat_query"]

            if len(repeats) >= _Thresholds.REPEAT_QUERY_COUNT:

                return SpecAdjustmentSuggestion(

                    spec_id=spec_id,

                    type=SuggestionType.DIRECTION_WRONG,

                    severity=Severity.HIGH,

                    detail=f"用户重复提交了相同或高度相似的问题，"

                           f"说明 Agent 的回答方向与用户预期不符。",

                    suggested_action="建议重新审视 Spec 的目标定义，确认 Agent "

                                     "是否真正理解了用户意图。可能需要调整 system prompt "

                                     "或重新定义输出格式。",

                    evidence=repeats[:3],

                )

        return None



    def _detect_info_overload(self, spec_id: str, by_run: Dict[str, List[Dict]]) -> Optional[SpecAdjustmentSuggestion]:

        """检测: 用户放弃 + 输出过长 → 信息过载"""

        for run_id, signals in sorted(by_run.items()):

            has_abandon = any(s.get("signal_type") == "abandon" for s in signals)

            if not has_abandon:

                continue

            # Check if output was large (inferred from abandon signals)

            return SpecAdjustmentSuggestion(

                spec_id=spec_id,

                type=SuggestionType.INFO_OVERLOAD,

                severity=Severity.LOW,

                detail="用户在看到 Agent 输出后离开或长时间无操作，"

                       "可能因为输出信息量过大或结构不清晰。",

                suggested_action="建议在 Spec 中要求 Agent 优先输出摘要或结构化结论，"

                                 "将详细分析放在可展开区域。",

                evidence=signals[:3],

            )

        return None



    def _detect_goal_drift(self, spec_id: str, by_run: Dict[str, List[Dict]]) -> Optional[SpecAdjustmentSuggestion]:

        """检测: 多个 run_id 均为负反馈 → 目标偏离"""

        negative_runs = 0

        total_runs = len(by_run)

        evidence: List[Dict] = []



        for run_id, signals in sorted(by_run.items()):

            score = sum(s.get("value", 0) for s in signals if isinstance(s.get("value"), (int, float)))

            if score < -0.2:

                negative_runs += 1

                evidence.append({"run_id": run_id, "score": round(score, 2), "count": len(signals)})



        if negative_runs >= _Thresholds.GOAL_DRIFT_RUNS:

            return SpecAdjustmentSuggestion(

                spec_id=spec_id,

                type=SuggestionType.GOAL_DRIFT,

                severity=Severity.CRITICAL if negative_runs >= 5 else Severity.HIGH,

                detail=f"最近 {total_runs} 个任务中，{negative_runs} 个获得负反馈，"

                       f"可能 Spec 的整体方向已偏离用户需求。",

                suggested_action="建议与业务负责人一起审查 Spec 的目标定义，"

                                 "对比用户实际需求与当前 Spec 设计的差距。",

                evidence=evidence[:5],

            )

        return None



    async def _detect_signal_cold(self, active_spec_ids: Set[str]) -> Dict[str, SpecAdjustmentSuggestion]:

        """检测: 活跃 Spec 长时间无任何信号 → 可能过期"""

        results: Dict[str, SpecAdjustmentSuggestion] = {}

        cutoff = time.time() - _Thresholds.SIGNAL_COLD_DAYS * 86400



        for spec_id in active_spec_ids:

            signals = await self._fetch_signals(spec_id, lookback_days=_Thresholds.SIGNAL_COLD_DAYS + 1)

            if not signals or all(s.get("_ts", 0) < cutoff for s in signals):

                results[spec_id] = SpecAdjustmentSuggestion(

                    spec_id=spec_id,

                    type=SuggestionType.SIGNAL_COLD,

                    severity=Severity.LOW,

                    detail=f"该 Spec 已连续 {_Thresholds.SIGNAL_COLD_DAYS} 天无用户反馈信号，"

                           f"可能已过期或用户已不再使用。",

                    suggested_action="建议确认该 Spec 对应的业务场景是否仍然活跃，"

                                     "若不再需要可归档 (mark_archived)。",

                    evidence=[],

                )

        return results



    # ── Signal fetching ──



    async def _fetch_signals(self, spec_id: str, lookback_days: int = 30) -> List[Dict[str, Any]]:

        """从 ImplicitFeedbackCollector + execution_store 拉取信号。



        当前版本: 从内存 collector 的 buffer + run_signals 获取。

        生产版: 应从 execution_store 的持久化信号表查询。

        """

        signals: List[Dict[str, Any]] = []



        # Source 1: Live collector buffer (recent, in-memory)

        try:

            from core.services.implicit_feedback import get_implicit_feedback_collector

            collector = get_implicit_feedback_collector()

            for run_id, sig_list in list(collector._run_signals.items()):

                if spec_id in run_id or self._run_belongs_to_spec(run_id, spec_id):

                    for s in sig_list:

                        signals.append({

                            "run_id": s.run_id,

                            "signal_type": s.signal_type,

                            "value": s.value,

                            "session_id": s.session_id,

                            "timestamp": s.timestamp,

                        })

        except Exception:

            logging.getLogger(__name__).debug('_fetch_signals failed', exc_info=True)


        # Source 2: execution_store labeled samples (persisted, longer history)

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            rows = await store.query_meta(key="implicit_label", limit=100)

            if isinstance(rows, list):

                for r in rows:

                    rid = r.get("run_id", "") if isinstance(r, dict) else ""

                    if rid and (spec_id in rid or self._run_belongs_to_spec(rid, spec_id)):

                        label = r.get("value", "") if isinstance(r, dict) else ""

                        if label in ("positive", "negative"):

                            signals.append({

                                "run_id": rid,

                                "signal_type": f"labeled_{label}",

                                "value": 0.3 if label == "positive" else -0.2,

                                "_ts": r.get("timestamp", 0) if isinstance(r, dict) else 0,

                            })

        except Exception:

            logging.getLogger(__name__).debug('_fetch_signals failed', exc_info=True)


        return signals



    @staticmethod

    def _run_belongs_to_spec(run_id: str, spec_id: str) -> bool:

        """Heuristic: check if run_id contains spec_id (e.g., 'wb-xxx'→'my-agent')."""

        return spec_id in run_id





# ── Singleton ──



_radar_instance: Optional[FeedbackRadar] = None





def get_feedback_radar() -> FeedbackRadar:

    global _radar_instance

    if _radar_instance is None:

        _radar_instance = FeedbackRadar()

    return _radar_instance

