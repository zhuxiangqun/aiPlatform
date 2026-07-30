"""

Business Value Calculator — five-dimension value measurement + business goal tracking.



Five dimensions:

  1. Efficiency  — token cost vs human equivalent

  2. Quality     — accuracy / pass-rate improvements

  3. Safety      — attacks blocked, circuits opened (risk avoidance)

  4. Innovation  — new task types, capability expansion

  5. Experience  — user satisfaction from implicit feedback



Three-audience translation:

  - CEO: total value + goal progress + strategic contribution

  - CFO: cost breakdown + savings + ROI ratio

  - PM:  accuracy trends + user satisfaction + error reduction



Integration:

  - EvolutionEngine Step 12: monthly value snapshot

  - DynamicRouter: goal-aware routing (strategy adjustment)

  - REST API: GET/POST/PUT/DELETE /api/core/value/{tenant}

"""

from __future__ import annotations



import json

import logging

import os

import time

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional



logger = logging.getLogger(__name__)





# ── Data models ──



@dataclass

class ValueEvent:

    """Single agent execution value snapshot."""

    run_id: str

    timestamp: float = field(default_factory=time.time)

    ai_cost_cny: float = 0.0

    human_equivalent_cost: float = 0.0

    efficiency_saved: float = 0.0

    skill_pass_rate: float = 0.0

    quality_value: float = 0.0

    attacks_blocked: int = 0

    safety_value: float = 0.0

    new_task_type: bool = False

    innovation_value: float = 0.0

    user_satisfaction: float = 0.0

    experience_value: float = 0.0





@dataclass

class BusinessGoal:

    """Business target definition."""

    goal_id: str

    description: str

    target_metric: str

    baseline_value: float

    target_value: float

    current_value: float = 0.0

    progress_pct: float = 0.0

    achieved: bool = False

    owner: str = ""

    period: str = ""





@dataclass

class MonthlyValueReport:

    """Monthly aggregated value report."""

    month: str

    tenant_id: str

    total_runs: int = 0

    efficiency: Dict[str, float] = field(default_factory=dict)

    quality: Dict[str, float] = field(default_factory=dict)

    safety: Dict[str, float] = field(default_factory=dict)

    innovation: Dict[str, float] = field(default_factory=dict)

    experience: Dict[str, float] = field(default_factory=dict)

    total_value_cny: float = 0.0

    value_breakdown_pct: Dict[str, float] = field(default_factory=dict)

    business_goals: List[Dict[str, Any]] = field(default_factory=list)





# ── Business Goal Tracker ──



