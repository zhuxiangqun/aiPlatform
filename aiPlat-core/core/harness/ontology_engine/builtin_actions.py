"""
Built-in action contracts + YAML auto-loader (v3, 2026-07-29).

6 contracts: 2 business-domain + 4 legacy bridge actions.
register_all() also scans ~/.aiplat/actions/*.yaml and workspace_seeds/actions/.
"""
from __future__ import annotations

import glob
import logging
import os
from typing import List

from core.harness.infrastructure.action_contract import (
    ActionContractModel,
    ActionScope,
    ActionCategory,
    FailureStrategy,
    RiskLevel,
)
# Production import anchors for YAML-resolved handlers (method_verify wiring).
from core.harness.ontology_engine.builtin_handlers import (  # noqa: F401
    accept_order,
    assign_work_order,
    set_entity_state,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Generic bridge actions (infrastructure-level, domain-agnostic)
# Business-domain actions belong in ~/.aiplat/actions/*.yaml
# ═══════════════════════════════════════════════════════════

BUILTIN_CONTRACTS: List[ActionContractModel] = [
    # ── Legacy bridge actions (for StateMachine backward compat) ──
    ActionContractModel(
        action_id="builtin_webhook_executor",
        label="Webhook 回调（兼容）",
        description="向后兼容：将旧 call_webhook 映射到 ActionRegistry",
        category=ActionCategory.NOTIFICATION,
        scope=ActionScope.GLOBAL,
        risk_level=RiskLevel.LOW,
        failure_strategy=FailureStrategy.LOG_ONLY,
        handler="core.harness.ontology_engine.builtin_handlers:webhook_forward",
    ),
    ActionContractModel(
        action_id="builtin_add_tag",
        label="添加标签（兼容）",
        description="向后兼容：将旧 add_tag 映射到 ActionRegistry",
        category=ActionCategory.MUTATION,
        scope=ActionScope.GLOBAL,
        risk_level=RiskLevel.LOW,
        failure_strategy=FailureStrategy.LOG_ONLY,
    ),
    ActionContractModel(
        action_id="builtin_mark_review",
        label="标记复审（兼容）",
        description="向后兼容：将旧 mark_related_for_review 映射到 ActionRegistry",
        category=ActionCategory.REVIEW,
        scope=ActionScope.GLOBAL,
        risk_level=RiskLevel.LOW,
        failure_strategy=FailureStrategy.LOG_ONLY,
    ),
    ActionContractModel(
        action_id="builtin_case_study",
        label="注入案例（兼容）",
        description="向后兼容：将旧 inject_case_study 映射到 ActionRegistry",
        category=ActionCategory.CASE_STUDY,
        scope=ActionScope.GLOBAL,
        risk_level=RiskLevel.LOW,
        failure_strategy=FailureStrategy.LOG_ONLY,
    ),
]


# ═══════════════════════════════════════════════════════════
# Registration entry point
# ═══════════════════════════════════════════════════════════

def register_all(registry) -> int:
    """Register all built-in contracts + scan action YAML dirs.

    Registry parameter is injected to avoid circular imports.
    """
    count = 0

    # 1. Register hard-coded built-in contracts
    for contract in BUILTIN_CONTRACTS:
        registry.register(contract)
        count += 1

    # 2. Scan YAML directories: $AIPLAT_HOME/actions + workspace seeds
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    scan_dirs = [
        os.path.join(home, "actions"),
        os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "workspace_seeds", "actions"
            )
        ),
    ]
    for yaml_dir in scan_dirs:
        if not os.path.isdir(yaml_dir):
            continue
        for yaml_path in glob.glob(os.path.join(yaml_dir, "*.yaml")):
            try:
                contracts = ActionContractModel.from_yaml_batch(yaml_path)
                for contract in contracts:
                    registry.register(contract)
                    count += 1
            except Exception as e:
                logger.warning("Failed to load %s: %s", yaml_path, e)

    logger.info("ActionRegistry: %d actions registered", count)
    return count
