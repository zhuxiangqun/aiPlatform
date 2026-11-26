"""受控演化计算底座（Phase 0–2 最小切片）。

职责：
  - Genome Registry / Candidate 状态机 / Fitness / Sandbox
  - 预算与安全边界 / 夹具回放 / G0–G1 出口就绪
  - DE/ES Orchestrator、三试点电池、holdout、演练
  - 离散 GA、评测/FDE 覆盖率诚实探针、G2 出口就绪

非目标：
  - 不写生产配置、不采生产流量、不宣称 E2/L4/认证
  - 不替代 ``evolution_engine.py`` 夜间 Skill 流水线
  - 套件绿 ≠ Gate 宣称完成；覆盖率缺测不得冒充达标
"""

from core.harness.evo_compute.baseline import (
    evaluate_closed_loop_baseline_gate,
    measure_closed_loop_baseline,
    run_closed_loop_baseline_suite,
)
from core.harness.evo_compute.battery import run_pilot_de_es_battery
from core.harness.evo_compute.budget import (
    approve_budget,
    check_budget,
    default_budget_policy,
    get_budget_policy,
    set_budget_policy,
)
from core.harness.evo_compute.coverage import (
    coverage_from_baseline_kpi,
    coverage_ratio_from_capability_report,
    coverage_ratio_from_inventory,
    default_g2_eval_inventory_fixture,
    default_g2_fde_inventory_fixture,
    measure_eval_coverage,
    measure_eval_coverage_from_capability_report,
    measure_eval_coverage_from_inventory,
    measure_fde_evidence_coverage,
    measure_fde_evidence_coverage_from_inventory,
)
from core.harness.evo_compute.drill import run_human_gate_canary_rollback_drill
from core.harness.evo_compute.exit_readiness import (
    evaluate_g0_exit_readiness,
    evaluate_g1_exit_readiness,
    evaluate_g2_exit_readiness,
)
from core.harness.evo_compute.fitness import rank_candidates
from core.harness.evo_compute.ga import run_ga_offline
from core.harness.evo_compute.genome_registry import (
    get_genome,
    list_genomes,
    register_genome,
)
from core.harness.evo_compute.holdout import compare_holdout
from core.harness.evo_compute.orchestrator import run_de_es_offline
from core.harness.evo_compute.pilots import (
    list_pilot_genome_ids,
    pilot_genome_specs,
    register_pilot_genomes,
)
from core.harness.evo_compute.regression import (
    REGRESSION_DATASET_VERSION,
    default_adversarial_cases,
    default_regression_set,
    run_regression_gate,
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
    evaluate_evo_compute_g1_gate,
    evaluate_evo_compute_g2_gate,
    evaluate_evo_compute_g2_slice2_gate,
    evaluate_evo_compute_g2_slice3_gate,
    run_evo_compute_g0_suite,
    run_evo_compute_g1_slice2_suite,
    run_evo_compute_g1_suite,
    run_evo_compute_g2_slice2_suite,
    run_evo_compute_g2_slice3_suite,
    run_evo_compute_g2_suite,
)

__all__ = [
    "CANDIDATE_STATUSES",
    "advance_candidate_status",
    "aggregate_partition_metrics",
    "approve_budget",
    "check_budget",
    "compare_holdout",
    "default_budget_policy",
    "default_replay_fixture",
    "default_safety_boundary",
    "evaluate_candidate_offline",
    "evaluate_closed_loop_baseline_gate",
    "evaluate_evo_compute_g0_gate",
    "evaluate_evo_compute_g1_gate",
    "coverage_from_baseline_kpi",
    "coverage_ratio_from_capability_report",
    "coverage_ratio_from_inventory",
    "default_g2_eval_inventory_fixture",
    "default_g2_fde_inventory_fixture",
    "evaluate_evo_compute_g2_gate",
    "REGRESSION_DATASET_VERSION",
    "default_adversarial_cases",
    "default_regression_set",
    "evaluate_evo_compute_g2_slice2_gate",
    "evaluate_evo_compute_g2_slice3_gate",
    "evaluate_g0_exit_readiness",
    "evaluate_g1_exit_readiness",
    "evaluate_g2_exit_readiness",
    "evaluate_safety_readiness",
    "get_budget_policy",
    "get_genome",
    "get_safety_boundary",
    "list_genomes",
    "list_pilot_genome_ids",
    "measure_closed_loop_baseline",
    "measure_eval_coverage",
    "measure_eval_coverage_from_capability_report",
    "measure_eval_coverage_from_inventory",
    "measure_fde_evidence_coverage",
    "measure_fde_evidence_coverage_from_inventory",
    "pilot_genome_specs",
    "rank_candidates",
    "register_genome",
    "register_pilot_genomes",
    "replay_candidate_offline",
    "run_closed_loop_baseline_suite",
    "run_de_es_offline",
    "run_evo_compute_g0_suite",
    "run_evo_compute_g1_slice2_suite",
    "run_evo_compute_g1_suite",
    "run_evo_compute_g2_slice2_suite",
    "run_evo_compute_g2_slice3_suite",
    "run_evo_compute_g2_suite",
    "run_ga_offline",
    "run_human_gate_canary_rollback_drill",
    "run_pilot_de_es_battery",
    "run_regression_gate",
    "set_budget_policy",
    "sign_safety_boundary",
]