class BusinessGoalTracker:

    """Business goal CRUD + auto-progress tracking."""



    def __init__(self):

        self._goals: Dict[str, BusinessGoal] = {}

        self._storage_path = os.path.expanduser("~/.aiplat/value/goals.json")

        self._load()



    def register(self, goal: BusinessGoal) -> str:

        self._goals[goal.goal_id] = goal

        self._save()

        return goal.goal_id



    def update(self, goal_id: str, current_value: float) -> Optional[BusinessGoal]:

        goal = self._goals.get(goal_id)

        if not goal:

            return None

        goal.current_value = current_value

        span = goal.target_value - goal.baseline_value

        if abs(span) > 0.001:

            goal.progress_pct = min(1.0, max(0.0,

                (current_value - goal.baseline_value) / span))

        else:

            goal.progress_pct = 1.0 if current_value >= goal.target_value else 0.0

        goal.achieved = goal.progress_pct >= 1.0

        self._save()

        return goal



    def get(self, goal_id: str) -> Optional[BusinessGoal]:

        return self._goals.get(goal_id)



    def get_all(self) -> List[BusinessGoal]:

        return list(self._goals.values())



    def get_status_for_routing(self) -> Dict[str, Any]:

        """Summary for GoalAwareRouter: which goals need attention."""

        lagging = [g.goal_id for g in self._goals.values() if g.progress_pct < 0.8]

        security_goals = [g.goal_id for g in self._goals.values()

                          if "risk" in g.description.lower() or "安全" in g.description]

        quality_goals = [g.goal_id for g in self._goals.values()

                         if "quality" in g.description.lower() or "质量" in g.description]

        return {

            "has_lagging_goal": len(lagging) > 0,

            "lagging_goal_ids": lagging,

            "security_incidents": sum(1 for g in self._goals.values()

                                       if g.progress_pct < 0.6 and g.goal_id in security_goals),

            "quality_trend": "declining" if any(

                g.progress_pct < 0.7 for g in self._goals.values() if g.goal_id in quality_goals

            ) else "stable",

        }



    def _save(self):

        try:

            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)

            with open(self._storage_path, "w") as f:

                json.dump({k: {

                    "goal_id": g.goal_id, "description": g.description,

                    "target_metric": g.target_metric, "baseline_value": g.baseline_value,

                    "target_value": g.target_value, "current_value": g.current_value,

                    "progress_pct": g.progress_pct, "achieved": g.achieved,

                    "owner": g.owner, "period": g.period,

                } for k, g in self._goals.items()}, f, indent=2)

        except Exception:

            logging.getLogger(__name__).debug('_save failed', exc_info=True)


    def _load(self):

        if not os.path.exists(self._storage_path):

            return

        try:

            with open(self._storage_path) as f:

                data = json.load(f)

            for k, v in data.items():

                self._goals[k] = BusinessGoal(**v)

        except Exception:

            logging.getLogger(__name__).debug('_load failed', exc_info=True)




# ── Value Calculator ──



