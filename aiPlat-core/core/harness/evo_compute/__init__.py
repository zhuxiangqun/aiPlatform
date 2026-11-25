"""受控演化计算底座（Phase 0 / G0 最小切片）。

职责：
  - Genome Registry（可进化对象边界）
  - Candidate 状态机（架构 §6 SSOT）
  - Fitness 多目标 + Pareto→ranked（§4.3.1）
  - 离线沙箱：接受预计算指标，评估一个候选并留证据
  - 闭环成熟度 KPI 基线落盘（工作假设 ≠ 已测）

非目标：
  - 不接 DE/ES 种群循环、不写生产配置、不宣称 E2/L4/认证
  - 不替代 ``evolution_engine.py`` 夜间 Skill 流水线
"""

from core.harness.evo_compute.baseline import (
    evaluate_closed_loop_baseline_gate,
    measure_closed_loop_baseline,
    run_closed_loop_baseline_suite,
)
from core.harness.evo_compute.fitness import rank_candidates
from core.harness.evo_compute.genome_registry import (
    get_genome,
    list_genomes,
    register_genome,
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
    "evaluate_candidate_offline",
    "evaluate_closed_loop_baseline_gate",
    "evaluate_evo_compute_g0_gate",
    "get_genome",
    "list_genomes",
    "measure_closed_loop_baseline",
    "rank_candidates",
    "register_genome",
    "run_closed_loop_baseline_suite",
    "run_evo_compute_g0_suite",
]
