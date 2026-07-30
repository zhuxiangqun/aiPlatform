"""FDE — 验收报告 / 培训材料 / SLA Runbook."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict
from apps.fde.api.schemas import FdeStatusResponse, FdeListResponse, FdeItemResponse


from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
import logging

router = APIRouter(tags=["fde-reports"])

# ════════════════════════════════════════════════════════════
# P1: 验收报告 PDF / 培训材料 / SLA Runbook
# ════════════════════════════════════════════════════════════


@router.get("/report/generate", response_model=FdeItemResponse)
async def generate_report(spec_id: str = Query(""), download: bool = Query(False)):
    """生成验收报告 (Markdown → 前端可预览/下载).

    聚合 KPI 数据 + 反馈统计 + Checklist 结果，
    输出可直接用于客户汇报的结构化报告。
    """
    # Gather data
    kpi_text = "无 KPI 数据"
    try:
        from core.harness.learning.kpi_tracker import get_kpi_tracker
        tracker = get_kpi_tracker()
        kpis = tracker.get_all(spec_id=spec_id) if spec_id else tracker.get_all()
        if kpis:
            lines = []
            for k in kpis:
                status = "✅" if k.get("met") else "❌"
                lines.append(f"| {k.get('name','?')} | {k.get('target','')} | {k.get('actual','')} | {status} |")
            kpi_text = "| 指标 | 目标 | 实际 | 达标 |\n|---|---|---|---|\n" + "\n".join(lines)
    except Exception:
        logging.getLogger(__name__).debug('generate_report failed', exc_info=True)

    feedback_count = 0
    try:
        fd = os.path.expanduser(os.environ.get("AIPLAT_FEEDBACK_DIR", "~/.aiplat/field_feedback"))
        if os.path.isdir(fd):
            feedback_count = len([f for f in os.listdir(fd) if f.endswith(".json")])
    except Exception:
        logging.getLogger(__name__).debug('generate_report failed', exc_info=True)

    from .fde_acceptance import acceptance_checklist
    checklist_data = (await acceptance_checklist(spec_id)) if spec_id else {}

    report_md = f"""# 交付验收报告

**项目**: {spec_id or "未指定"}
**生成时间**: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
**FDE**: {os.getenv("AIPLAT_FDE_NAME", "FDE")}

---

## 1. KPI 达标情况

{kpi_text}

## 2. 用户反馈统计

- 反馈总数: {feedback_count}
- Checklist 评分: {checklist_data.get("passed", 0)}/{checklist_data.get("total", 0)} 通过

## 3. 验收清单结果

"""
    for c in checklist_data.get("checklist", []):
        icon = "✅" if c["status"] == "pass" else ("❌" if c["status"] == "fail" else "⏳")
        report_md += f"- {icon} {c['label']}: {c['detail']}\n"

    report_md += f"""
## 4. 交付结论

{'**判定**: 可移交 ✅' if checklist_data.get('ready_for_signoff') else '**判定**: 尚不可移交 ⚠️ — 有未达标项需解决'}

---
*由 aiPlat FDE 工作台自动生成*
"""

    if download:
        return PlainTextResponse(report_md, media_type="text/markdown",
                                 headers={"Content-Disposition": f"attachment; filename=acceptance-report-{spec_id or 'project'}.md"})
    return {"report": report_md, "format": "markdown", "spec_id": spec_id,
            "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/training/materials", response_model=FdeItemResponse)
async def generate_training_materials(spec_id: str = Query(""), download: bool = Query(False)):
    """自动生成客户培训材料.

    基于当前 Agent 配置 + Skills + KPI 生成 Markdown 用户手册.
    """
    materials = []

    # Agent overview
    try:
        agents_dir = os.path.expanduser("~/.aiplat/agents")
        if os.path.isdir(agents_dir):
            agent_count = len([d for d in os.listdir(agents_dir)
                              if os.path.isdir(os.path.join(agents_dir, d))])
            materials.append(f"## 配置的 Agent\n\n系统共配置 **{agent_count}** 个 Agent。")

            for d in sorted(os.listdir(agents_dir)):
                ad = os.path.join(agents_dir, d)
                if not os.path.isdir(ad):
                    continue
                md_path = os.path.join(ad, "AGENT.md")
                if os.path.isfile(md_path):
                    with open(md_path, "r") as fh:
                        body = fh.read()
                    parts = body.split("---", 2)
                    sop = parts[2].strip()[:300] if len(parts) >= 3 else body[:300]
                    materials.append(f"### {d}\n\n{sop}\n")
    except Exception:
        materials.append("## Agent 配置\n\n无法读取 Agent 配置。")

    # Skills overview
    try:
        skills_dir = os.path.expanduser("~/.aiplat/skills")
        if os.path.isdir(skills_dir):
            skill_count = len([d for d in os.listdir(skills_dir)
                              if os.path.isdir(os.path.join(skills_dir, d))])
            materials.append(f"## 已配置 Skill\n\n共 **{skill_count}** 个 Skill 可用。")
    except Exception:
        logging.getLogger(__name__).debug('generate_training_materials failed', exc_info=True)

    # Quick start guide
    quick_start = """