class ValueCalculator:

    """Five-dimension value measurement + three-audience translation."""



    def __init__(self):

        self.goal_tracker = BusinessGoalTracker()

        self._cost_1M_input = float(os.getenv("AIPLAT_VALUE_COST_1M_INPUT", "1.0"))

        self._cost_1M_output = float(os.getenv("AIPLAT_VALUE_COST_1M_OUTPUT", "3.0"))

        self._human_cost_h = float(os.getenv("AIPLAT_VALUE_HUMAN_COST_H", "200"))

        self._min_per_task = float(os.getenv("AIPLAT_VALUE_MIN_PER_TASK", "15"))

        self._cost_per_error = float(os.getenv("AIPLAT_VALUE_COST_PER_ERROR", "500"))

        self._avg_fine = float(os.getenv("AIPLAT_VALUE_AVG_FINE", "50000"))

        self._new_cap_value = float(os.getenv("AIPLAT_VALUE_NEW_CAPABILITY", "10000"))

        self._prod_gain = float(os.getenv("AIPLAT_VALUE_PRODUCTIVITY_GAIN", "0.15"))

        self._report_path = os.path.expanduser("~/.aiplat/value/monthly.jsonl")



    def compute_run_value(self, run_id: str, *, events: List[Dict] = None,

                          pass_rate: float = 0.0, attacks: int = 0,

                          satisfaction: float = 0.0, new_task: bool = False) -> ValueEvent:

        """Compute five-dimension value for a single agent run."""

        events = events or []

        total_input = sum(e.get("input_tokens", 0) for e in events)

        total_output = sum(e.get("output_tokens", 0) for e in events)

        n_steps = len(events) or 1



        ai_cost = round(

            total_input / 1_000_000 * self._cost_1M_input +

            total_output / 1_000_000 * self._cost_1M_output, 4)

        human_cost = round(n_steps * (self._min_per_task / 60) * self._human_cost_h, 2)

        saved = round(human_cost - ai_cost, 2)



        return ValueEvent(

            run_id=run_id,

            ai_cost_cny=ai_cost,

            human_equivalent_cost=human_cost,

            efficiency_saved=max(saved, 0),

            skill_pass_rate=pass_rate,

            quality_value=round(pass_rate * self._cost_per_error, 2),

            attacks_blocked=attacks,

            safety_value=round(attacks * self._avg_fine, 2),

            new_task_type=new_task,

            innovation_value=self._new_cap_value if new_task else 0.0,

            user_satisfaction=satisfaction,

            experience_value=round(satisfaction * self._prod_gain * self._human_cost_h * 2000, 2),

        )



    async def compute_monthly(self, tenant_id: str, month: str) -> MonthlyValueReport:

        """Aggregate monthly value across all runs."""

        report = MonthlyValueReport(month=month, tenant_id=tenant_id)

        try:

            from core.services.execution_store import get_execution_store

            store = get_execution_store()

            runs = await self._get_monthly_runs(store, tenant_id, month)

        except Exception:

            logger.debug("Monthly run fetch skipped", exc_info=True)

            runs = []



        tot_eff = tot_qual = tot_safe = tot_inno = tot_exp = 0.0

        tot_atk = 0

        for rid in runs[:1000]:

            try:

                cost = await store.get_run_cost_summary(run_id=rid) if hasattr(store, "get_run_cost_summary") else {}

                events = await self._get_events(store, rid)

                v = self.compute_run_value(rid, events=events,

                    pass_rate=float(cost.get("success_rate", 0.8)),

                    attacks=int(cost.get("attacks_blocked", 0)),

                    satisfaction=float(cost.get("satisfaction", 0.85)))

                tot_eff += v.efficiency_saved

                tot_qual += v.quality_value

                tot_safe += v.safety_value

                tot_inno += v.innovation_value

                tot_exp += v.experience_value

                tot_atk += v.attacks_blocked

                report.total_runs += 1

            except Exception:

                continue



        report.efficiency = {"saved": round(tot_eff, 2)}

        report.quality = {"value": round(tot_qual, 2)}

        report.safety = {"value": round(tot_safe, 2), "attacks_blocked": tot_atk}

        report.innovation = {"value": round(tot_inno, 2)}

        report.experience = {"value": round(tot_exp, 2)}

        report.total_value_cny = round(tot_eff + tot_qual + tot_safe + tot_inno + tot_exp, 2)

        total = max(report.total_value_cny, 1)

        report.value_breakdown_pct = {

            "efficiency": round(tot_eff / total, 4),

            "quality": round(tot_qual / total, 4),

            "safety": round(tot_safe / total, 4),

            "innovation": round(tot_inno / total, 4),

            "experience": round(tot_exp / total, 4),

        }

        report.business_goals = [

            {"goal_id": g.goal_id, "description": g.description,

             "progress_pct": g.progress_pct, "achieved": g.achieved}

            for g in self.goal_tracker.get_all()

        ]

        return report



    # ── Three-audience translation ──



    def translate_for(self, report: MonthlyValueReport, audience: str) -> Dict[str, Any]:

        if audience == "ceo":

            return self._translate_ceo(report)

        elif audience == "cfo":

            return self._translate_cfo(report)

        return self._translate_pm(report)



    def _translate_ceo(self, r: MonthlyValueReport) -> Dict[str, Any]:

        return {

            "hero_number": f"¥{r.total_value_cny / 10000:.0f}万",

            "hero_label": "AI综合价值",

            "breakdown": [

                {"label": "效率贡献", "value": f"{r.value_breakdown_pct.get('efficiency',0)*100:.0f}%"},

                {"label": "安全贡献", "value": f"{r.value_breakdown_pct.get('safety',0)*100:.0f}%"},

                {"label": "质量贡献", "value": f"{r.value_breakdown_pct.get('quality',0)*100:.0f}%"},

            ],

            "goal_summary": r.business_goals,

            "total_runs": r.total_runs,

            "month": r.month,

        }



    def _translate_cfo(self, r: MonthlyValueReport) -> Dict[str, Any]:

        saved = r.efficiency.get("saved", 0)

        ai_cost = r.total_runs * 0.5  # approximate

        return {

            "hero_number": f"¥{saved:,.0f}",

            "hero_label": "月净节省",

            "detail_rows": [

                {"label": "AI推理成本(估)", "value": f"¥{ai_cost:,.2f}"},

                {"label": "人工等效节省", "value": f"¥{saved:,.2f}"},

                {"label": "投入产出比", "value": f"1:{saved / max(ai_cost, 0.01):.0f}"},

            ],

            "total_runs": r.total_runs,

            "month": r.month,

        }



    def _translate_pm(self, r: MonthlyValueReport) -> Dict[str, Any]:

        return {

            "hero_number": f"{r.total_runs}",

            "hero_label": "本月任务数",

            "detail_rows": [

                {"label": "安全拦截", "value": f"{r.safety.get('attacks_blocked',0)}次"},

                {"label": "业务目标数", "value": f"{len(r.business_goals)}个"},

            ],

            "goal_summary": r.business_goals,

            "month": r.month,

        }



    def _persist(self, report: MonthlyValueReport) -> None:

        try:

            os.makedirs(os.path.dirname(self._report_path), exist_ok=True)

            with open(self._report_path, "a") as f:

                f.write(json.dumps({

                    "month": report.month, "tenant_id": report.tenant_id,

                    "total_runs": report.total_runs,

                    "efficiency": report.efficiency, "quality": report.quality,

                    "safety": report.safety, "innovation": report.innovation,

                    "experience": report.experience,

                    "total_value_cny": report.total_value_cny,

                    "value_breakdown_pct": report.value_breakdown_pct,

                }, ensure_ascii=False) + "\n")

        except Exception:

            logging.getLogger(__name__).debug('_persist failed', exc_info=True)


    # ── Helpers ──



    async def _get_monthly_runs(self, store, tenant_id: str, month: str) -> List[str]:

        if hasattr(store, "get_monthly_runs"):

            return await store.get_monthly_runs(tenant_id, month)

        return []



    async def _get_events(self, store, run_id: str) -> list:

        if hasattr(store, "get_syscall_events"):

            return await store.get_syscall_events(run_id)

        return []





