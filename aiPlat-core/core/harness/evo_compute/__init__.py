"""受控演化计算底座（Phase 0 / G0）。

职责：
  - Genome Registry（可进化对象边界）
  - Candidate 状态机（架构 §6 SSOT）
  - Fitness 多目标 + Pareto→ranked（§4.3.1）
  - 离线沙箱：接受预计算指标，评估一个候选并留证据
  - 闭环成熟度 KPI 基线落盘（工作假设 ≠ 已测）
  - 三试点 genome、预算硬上限、安全边界签字、夹具回放、G0 出口就绪

非目标：
  - 不接 DE/ES 种群循环、不写生产配置、不宣称 E2/L4/认证
  - 不替代 ``evolution_engine.py`` 夜间 Skill 流水线
  - 不自动批准预算/安全边界
"""

from core.harness.evo_compute.baseline import (
    evaluate_closed_loop_baseline_gate,
    measure_closed_loop_baseline,
    run_closed_loop_baseline_suite,
)
from core.harness.evo_compute.budget import (
    approve_budget,
    check_budget,
    default_budget_policy,
    get_budget_policy,
    set_budget_policy,
)
from core.harness.evo_compute.exit_readiness import evaluate_g0_exit_readiness
from core.harness.evo_compute.fitness import rank_candidates
from core.harness.evo_compute.genome_registry import (
    get_genome,
    list_genomes,
    register_genome,
)
from core.harness.evo_compute.pilots import (
    list_pilot_genome_ids,
    pilot_genome_specs,
    register_pilot_genomes,
)
from core.harness.evo_compute.replay import (
    aggregate_partition_metrics,
    default_replay_fixture,
    replay_candidate_offline,
)
from core.harness.evo_compute.safety import (
    default_safety_boundary,
    evaluate_safety_readiness,
    get_safety_boundary,
    sign_safety_boundary,
)
from core.harness.evo_compute.sandbox import evaluate_candidate_offline
from core.harness.evo_compute.status import (
    CANDIDATE_STATUSES,
    advance_candidate_status,
)
from core.harness.evo_compute.suite import (
    evaluate_evo_compute_g0_gate,
    run_evo_compute_g0_suite,
)

__all__ = [
    "CANDIDATE_STATUSES",
    "advance_candidate_status",
    "aggregate_partition_metrics",
    "approve_budget",
    "check_budget",
    "default_budget_policy",
    "default_replay_fixture",
    "default_safety_boundary",
    "evaluate_candidate_offline",
    "evaluate_closed_loop_baseline_gate",
    "evaluate_evo_compute_g0_gate",
    "evaluate_g0_exit_readiness",
    "evaluate_safety_readiness",
    "get_budget_policy",
    "get_genome",
    "get_safety_boundary",
    "list_genomes",
    "list_pilot_genome_ids",
    "measure_closed_loop_baseline",
    "pilot_genome_specs",
    "rank_candidates",
    "register_genome",
    "register_pilot_genomes",
    "replay_candidate_offline",
    "run_closed_loop_baseline_suite",
    "run_evo_compute_g0_suite",
    "set_budget_policy",
    "sign_safety_boundary",
]
