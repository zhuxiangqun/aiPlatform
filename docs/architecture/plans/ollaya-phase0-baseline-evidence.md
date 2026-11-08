# Ollaya 决策层 · 阶段 0 证据包（进行中）

> **状态**：工程可采数已接线 · **≠ 阶段 0 完成 · ≠ Go 阶段 1 · ≠ 已立项 · ≠ 影子已开**  
> **依据**：[ollaya-decision-layer-implementation-plan.md](./ollaya-decision-layer-implementation-plan.md) §4  
> **日期**：2026-11-08（续 · ops 采数面）

## 0.1 观测窗口与环境说明（模板 · 待负责人填实）

| 字段 | 填写 |
|------|------|
| 环境 | ☐dev ☐staging ☐prod（分表，勿混） |
| 观测窗口起止 | ____ ～ ____（建议 ≥7 天或业务高峰周） |
| 进程/副本 | 部署拓扑简述；**每进程各自计数**（进程内共享，跨副本需聚合） |
| 采集方式 | `GET /api/core/diagnostics/domain-router/route-stats`（见下）或同进程 `CoreFacade.domain_router_route_stats()` |
| 联系人 | |

## 0.2 埋点设计（已扩展现有 `route_stats`）

| 项 | 现状 |
|----|------|
| 权威位置 | `aiPlat-core/core/harness/knowledge/domain_router.py` |
| 进程共享 | ✅ 类级 `_ROUTE_STATS`（修复「每次 `DomainRouter()` 新建导致计数恒空」） |
| 单例入口 | ✅ `get_domain_router()`；`CoreFacade.get_domain_router` / `domain_router_route_stats` |
| HTTP 采数 | ✅ `GET /diagnostics/domain-router/route-stats`（经 CoreFacade；管理端常挂 `/api/core/...`） |
| 字段 | `total` / `t1_hits` / `t2_hits` / `t3_hits` + 占比；`t3_latency_ms_p50` / `p95`；`t2_boundary_hits` / `t2_reject_hits`（旁路计数，不进 total）；`stats_uptime_s` |
| 不做 | 不落盘用户原文；不开 `decision_shadow`；不改 `classify()` 返回语义 |

快照诚实字段：`scope=process`；`honesty` 标明重启清零、旁路计数语义、≠ 影子延迟、≠ accuracy、≠ Go。

**T2 边界定义（有条件 Go）**：T1 未命中且 T2 **接受**，但 `score < min_conf + boundary_score_slack`（默认 0.05）或 `margin < min_margin * boundary_margin_factor`（默认 2.0）。`t2_reject_hits` = 有 embedding 信号但未过阈值、将走 T3。

## 0.3 / 0.4 采集表（待现网窗口填数）

| 环境 | 窗口 | total | t1% | t2% | t3% | t3_n | T3 p50 ms | T3 p95 ms | t2_boundary | t2_reject | 备注 |
|------|------|------|-----|-----|-----|------|-----------|-----------|-------------|-----------|------|
| | | | | | | | | | | | |

### 运维采数（推荐）

在**承载 classify 流量的同一 core 进程**上（网关/反向代理路径以部署为准）：

```bash
# 例：本地 / 已代理到 core
curl -sS "$CORE_BASE/api/core/diagnostics/domain-router/route-stats" | python3 -m json.tool
```

同进程 Python（调试用）：

```bash
python3 -c "
from core.api.core_facade import domain_router_route_stats
print(domain_router_route_stats())
"
```

**注意**：新开 CLI 进程计数为 0；多副本须每副本拉一次再人工加总；进程重启清零。

## 0.5 意图路由 `classify_with_llm` 调用链 ✅

| 项 | 结论 |
|----|------|
| 定义位置 | `aiPlat-core/core/harness/routing/classifier.py` |
| 生产调用方 | **未发现**：`classify_with_llm(` 仅命中定义 |
| 宣讲约束 | **禁止**「引入 Ollaya 即可省线上意图 LLM fallback」 |

```bash
rg -n 'classify_with_llm\(' --glob '*.py'
```

## 0.6 阶段 1 工程约束评审包

设计正文已在实施方案 §5–§6（异步/队列/超时/采样/审计白名单）。  
本阶段交付：**评审用检查表**（仍待评审会签字）：

| # | 检查项 | 状态 |
|---|--------|------|
| C1 | 影子关闭时 `classify` 返回语义不变 | 设计约定；未实现影子故 trivially 真 |
| C2 | 主路径无 await 决策 HTTP | 未接线 |
| C3 | 队列满/超时仅 drop | 未接线 |
| C4 | `decision_shadow.enabled` 默认 false | 未接线 |
| C5 | 审计字段 ⊆ 白名单；默认无原文 | 见方案 §5.4 / §6 |
| C6 | 可一键关闭 | 未接线 |

→ 评审会前禁止合并影子代码。

## 0.7 Go / No-Go

| 结论 | 条件 |
|------|------|
| Go 阶段 1 | 0.1–0.4 表填实 + 0.6 评审通过 + T3（或边界带）样本达标 |
| 有条件 Go | T3 少但 `t2_boundary_hits` 样本足，且约定只影子边界样本 |
| No-Go | 几乎无 T3/边界；或无法脱敏审计；或无人维护决策服务 |

**当前书面结论**：❌ 未开 Go（缺现网窗口数据与评审纪要）。

## 明确不交付

影子延迟、Ollaya 准确率、线上替换、`decision_shadow` 包。

## 下一步

1. 负责人填 0.1；运维对目标环境副本周期性 `curl` 填 0.3/0.4。  
2. 召开 0.6 评审 → 0.7 书面 Go/No-Go。  
3. **仅 Go 后** 才允许实现阶段 1 影子。
