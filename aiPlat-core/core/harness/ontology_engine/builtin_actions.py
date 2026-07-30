"""
Built-in action contracts + YAML auto-loader (v3, 2026-07-29).

6 contracts: 2 business-domain + 4 legacy bridge actions.
register_all() also scans ~/.aiplat/actions/*.yaml for custom actions.
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

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Business-domain actions
# ═══════════════════════════════════════════════════════════

BUILTIN_CONTRACTS: List[ActionContractModel] = [
    ActionContractModel(
        action_id="approve_diagnosis",
        label="批准诊断",
        description="批准诊断会话结果，进入交付阶段",
        category=ActionCategory.MUTATION,
        scope=ActionScope.DOMAIN,
        domain_id="fde-delivery",
        target_class="诊断会话",
        required_state="delivered",
        forbidden_states=["completed", "abandoned"],
        effect_semantics="将诊断会话从 delivered 推进到 in_progress，锁定诊断报告并分配交付工程师",
        compensation="调用 reject_diagnosis 回退到 delivered 并解除工程师分配",
        risk_level=RiskLevel.MEDIUM,
        require_approval=False,
        allowed_roles=["fde_engineer", "admin"],
        input_schema={
            "type": "object",
            "required": ["assigned_engineer"],
            "properties": {
                "assigned_engineer": {"type": "string", "description": "交付工程师姓名"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        failure_strategy=FailureStrategy.BLOCK,
        handler="core.harness.ontology_engine.builtin_handlers:approve_diagnosis",
    ),
    ActionContractModel(
        action_id="accept_order",
        label="接受工单",
        description="安装师傅接受安装工单，指派上门时间",
        category=ActionCategory.BUSINESS,
        scope=ActionScope.DOMAIN,
        domain_id="lock-service",
        target_class="安装工单",
        required_state="pending",
        forbidden_states=["completed", "cancelled"],
        effect_semantics="将工单状态置为 accepted，指派安装师傅并锁定上门时间窗口",
        compensation="调用 cancel_order 释放师傅排期并通知客户",
        risk_level=RiskLevel.LOW,
        require_approval=False,
        allowed_roles=["technician", "operator", "admin"],
        input_schema={
            "type": "object",
            "required": ["technician_id", "appointment_slot"],
            "properties": {
                "technician_id": {"type": "string", "description": "安装师傅 ID"},
                "appointment_slot": {"type": "string", "description": "上门时间窗口"},
            },
        },
        failure_strategy=FailureStrategy.LOG_ONLY,
        handler="core.harness.ontology_engine.builtin_handlers:accept_order",
    ),
    # ── BellSystem24 business actions ──
    ActionContractModel(
        action_id="bell_deploy_ai_agent",
        label="部署AI Agent",
        description="Bell24: GenAI共创实验室完成 → 在bell-data-cloud域创建AI_Agent实体",
        category=ActionCategory.BUSINESS,
        scope=ActionScope.CROSS_DOMAIN,
        domain_id="bell-consulting",
        target_class="生成式AI共创实验室",
        required_state="active",
        forbidden_states=["archived"],
        effect_semantics="将GenAI共创实验室标为deployed，在bell-data-cloud创建AI_Agent实体并建立跨域develops关系",
        compensation="调用 archive_ai_agent 删除AI_Agent实体并回退lab状态",
        risk_level=RiskLevel.MEDIUM,
        require_approval=True,
        allowed_roles=["consultant", "admin"],
        input_schema={
            "type": "object",
            "required": ["agent_name", "development_partner"],
            "properties": {
                "agent_name": {"type": "string", "description": "AI Agent名称"},
                "development_partner": {"type": "string", "enum": ["AVILEN", "伊藤忠", "CTC", "Microsoft", "Google", "AWS"]},
                "launch_date": {"type": "string", "description": "上线日期"},
                "target_clients": {"type": "integer", "description": "目标客户数"},
            },
        },
        failure_strategy=FailureStrategy.BLOCK,
        handler="core.harness.ontology_engine.builtin_handlers:deploy_ai_agent",
    ),
    ActionContractModel(
        action_id="bell_cro_emergency",
        label="CRO紧急应对",
        description="Bell24 CRO: 临床试验严重事件 → 创建紧急应对记录",
        category=ActionCategory.BUSINESS,
        scope=ActionScope.DOMAIN,
        domain_id="bell-healthcare",
        target_class="临床试验",
        required_state="active",
        forbidden_states=["completed", "terminated"],
        effect_semantics="创建EmergencyReception实体，建立supports关系，记录事件类型/严重程度/响应措施",
        compensation="调用 close_emergency 标记事件为已解决",
        risk_level=RiskLevel.HIGH,
        require_approval=True,
        allowed_roles=["cro_operator", "admin"],
        input_schema={
            "type": "object",
            "required": ["incident_type", "severity"],
            "properties": {
                "incident_type": {"type": "string", "description": "事件类型（如肝损伤）"},
                "severity": {"type": "string", "enum": ["critical", "serious", "moderate", "mild"]},
                "description": {"type": "string", "description": "事件描述"},
                "response_action": {"type": "string", "description": "响应措施"},
            },
        },
        failure_strategy=FailureStrategy.ESCALATE,
        handler="core.harness.ontology_engine.builtin_handlers:trigger_emergency_response",
    ),
    ActionContractModel(
        action_id="bell_complete_bpr",
        label="完成BPR交付",
        description="Bell24: BPR咨询交付完成 → 记录效率并推荐AI Agent",
        category=ActionCategory.BUSINESS,
        scope=ActionScope.DOMAIN,
        domain_id="bell-consulting",
        target_class="BPR咨询服务",
        required_state="implementation",
        forbidden_states=["completed", "planning"],
        effect_semantics="将BPR状态推进到completed，记录效率提升率，效率≥20%时自动推荐后续AI Agent导入",
        compensation="调用 revert_bpr 回退到implementation并重置效率指标",
        risk_level=RiskLevel.LOW,
        require_approval=False,
        allowed_roles=["consultant", "admin"],
        input_schema={
            "type": "object",
            "required": ["efficiency_improvement_rate", "man_hours_saved"],
            "properties": {
                "efficiency_improvement_rate": {"type": "integer", "description": "效率提升率(%)"},
                "man_hours_saved": {"type": "integer", "description": "节省工时"},
            },
        },
        failure_strategy=FailureStrategy.LOG_ONLY,
        handler="core.harness.ontology_engine.builtin_handlers:complete_bpr_delivery",
    ),
    ActionContractModel(
        action_id="bell_sync_overseas",
        label="同步海外状态",
        description="Bell24: 海外子公司员工数/据点更新 → 同步到集团视图",
        category=ActionCategory.MUTATION,
        scope=ActionScope.CROSS_DOMAIN,
        domain_id="bell-global",
        target_class="海外子公司",
        required_state="active",
        forbidden_states=["dormant"],
        effect_semantics="更新bell-global中海外子公司的consolidation_status/employees/locations_count",
        compensation="调用 rollback_overseas 恢复为上次快照值",
        risk_level=RiskLevel.LOW,
        require_approval=False,
        allowed_roles=["operator", "admin"],
        input_schema={
            "type": "object",
            "required": ["consolidation_status"],
            "properties": {
                "consolidation_status": {"type": "string", "enum": ["consolidated", "non_consolidated"]},
                "employees": {"type": "integer", "description": "员工数"},
                "locations_count": {"type": "integer", "description": "据点数量"},
            },
        },
        failure_strategy=FailureStrategy.LOG_ONLY,
        handler="core.harness.ontology_engine.builtin_handlers:sync_overseas_status",
    ),
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
    """Register all built-in contracts + scan ~/.aiplat/actions/*.yaml.

    Registry parameter is injected to avoid circular imports.
    """
    count = 0

    # 1. Register hard-coded built-in contracts
    for contract in BUILTIN_CONTRACTS:
        registry.register(contract)
        count += 1

    # 2. Scan YAML directory for custom actions
    yaml_dir = os.path.expanduser("~/.aiplat/actions/")
    if os.path.isdir(yaml_dir):
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