# ── Goal Prediction (V3.0) ──



def predict_goal_achievement(goal: BusinessGoal) -> Dict[str, Any]:

    """Linear trend extrapolation: predict if goal will be achieved by period end.



    Uses current progress vs elapsed time ratio:

      - If progress% > elapsed time% → on_track

      - If progress% ≈ elapsed time% → at_risk

      - If progress% < elapsed time% → behind



    Returns: {status, projected_value, days_to_target, recommendation}

    """

    span = goal.target_value - goal.baseline_value

    if abs(span) < 0.001:

        return {"status": "achieved" if goal.achieved else "unknown", "projected_value": goal.current_value,

                "days_to_target": 0, "recommendation": ""}



    elapsed_pct = 0.5  # assume mid-period if no time tracking

    progress = goal.progress_pct

    gap_ratio = progress / max(elapsed_pct, 0.01)



    if gap_ratio >= 1.1:

        status = "on_track"

        rec = ""

    elif gap_ratio >= 0.9:

        status = "at_risk"

        rec = "建议适度加速执行或启用提速Strategy"

    else:

        status = "behind"

        rec = "⚠️强烈建议启用提速Strategy: 减少审批环节, 增加并行执行"



    remaining = abs(span) * (1 - goal.progress_pct)

    daily_rate = abs(span) * progress / 30 if progress > 0 else 0.001

    days = int(remaining / daily_rate) if daily_rate > 0 else 999



    projected = goal.current_value + (daily_rate * (90 - 45))



    return {

        "status": status,

        "projected_value": round(projected, 2),

        "days_to_target": days,

        "recommendation": rec,

        "goal_id": goal.goal_id,

        "current_progress_pct": goal.progress_pct,

    }





# ── Global singleton ──



_value_calc: Optional[ValueCalculator] = None





def get_value_calculator() -> ValueCalculator:

    global _value_calc

    if _value_calc is None:

        _value_calc = ValueCalculator()

    return _value_calc

