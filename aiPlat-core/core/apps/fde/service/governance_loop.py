"""Data-governance scenario loop (Xingye 8-step shape) → aiPlat honest map.

Suggestion/authority discipline:
- Steps 1–3 may produce suggestions / pending review only.
- Step 4 changes TBox only via VersionedOntologyStore proposal apply.
- Steps 5–6 write ABox via Action L1 (data-gov).
- Step 8 is delivery (Agent / FDE), not silent YAML mutation.
- Never claim material KPIs (95% / 85% / 5 days).
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_governance_loop_map() -> Dict[str, Any]:
    """Read-only map for UI / playbooks. No TBox or GraphIndex side effects."""
    steps: List[Dict[str, Any]] = [
        {
            "step": 1,
            "title": "获取系统元数据",
            "material": "系统名/库名/物理路径/表名",
            "aiplat": "Path B：表/CSV table_map · JSON · webhook；工厂粘贴表头",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/diagnostics/fde",
            "href_label": "FDE⑦ 入轨",
        },
        {
            "step": 2,
            "title": "AI 补齐元数据",
            "material": "表含义/业务语境 → 本体语料",
            "aiplat": "schema-suggestions 列含义启发式 + 抽取 LLM（建议/待审）",
            "status": "suggestion",
            "status_label": "建议层竖切",
            "href": "/knowledge/business?tab=factory&domain=data-gov&focus=schema",
            "href_label": "工厂①b 表头",
        },
        {
            "step": 3,
            "title": "本体语料智能解析",
            "material": "去噪、抽关键",
            "aiplat": "工厂抽取待审；AcceptTab 丢幽灵/错挂",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/knowledge/business?tab=factory&domain=data-gov",
            "href_label": "工厂① 抽取",
        },
        {
            "step": 4,
            "title": "本体构建",
            "material": "方法论构建本体与知识图谱",
            "aiplat": "Path A：confirm/代码/表头 → 提案 → 批准→apply",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/knowledge/business?tab=factory&domain=data-gov",
            "href_label": "工厂③ 提案",
        },
        {
            "step": 5,
            "title": "数据资产目录",
            "material": "目录结构 + 血缘",
            "aiplat": "mount_catalog 闸2；教学图种子；血缘全量弱",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/diagnostics/fde",
            "href_label": "FDE⑦ 治理图",
        },
        {
            "step": 6,
            "title": "数据治理",
            "material": "指标/词表/质量/价值",
            "aiplat": "OCS 完整性 + data-gov 闸2 动作 + 业务价值页（竖切）",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/diagnostics/fde",
            "href_label": "FDE⑦ + 质量面板",
            "api": "GET /ontology/governance/quality?domain_id=data-gov",
        },
        {
            "step": 7,
            "title": "通过本体查数取数",
            "material": "按业务语义定位取数",
            "aiplat": "GraphIndex 定位 + 沙箱 fetch（Org L5 P1）；非直连业务库 / 非 live",
            "status": "vertical",
            "status_label": "已竖切",
            "href": "/diagnostics/fde",
            "href_label": "FDE⑦ 本体定位+取数",
            "api": "POST /ontology/governance/locate|fetch",
        },
        {
            "step": 8,
            "title": "创建智能体应用",
            "material": "工具与 Agent 应用（材料闭环终点）",
            "aiplat": "/workspace/agents + FDE⑦ 验收",
            "status": "entry",
            "status_label": "已有入口",
            "href": "/workspace/agents",
            "href_label": "应用库 Agent",
        },
    ]
    return {
        "scenario": "data-governance",
        "steps": steps,
        "count": len(steps),
        "authority_note": (
            "①–③ 建议/待审；④ 改说明书须提案 apply；⑤⑥ 写实例须 Action；"
            "⑧ 交付终点。禁止宣称材料 KPI（补齐率/准确率/人天）。"
        ),
        "kpis_claimed_by_material": False,
    }