## 快速上手指南

1. 登录系统 → 进入"终端使用"页面
2. 选择 Agent → 输入你的问题 → 按回车发送
3. Agent 会自动分析你的需求并给出答案
4. 如需帮助，输入 `/help` 或联系技术支持

## 常见问题

**Q: Agent 不回答怎么办？**
A: 确认网络连接正常，检查是否选中了正确的 Agent。

**Q: 如何切换 Agent？**
A: 左上角 Agent 选择器可以切换不同角色。

**Q: 如何查看历史对话？**
A: 左侧面板 > 会话历史中可查看所有对话记录。
"""
    materials.append(quick_start)

    manual = "\n\n".join(materials)
    if download:
        return PlainTextResponse(manual, media_type="text/markdown",
                                 headers={"Content-Disposition": f"attachment; filename=training-manual-{spec_id or 'project'}.md"})
    return {"manual": manual, "format": "markdown", "spec_id": spec_id,
            "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/handover/runbook", response_model=FdeItemResponse)
async def generate_runbook(spec_id: str = Query(""), download: bool = Query(False)):
    """生成 SLA 运维 Runbook.

    基于已部署架构 + 告警规则 + 应急流程生成 Markdown 手册.
    """
    runbook = f"""# 运维 Runbook — {spec_id or "未指定项目"}

> 生成时间: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}

---

## 1. 系统架构概述

本系统基于 aiPlat 平台部署，采用分层架构:

- **应用层 (port 8004)**: 业务应用接口
- **平台层 (port 8003)**: API 编排 + 认证
- **核心层 (port 8002)**: Agent/Skill/Tool 引擎
- **基础设施层 (port 8001)**: 模型管理 + 数据处理

## 2. 关键进程监控

| 组件 | 端口 | 健康检查 |
|------|:---:|------|
| aiplat-core | 8002 | `GET /health` |
| aiplat-platform | 8003 | `GET /health` |
| aiplat-app | 8004 | `GET /health` |
| Ollama | 11434 | `GET /api/tags` |

## 3. 告警规则

| 条件 | 严重度 | 动作 |
|------|:---:|------|
| 任一进程不可达 | P0 | 立即通知技术负责人 |
| Token 使用 > 80% | P1 | 检查模型配额 |
| Agent 失败率 > 10% | P2 | 检查日志 + 重启服务 |
| 磁盘使用 > 90% | P1 | 清理临时文件 |

## 4. 常见应急流程

### 服务重启
```bash
cd /opt/aiplat && bash start.sh
```

### 模型不可用
```bash
# 检查 Ollama
ollama list
# 如需要，重新拉取模型
ollama pull qwen2.5:3b
```

### 数据库故障
```bash
# 数据库文件位于 ~/.aiplat/
# 备份操作
cp ~/.aiplat/data.sqlite ~/.aiplat/data.sqlite.bak
```

## 5. 联系人

| 角色 | 联系方式 |
|------|------|
| 技术支持 | support@aiplat.local |
| 紧急联系 | 通过内部 IM 工作群 |

---

*由 aiPlat FDE 工作台自动生成*
"""
    if download:
        return PlainTextResponse(runbook, media_type="text/markdown",
                                 headers={"Content-Disposition": f"attachment; filename=sla-runbook-{spec_id or 'project'}.md"})
    return {"runbook": runbook, "format": "markdown", "spec_id": spec_id,
            "generated_at": datetime.now(timezone.utc).isoformat()}
