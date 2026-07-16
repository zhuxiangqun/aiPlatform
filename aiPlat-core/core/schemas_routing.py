"""
Routing schema — 统一路由输出结构，所有路由决策点共享。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentCategory(str, Enum):
    """通用意图分类。覆盖所有 Agent 类型的常见用户意图。"""
    # ── 客服类 ──
    ORDER_QUERY = "order_query"          # 订单查询
    REFUND_REQUEST = "refund_request"     # 退款/退货
    PRODUCT_INFO = "product_info"         # 产品咨询
    COMPLAINT = "complaint"              # 投诉
    ACCOUNT_SERVICE = "account_service"   # 账号/会员服务
    # ── 开发类 ──
    CODE_REVIEW = "code_review"          # 代码审查
    CODE_GENERATION = "code_generation"   # 代码生成
    BUG_FIX = "bug_fix"                  # Bug 修复
    ARCHITECTURE_DESIGN = "architecture_design"  # 架构设计
    TECH_CONSULT = "tech_consult"        # 技术咨询
    # ── 测试类 ──
    TEST_GENERATION = "test_generation"   # 测试用例生成
    E2E_TEST = "e2e_test"               # 端到端测试
    # ── 文档/知识类 ──
    FACT_LOOKUP = "fact_lookup"          # 事实查询
    SUMMARY = "summary"                  # 总结摘要
    COMPARE = "compare"                  # 对比分析
    EVIDENCE_TRACE = "evidence_trace"    # 证据追溯
    APPLICABILITY_ANALYSIS = "applicability_analysis"  # 适用性分析
    # ── 安全类 ──
    SECURITY_AUDIT = "security_audit"    # 安全审查
    COMPLIANCE_CHECK = "compliance_check"  # 合规检查
    # ── 通用类 ──
    RESEARCH = "research"                # 调研/搜索
    MONITORING = "monitoring"            # 监控/跟踪
    CHITCHAT = "chitchat"               # 闲聊
    FOLLOW_UP = "follow_up"             # 后续追问
    UNKNOWN = "unknown"                  # 无法分类


class RouteKind(str, Enum):
    """路由目标类型。"""
    AGENT = "agent"            # 路由到另一个 Agent
    SKILL = "skill"            # 路由到某个 Skill
    TOOL = "tool"              # 路由到某个 Tool
    CLARIFY = "clarify"        # 需要追问用户
    HUMAN = "human"            # 转人工
    DIRECT = "direct"          # 当前 Agent 直接处理（不做额外路由）


class ConfidenceLevel(str, Enum):
    HIGH = "high"       # ≥0.8
    MEDIUM = "medium"   # 0.4-0.8
    LOW = "low"         # <0.4


class SuggestedRoute(BaseModel):
    """单条候选路由及其得分。"""
    kind: RouteKind = Field(description="路由目标类型")
    target: str = Field(description="目标标识 (agent_id / skill_name / tool_name)")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="匹配得分 (0-1)")
    reason: str = Field(default="", description="简短理由")


class RoutingResult(BaseModel):
    """统一路由输出结构。所有路由决策点 (classifier / policy / executor) 共享此格式。

    字段对齐文章定义:
      route → intent + primary_route
      confidence → confidence
      entities → extracted params for downstream
      reason → reason (可解释性)
      fallback → suggested_routes (备选路径)
    """
    # ── 分类结果 ──
    intent: IntentCategory = Field(default=IntentCategory.UNKNOWN, description="识别出的意图")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度 0-1")
    confidence_level: ConfidenceLevel = Field(default=ConfidenceLevel.LOW, description="置信度等级")

    # ── 主路由 ──
    primary_route: SuggestedRoute = Field(
        default_factory=lambda: SuggestedRoute(kind=RouteKind.DIRECT, target=""),
        description="推荐的主路由"
    )

    # ── 候选路由 (备选) ──
    suggested_routes: List[SuggestedRoute] = Field(
        default_factory=list,
        description="备选路由列表 (含得分，供后续逻辑参考)"
    )

    # ── 实体提取 ──
    entities: Dict[str, Any] = Field(
        default_factory=dict,
        description="从用户输入中提取的结构化实体 (order_id, product_name, user_tier, language, directory, ...)"
    )

    # ── 可解释性 ──
    reason: str = Field(default="", description="路由决策理由，用于日志和调试")
    signals: Dict[str, Any] = Field(default_factory=dict, description="匹配信号 (关键词命中 / 规则名称等)")

    # ── 行为建议 ──
    should_clarify: bool = Field(default=False, description="置信度低时建议追问用户")
    clarification_prompt: str = Field(default="", description="追问话术")

    # ── 能力级 hints ──
    suggested_skill_ids: List[str] = Field(default_factory=list, description="建议绑定的 Skill IDs (增量)")
    suggested_tool_ids: List[str] = Field(default_factory=list, description="建议绑定的 Tool IDs")
    auto_filter_skill_ids: List[str] = Field(default_factory=list, description="自动选择的 Skill IDs (子集过滤，仅包含Agent已有的)")


class RoutingContext(BaseModel):
    """路由分类器的输入上下文。"""
    user_message: str = Field(default="", description="用户输入消息")
    agent_id: str = Field(default="", description="当前 Agent ID (为空表示自动选择)")
    agent_type: str = Field(default="", description="当前 Agent 类型")
    agent_name: str = Field(default="", description="当前 Agent 名称")
    agent_description: str = Field(default="", description="Agent 功能描述")
    available_agents: List[Dict[str, Any]] = Field(default_factory=list, description="可用的 Agent 列表")
    available_skills: List[str] = Field(default_factory=list, description="当前 Agent 绑定的 Skill IDs")
    available_tools: List[str] = Field(default_factory=list, description="当前 Agent 绑定的 Tool IDs")
    session_id: str = Field(default="", description="会话 ID")
