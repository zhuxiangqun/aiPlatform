#!/usr/bin/env python3
"""Generate the five dimension-specific whitepaper volumes.

Reads docs/whitepaper/whitepaper-suite.yaml and writes:

  docs/whitepaper/volumes/01-tech-architecture.md
  docs/whitepaper/volumes/02-product-capability.md
  docs/whitepaper/volumes/03-commercial-value.md
  docs/whitepaper/volumes/04-ecosystem-integration.md
  docs/whitepaper/volumes/05-security-governance.md

Authority model: volumes are *audience packages* over existing canonical docs.
They do not invent capability counts or ROI numbers. Hand-edit sources, then regenerate.

Usage:
  python3 scripts/generate_whitepaper_volumes.py
  python3 scripts/generate_whitepaper_volumes.py --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / "docs" / "whitepaper" / "whitepaper-suite.yaml"
OUT_DIR = REPO / "docs" / "whitepaper" / "volumes"
CAPS = REPO / "AIPLAT_CAPABILITIES.md"
SCORES = REPO / "docs" / "framework" / "assessment-scores.json"

VOLUME_FILES = {
    "tech-architecture": "01-tech-architecture.md",
    "product-capability": "02-product-capability.md",
    "commercial-value": "03-commercial-value.md",
    "ecosystem-integration": "04-ecosystem-integration.md",
    "security-governance": "05-security-governance.md",
}

STAMP_RE = re.compile(
    r"<!-- volume_stamp id=([^\s]+) suite_sha256=([0-9a-f]+)"
    r" caps_sha256=([0-9a-f]+) scores_sha256=([0-9a-f]+) -->"
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes()) if path.is_file() else ""


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        # Minimal fallback for simple suite file (no nested complexity beyond what we need)
        raise SystemExit(
            "FAIL: PyYAML required — pip install pyyaml, or run in repo venv"
        )
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _rel(path: str) -> Path:
    return (REPO / path).resolve()


def _link(path: str) -> str:
    """Markdown link from volumes/ to repo path."""
    # volumes/ lives under docs/whitepaper/volumes/
    if path.startswith("docs/whitepaper/"):
        # sibling under docs/whitepaper/
        target = "../" + path[len("docs/whitepaper/") :]
    elif path.startswith("docs/"):
        target = "../" + path[len("docs/") :]
    elif path.startswith("packages/") or path.startswith("AIPLAT_") or path == "CLAUDE.md":
        target = "../../" + path
    else:
        target = "../../" + path
    return f"[`{path}`]({target})"


def _read_excerpt(path: Path, max_chars: int = 12000) -> Tuple[str, bool]:
    if not path.is_file():
        return f"_(存在性检查失败：文件缺失 `{path.relative_to(REPO)}`)_\n", False
    text = path.read_text(encoding="utf-8", errors="replace")
    # strip yaml frontmatter for readability
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            text = text[end + 4 :].lstrip("\n")
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars].rstrip() + "\n\n…\n\n_(节选；全文见权威源)_\n"
    return text, True


def _caps_section_extract(titles: List[str], max_chars: int = 8000) -> str:
    if not CAPS.is_file():
        return "_(AIPLAT_CAPABILITIES.md 缺失)_\n"
    body = CAPS.read_text(encoding="utf-8")
    chunks: List[str] = []
    for title in titles:
        # match ## 七、安全与治理 style
        pat = re.compile(
            rf"^(## [^\n]*{re.escape(title)}[^\n]*)\n(.*?)(?=^## |\Z)",
            re.M | re.S,
        )
        m = pat.search(body)
        if not m:
            # softer: any heading containing keyword
            pat2 = re.compile(
                rf"^(## [^\n]*{re.escape(title)}[^\n]*)\n(.*?)(?=^## |\Z)",
                re.M | re.S | re.I,
            )
            m = pat2.search(body)
        if not m:
            chunks.append(f"### （未命中章节）{title}\n\n_(CAPABILITIES 中未找到含「{title}」的 ## 标题)_\n")
            continue
        head, content = m.group(1), m.group(2)
        block = head + "\n" + content
        if len(block) > max_chars:
            block = block[:max_chars].rstrip() + "\n\n…\n\n_(节选)_\n"
        chunks.append(block)
    return "\n".join(chunks)


def _assessment_stamp() -> str:
    if not SCORES.is_file():
        return "_(assessment-scores.json 缺失)_\n"
    data = json.loads(SCORES.read_text(encoding="utf-8"))
    lines = [
        f"> generated_at=`{data.get('generated_at', '—')}` · "
        f"spec=`{data.get('spec_version', '—')}`",
        "",
        "| 框架 | 结果 |",
        "|------|------|",
    ]
    for key, fw in (data.get("frameworks") or {}).items():
        name = fw.get("name") or key
        if fw.get("composite_grade") is not None:
            result = f"**{fw['composite_grade']}** ({fw.get('composite_level_value', '')})"
        elif fw.get("overall_pct") is not None:
            result = f"**{fw['overall_pct']}%**"
        else:
            result = "_(见 JSON)_"
        lines.append(f"| {name} | {result} |")
    lines.append("")
    return "\n".join(lines)


def _doc_table(entries: List[Dict[str, Any]], suite_dir_note: str = "") -> str:
    rows = ["| 路径 | 角色 | 存在 |", "|------|------|:----:|"]
    for e in entries or []:
        path = str(e.get("path") or "")
        role = str(e.get("role") or e.get("note") or "")
        ok = _rel(path).is_file()
        rows.append(f"| {_link(path)} | {role} | {'✅' if ok else '❌'} |")
    if suite_dir_note:
        rows.append("")
        rows.append(suite_dir_note)
    return "\n".join(rows) + "\n"


def _build_volume(
    vol: Dict[str, Any],
    suite_sha: str,
    caps_sha: str,
    scores_sha: str,
    generated_at: str,
) -> str:
    vid = str(vol["id"])
    name = str(vol["name"])
    audience = str(vol.get("audience") or "")
    question = str(vol.get("core_question") or "")
    priority = str(vol.get("priority") or "")
    status = str(vol.get("status") or "")
    notes = str(vol.get("notes") or "")
    canonical = list(vol.get("canonical") or [])
    supporting = list(vol.get("supporting") or [])

    parts: List[str] = [
        "---",
        f'title: "aiPlat {name}"',
        f"volume_id: {vid}",
        "type: whitepaper-volume",
        "status: generated",
        f'generated_at: "{generated_at}"',
        f'audience: "{audience}"',
        f'core_question: "{question}"',
        f"priority: {priority}",
        f"source_status: {status}",
        f'suite: docs/whitepaper/whitepaper-suite.yaml',
        f"suite_sha256: \"{suite_sha}\"",
        f"caps_sha256: \"{caps_sha}\"",
        f"scores_sha256: \"{scores_sha}\"",
        "language: zh-CN",
        "---",
        "",
        f"<!-- volume_stamp id={vid} suite_sha256={suite_sha} "
        f"caps_sha256={caps_sha} scores_sha256={scores_sha} -->",
        "",
        f"# aiPlat {name}",
        "",
        f"> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  ",
        f"> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · "
        f"清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  ",
        f"> 重生成：`bash scripts/sync_whitepapers.sh` 或 "
        f"`python3 scripts/generate_whitepaper_volumes.py`",
        "",
        "## 0. 卷册元信息",
        "",
        "| 字段 | 值 |",
        "|------|-----|",
        f"| 卷 ID | `{vid}` |",
        f"| 受众 | {audience} |",
        f"| 核心问题 | {question} |",
        f"| 优先级 | {priority} |",
        f"| 材料完备度（suite） | `{status}` |",
        f"| 生成时间 (UTC) | `{generated_at}` |",
        f"| CAPABILITIES sha256 | `{caps_sha[:12]}…` |",
        f"| assessment-scores sha256 | `{scores_sha[:12]}…` |",
        "",
    ]
    if notes:
        parts += ["**备注**：", "", notes, ""]

    parts += [
        "## 1. 本卷论证目标",
        "",
        f"本卷面向 **{audience}**，围绕「**{question}**」组织既有权威文档。"
        "结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。",
        "",
        "## 2. 权威源清单（存在性已校验）",
        "",
        "### 2.1 Canonical",
        "",
        _doc_table(canonical),
        "",
        "### 2.2 Supporting",
        "",
        _doc_table(supporting) if supporting else "_(无)_",
        "",
        "## 3. 正文编排（节选权威源）",
        "",
    ]

    # Dimension-specific body
    if vid == "tech-architecture":
        parts += [
            "### 3.0 关键设计决策索引",
            "",
            "本卷不重抄 ADR 全文，以索引方式消解散落问题。设计决策分散在以下权威源：",
            "",
            "| 决策域 | 权威源 |",
            "|--------|--------|",
            f"| 平台总览与边界 | {_link('docs/architecture/overview.md')} |",
            f"| 执行决策矩阵 | {_link('docs/architecture/execution-decision-matrix.md')} |",
            f"| Pi 薄运行时 | {_link('docs/architecture/plans/pi-thin-runtime.md')} |",
            f"| 文档体系与 ADR 分布 | {_link('docs/DOCUMENT_SYSTEM.md')} |",
            "",
            "索引维护责任与更新触发条件见 "
            f"{_link('docs/whitepaper/WHITEPAPER_SYSTEM.md')}「ADR 索引维护」节。",
            "",
            "> 索引只指向权威源，不复制 ADR 正文。修改 overview / "
            "execution-decision-matrix / pi-thin-runtime / DOCUMENT_SYSTEM "
            "任一文件时，必须同步本索引。",
            "",
            "### 3.1 架构全景（overview）",
            "",
        ]
        excerpt, _ = _read_excerpt(_rel("docs/architecture/overview.md"), 14000)
        parts += [excerpt, "", "### 3.2 架构对比入口（comparison）", ""]
        excerpt, _ = _read_excerpt(_rel("docs/architecture/comparison.md"), 10000)
        parts += [
            excerpt,
            "",
            "### 3.3 工程落地视图索引（部署 / 性能 / 可观测 / 数据 / 测试 …）",
            "",
            "本卷定位是「为什么这样设计」与架构全景；**工程落地细节不在此卷全文复述**，"
            "以免形成第二真相源。CTO/架构师做技术尽调时，按下表进入权威源"
            "（含物理/部署视图、数据视图、开发视图、质量属性）。",
            "",
            "| 工程维度 | 读者要回答的问题 | 权威源（优先） | CAPABILITIES / 姊妹卷 |",
            "|----------|------------------|----------------|----------------------|",
            f"| **部署与运维** | 生产怎么布？环境/灾备/灰度？ | "
            f"{_link('docs/manuals/deployment.md')} · "
            f"{_link('docs/architecture/plans/disaster-recovery-plan.md')} · "
            f"`deploy/helm/aiplat/` | CAPABILITIES「部署与运维 / 部署与灰度」 |",
            f"| **性能与扩展** | QPS/P95/容量/扩展策略？ | "
            f"{_link('docs/standards/规范-性能.md')} · "
            f"{_link('docs/architecture/slo.md')} · "
            f"`scripts/benchmark_all.sh` | CAPABILITIES「部署与运维」基准条目 |",
            f"| **可观测性** | 日志/指标/追踪怎么采与告警？ | "
            f"{_link('docs/architecture/plans/observability-eval-repair-architecture.md')} · "
            f"{_link('docs/standards/规范-core-run_id-trace_id-request_id.md') if _rel('docs/standards/规范-core-run_id-trace_id-request_id.md').is_file() else _link('docs/architecture/slo.md')} | "
            "CAPABILITIES「可观测性」· 安全卷可交叉 |",
            f"| **数据架构** | 存什么、隔离、备份？ | "
            f"{_link('docs/knowledge-system.md')} · "
            f"{_link('docs/architecture/knowledge-base-architecture.md')} | "
            "CAPABILITIES「知识引擎」· 灾备计划（备份） |",
            f"| **安全嵌入视图** | Gate/信任边界如何嵌进运行时？ | "
            f"{_link('docs/security/security-architecture.md')} | "
            f"分卷 05 · CAPABILITIES「安全与治理 / Gate」 |",
            f"| **测试与验证** | 金字塔 / CI / 质量门？ | "
            f"{_link('docs/manuals/testing.md')} · "
            f"{_link('docs/architecture/execution-quality-gates.md')} · "
            "`.github/workflows/` | CAPABILITIES「管理 & 质量」 |",
            f"| **技术风险与演进** | 技术债、依赖风险、路线？ | "
            f"{_link('AIPLAT_ROADMAP.md')} · "
            f"{_link('docs/research/architecture-evolution-roadmap.md')} · "
            f"{_link('CLAUDE.md')} §16 | 商业卷 ROADMAP 节选（非财务） |",
            f"| **开发视图** | 代码组织、模块边界、上手？ | "
            f"{_link('CLAUDE.md')} · {_link('docs/DOCUMENT_SYSTEM.md')} · "
            f"{_link('docs/manuals/getting-started.md')} · "
            f"{_link('docs/architecture/plans/app-module-layout.md')} | — |",
            f"| **集成架构** | MCP/A2A/外部适配？ | "
            f"{_link('docs/mcp/index.md')} · "
            f"{_link('docs/policy/mcp-stdio-prod-allowlist.md')} | "
            f"分卷 04 · CAPABILITIES「MCP / A2A」 |",
            f"| **质量属性 / SLA·SLO** | 可用性目标与误差预算？ | "
            f"{_link('docs/architecture/slo.md')} · "
            f"{_link('docs/architecture/execution-quality-gates.md')} | "
            "CAPABILITIES「管理 & 质量」 |",
            "",
            "> **阅读约定**：上表保证「只读本卷也能知道去哪尽调」。"
            "性能容量叙事以规范预算 + `benchmark_all.sh` + SLO 为准；"
            "若缺少独立压测报告，以脚本与门禁结果为可执行证据，勿在卷内编造 QPS 数字。",
            "",
        ]
    elif vid == "product-capability":
        parts += [
            "### 3.0 典型产品场景 → 权威入口（场景切片，非第二清单）",
            "",
            "| 场景 | 客户要解决的问题 | 从哪里看能力/怎么做 |",
            "|------|------------------|---------------------|",
            "| **FDE 交付** | 把业务问题做成可签收的 AI 交付 | "
            f"{_link('docs/manuals/fde/README.md')} · CAPABILITIES「平台治理 / FDE」 |",
            "| **App 工厂 / Builder** | 从需求到 Agent/应用产物 | "
            f"管理端 Builder · {_link('docs/architecture/plans/pi-thin-runtime.md')}（厂外交付边界） |",
            "| **Workbench** | 开发与调试工作台 | "
            f"{_link('docs/manuals/management.md') if _rel('docs/manuals/management.md').is_file() else _link('docs/manuals/getting-started.md')} · CAPABILITIES「Workbench」 |",
            "| **评测治理** | 评测流程与治理规则 | CAPABILITIES「评测 / Governance」 |",
            "| **ORG 签收** | 组织级签收与现场闭环 | CAPABILITIES「apps/org」· manuals |",
            "| **渠道接入** | 多渠道消息与集成 | CAPABILITIES「Channel」· 应用端 channels |",
            "| **知识 / 本体 / RAG** | 企业知识可检索、可治理 | "
            f"{_link('docs/knowledge-system.md') if _rel('docs/knowledge-system.md').is_file() else _link('docs/manuals/ontology.md')} · CAPABILITIES「知识引擎 / RAG」 |",
            "| **Agent / Skill 运行** | 多步工具调用与技能执行 | "
            "CAPABILITIES「Agent 系统 / Skill 系统」· "
            f"{_link('docs/architecture/execution-decision-matrix.md')} |",
            "| **治理下执行** | 权限、审批、审计可证明 | "
            "安全与治理分卷 · CAPABILITIES「Gate / 安全与治理」 |",
            "| **薄交付（Pi）** | 用户侧轻量跑快照、不装全栈 | "
            f"{_link('docs/architecture/plans/pi-thin-runtime.md')} · "
            f"{_link('packages/aiplat-pi-runtime/README.md')} |",
            "",
            "> 上表只指路。**接线以 "
            f"{_link('AIPLAT_CAPABILITIES.md')} 行为为准**；"
            f"{_link('docs/manuals/README.md') if _rel('docs/manuals/README.md').is_file() else _link('docs/manuals/getting-started.md')} "
            "仅提供操作说明，不作为行为契约。",
            "",
            "### 3.1 能力统计（摘自 CAPABILITIES）",
            "",
        ]
        if CAPS.is_file():
            raw = CAPS.read_text(encoding="utf-8")
            m = re.search(
                r"## 统计\s*\n+(.*?)(?:\n---|\n\*最后更新|\Z)", raw, re.S
            )
            if m:
                table_lines = []
                for line in m.group(1).splitlines():
                    if line.strip().startswith("|"):
                        table_lines.append(line)
                    elif table_lines:
                        break
                parts.append("\n".join(table_lines) or m.group(1)[:3000])
            parts += [
                "",
                "### 3.2 上手路径（节选）",
                "",
            ]
            excerpt, _ = _read_excerpt(
                _rel("docs/manuals/getting-started.md"), 5000
            )
            parts += [
                excerpt,
                "",
                "### 3.3 交付边界（Pi 薄 Runtime）",
                "",
            ]
            excerpt, _ = _read_excerpt(
                _rel("docs/architecture/plans/pi-thin-runtime.md"), 8000
            )
            parts += [
                excerpt,
                "",
                "> 完整能力表见总白皮书第 3 章或直接打开 "
                f"{_link('AIPLAT_CAPABILITIES.md')}。",
                "",
            ]
        else:
            parts.append("_(CAPABILITIES 缺失)_")
    elif vid == "commercial-value":
        parts += [
            "### 3.0 商业价值模型",
            "",
            "本卷不引用未授权的客户 ROI、人天单价或伙伴分成比例。"
            "商业论证以平台已接线的价值系统为准：",
            "",
            f"- 价值维度与算法符号：{_link('aiPlat-core/core/harness/finance/value_calculator.py')}",
            f"- 五维价值映射与 TCO 对照：{_link('docs/whitepaper/commercial-value-model.md')}",
            "- CEO/CFO/PM 翻译口径：见 `commercial-value-model.md` 第 2 节",
            "- 分阶段落地闸门：见 `commercial-value-model.md` 第 4 节",
            f"- 示意案例：{_link('docs/whitepaper/cases/internal-illustrative-fde.md')}",
            "",
            "---",
            "",
            "> **非客户授权案例声明**",
            ">",
            "> `cases/internal-illustrative-fde.md` 为内部示意，"
            "`authorized: false`、`kind: illustrative`，仅用于说明算法与口径，"
            "不构成任何客户承诺或收益保证。真实客户案例必须走 "
            f"{_link('docs/whitepaper/cases/README.md')} 授权流程。",
            "",
            "---",
            "",
            "商业卷 ready 边界：价值系统已接线、TCO 对照清单已闭环、"
            "内部示意 worked example 已标注。"
            "真实客户数字与商务条款后续只追加 `cases/` 与商务附录，不重做卷骨架。",
            "",
            "### 3.1 价值模型专稿（节选）",
            "",
        ]
        excerpt, _ = _read_excerpt(
            _rel("docs/whitepaper/commercial-value-model.md"), 8000
        )
        parts += [
            excerpt,
            "",
            _assessment_stamp(),
            "### 3.2 商业化路线图（节选）",
            "",
            "> 下列 ROADMAP 是内部作战手册节选，不是对外已审计财报；"
            "勿将路线图基线误读为客户授权 ROI。",
            "",
        ]
        excerpt, _ = _read_excerpt(_rel("AIPLAT_ROADMAP.md"), 12000)
        parts += [excerpt, ""]
        if _rel("docs/strategy/comparison-vs-vendors.md").is_file():
            parts += ["### 3.3 厂商策略对比（节选）", ""]
            excerpt, _ = _read_excerpt(
                _rel("docs/strategy/comparison-vs-vendors.md"), 8000
            )
            parts += [excerpt, ""]
    elif vid == "ecosystem-integration":
        parts += [
            "### 3.0 生态伙伴分层与开放边界",
            "",
            "本卷以技术伙伴分层闭环，不写未确认的分成比例、商标授权或排他条款。",
            "",
            f"- 技术分层：{_link('docs/whitepaper/ecosystem-partner-tiers.md')}",
            "  - Pi-only 接入",
            "  - KB 混合接入",
            "  - 工具代理接入",
            "  - MCP / API ISV 接入",
            "  - 私有化厚部署",
            "- 开放边界矩阵：见 `ecosystem-partner-tiers.md` 第 3 节",
            f"- 企业混合部署：{_link('packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md')}；"
            f"能力行以 {_link('AIPLAT_CAPABILITIES.md')} 为准",
            f"- 商务条款模板：{_link('docs/whitepaper/ecosystem-partner-commercial-template.md')}",
            "",
            "---",
            "",
            "> **商务条款声明**",
            ">",
            "> 分成、权益、商标、排他等条款以双方盖章版协议为准。"
            "`ecosystem-partner-commercial-template.md` 仅为空白模板，不构成要约。",
            "",
            "---",
            "",
            "生态卷 ready 边界：技术分层与开放边界已闭环；"
            "商务条款提供可盖章模板附录；正文不写假分成。",
            "",
            "### 3.1 技术分层专稿（节选）",
            "",
        ]
        excerpt, _ = _read_excerpt(
            _rel("docs/whitepaper/ecosystem-partner-tiers.md"), 8000
        )
        parts += [
            excerpt,
            "",
            "### 3.2 开放边界矩阵（接入面）",
            "",
            "| 接入面 | 伙伴/集成商做什么 | 权威入口 | 平台侧治理 |",
            "|--------|-------------------|----------|------------|",
            "| **MCP 工具** | 注册/暴露工具供 Agent 调用 | "
            f"{_link('docs/mcp/index.md')} | "
            f"{_link('docs/policy/mcp-stdio-prod-allowlist.md')} + 成本阶梯 |",
            "| **HTTP API** | 调平台/Core 能力 | "
            f"{_link('docs/API/api-reference.md')} | 鉴权 / 租户 / 限流（platform） |",
            "| **A2A** | Agent 间互操作 | CAPABILITIES「A2A 协议」切片 | PolicyGate / 身份透传 |",
            "| **Pi Package** | 消费工厂导出的薄 Runtime 包 | "
            f"{_link('packages/aiplat-pi-runtime/README.md')} · "
            f"{_link('docs/architecture/plans/pi-thin-runtime.md')} | "
            "能力边界写进交付说明（无平台 Memory/SECI） |",
            "| **Skill / Handler** | 贡献可执行技能 | CAPABILITIES「Skill 系统」· engine skills | "
            "`execution_type` + lint + 准入 |",
            "",
            "### 3.3 MCP / A2A 能力切片（CAPABILITIES）",
            "",
            _caps_section_extract(["MCP 协议", "A2A 协议"], 6000),
            "",
            "### 3.4 MCP 文档入口",
            "",
        ]
        excerpt, _ = _read_excerpt(_rel("docs/mcp/index.md"), 5000)
        parts += [excerpt, "", "### 3.5 MCP 生产准入", ""]
        excerpt, _ = _read_excerpt(
            _rel("docs/policy/mcp-stdio-prod-allowlist.md"), 6000
        )
        parts += [excerpt, "", "### 3.6 API 参考（节选）", ""]
        excerpt, _ = _read_excerpt(_rel("docs/API/api-reference.md"), 8000)
        parts += [excerpt, "", "### 3.7 厂外 Pi Package", ""]
        excerpt, _ = _read_excerpt(
            _rel("packages/aiplat-pi-runtime/README.md"), 6000
        )
        parts += [excerpt, ""]
        if _rel("docs/API/AttributionSchema.md").is_file():
            parts += ["### 3.8 归因协议（节选）", ""]
            excerpt, _ = _read_excerpt(
                _rel("docs/API/AttributionSchema.md"), 4000
            )
            parts += [excerpt, ""]
    elif vid == "security-governance":
        parts += [
            "### 3.0 治理与安全材料",
            "",
            "治理卷材料已厚，本卷 suite 状态为 ready，保留以下权威源：",
            "",
            f"- 评分戳：{_link('docs/framework/assessment-scores.json')}",
            f"- 安全架构：{_link('docs/security/security-architecture.md')}",
            f"- Gate 与安全能力：{_link('AIPLAT_CAPABILITIES.md')} 中 Gate / 安全节",
            f"- L 级 ADR：{_link('docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md')}",
            "",
            "> 治理卷不新增示意案例，不引用未授权客户数据。",
            "",
            "### 3.1 权威评分戳",
            "",
            _assessment_stamp(),
            "### 3.2 安全架构（节选）",
            "",
        ]
        excerpt, _ = _read_excerpt(
            _rel("docs/security/security-architecture.md"), 12000
        )
        parts += [excerpt, "", "### 3.3 CAPABILITIES：安全与治理 / Gate", ""]
        parts += [
            _caps_section_extract(["安全与治理", "Gate 系统"], 10000),
            "",
            "### 3.4 自主性定级 ADR（节选）",
            "",
        ]
        excerpt, _ = _read_excerpt(
            _rel("docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md"),
            8000,
        )
        parts += [excerpt, ""]
    else:
        parts.append("_(未知 volume id)_")

    parts += [
        "## 4. 相关横切（对标 / 评级）",
        "",
        "完整对标与评级目录见总白皮书 §2.5 与 "
        f"{_link('docs/whitepaper/WHITEPAPER_SYSTEM.md')}。",
        "",
        "## 5. 验证",
        "",
        "```bash",
        "python3 scripts/generate_whitepaper_volumes.py --check",
        "python3 scripts/generate_platform_whitepaper.py --check",
        "```",
        "",
        f"*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`{vid}`*",
        "",
    ]
    return "\n".join(parts)


def generate_all() -> List[Path]:
    if not SUITE.is_file():
        raise SystemExit(f"FAIL: missing {SUITE}")
    suite = _load_yaml(SUITE)
    suite_sha = _sha256_file(SUITE)
    caps_sha = _sha256_file(CAPS)
    scores_sha = _sha256_file(SCORES)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for vol in suite.get("volumes") or []:
        vid = vol["id"]
        fname = VOLUME_FILES.get(vid)
        if not fname:
            print(f"WARN: no outfile mapping for {vid}", file=sys.stderr)
            continue
        out = OUT_DIR / fname
        out.write_text(
            _build_volume(vol, suite_sha, caps_sha, scores_sha, generated_at),
            encoding="utf-8",
        )
        written.append(out)
        print(f"PASS: wrote {out.relative_to(REPO)}")
    # index
    index = OUT_DIR / "README.md"
    lines = [
        "# 五维白皮书分卷（生成物）",
        "",
        "> 由 `scripts/generate_whitepaper_volumes.py` 根据 "
        "`../whitepaper-suite.yaml` + CAPABILITIES + assessment-scores 生成。勿手改正文。",
        "",
        "| 卷 | 文件 |",
        "|----|------|",
    ]
    for vol in suite.get("volumes") or []:
        vid = vol["id"]
        fname = VOLUME_FILES.get(vid, "")
        lines.append(f"| {vol.get('name')} (`{vid}`) | [{fname}](./{fname}) |")
    lines += [
        "",
        f"suite_sha256=`{suite_sha}` · caps_sha256=`{caps_sha}` · "
        f"scores_sha256=`{scores_sha}` · generated_at=`{generated_at}`",
        "",
        "同步：`bash scripts/sync_whitepapers.sh`",
        "",
    ]
    index.write_text("\n".join(lines), encoding="utf-8")
    written.append(index)
    print(f"PASS: wrote {index.relative_to(REPO)}")
    return written


def check_fresh() -> int:
    if not SUITE.is_file():
        print(f"FAIL: missing {SUITE}", file=sys.stderr)
        return 2
    suite_sha = _sha256_file(SUITE)
    caps_sha = _sha256_file(CAPS)
    scores_sha = _sha256_file(SCORES)
    suite = _load_yaml(SUITE)
    ok = True
    for vol in suite.get("volumes") or []:
        vid = vol["id"]
        fname = VOLUME_FILES.get(vid)
        if not fname:
            continue
        path = OUT_DIR / fname
        if not path.is_file():
            print(f"FAIL: missing volume {path}", file=sys.stderr)
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        m = STAMP_RE.search(text)
        if (
            not m
            or m.group(1) != vid
            or m.group(2) != suite_sha
            or m.group(3) != caps_sha
            or m.group(4) != scores_sha
        ):
            print(
                f"FAIL: stale volume {path.relative_to(REPO)} "
                f"— run: bash scripts/sync_whitepapers.sh",
                file=sys.stderr,
            )
            ok = False
    if ok:
        print(
            "PASS: all five whitepaper volumes fresh vs "
            "suite + CAPABILITIES + assessment-scores"
        )
        return 0
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.check:
        return check_fresh()
    generate_all()
    return check_fresh()


if __name__ == "__main__":
    raise SystemExit(main())
