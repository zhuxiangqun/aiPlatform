"""FDE Overview — compact self-description (split from fde.py)."""
from __future__ import annotations

from fastapi import APIRouter
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


router = APIRouter(tags=["fde-overview"])


@router.get("/overview", response_model=FdeItemResponse)
async def fde_overview():
    """System overview in 3 sections: what it is, what it can do, how it evolves."""
    return {
        "system": "本体智能平台 — AI时代的企业大脑原型",
        "philosophy": "用确定性的本体包住不确定性的大模型。LLM做推理，Ontology做业务世界建模。",
        "architecture": {
            "buses": {
                "seci": "知识创造螺旋 (POST_LOOP -> atom -> convergence -> adjust)",
                "context": "10层上下文组装 (FDE全量/Agent轻量/Skill轻量/Pipeline轻量)",
                "quality": "4子系统统一评分 (FDE+SECI+Convergence+ContextBus)",
            },
            "governance": {
                "capabilities": 8,
                "self_audit": "8/8 pass in <50ms",
                "maturity": "7 production / 1 beta",
            },
            "self_evolution": {
                "phase_1": "时序列观察 (SystemSnapshot持久化, 12周趋势)",
                "phase_2": "主动诊断 (5条跨子系统关联规则)",
                "phase_3": "自动修复 (confidence>=0.9安全门, 5条修复, 审计)",
                "phase_4": "自主演化 (术语自动发布, 方案草稿审批)",
                "phase_5": "抽象目标分解 (AbstractGoalDecomposer — LLM+Ontology拆解模糊目标→子目标→依赖规划→进度评估)",
                "phase_6": "自主部署 (DeployEngine — 沙箱→灰度→push→构建→部署→验证→回滚全闭环)",
                "phase_7": "外部发现 (Discovery — socket扫描→服务指纹→DataSourceConfig→监听注册, 默认DENY)",
            },
        },
        "endpoints": 31,
        "capabilities": 756,
        "domains": 8,
        "version": "18.0",
    }
