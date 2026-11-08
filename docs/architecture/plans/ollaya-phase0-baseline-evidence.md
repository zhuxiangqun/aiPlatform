# Ollaya 决策层 · 阶段 0 证据包（进行中）

> **状态**：工程可采数已接线 · **≠ 阶段 0 完成 · ≠ Go 阶段 1 · ≠ 已立项 · ≠ 影子已开**  
> **依据**：[ollaya-decision-layer-implementation-plan.md](./ollaya-decision-layer-implementation-plan.md) §4  
> **日期**：2026-11-08（续 · collector + 评审包）

## 0.1 观测窗口与环境说明（模板 · 待负责人填实）

| 字段 | 填写 |
|------|------|
| 环境 | ☐dev ☐staging ☐prod（分表，勿混） |
| 观测窗口起止 | ____ ～ ____（建议 ≥7 天或业务高峰周） |
| 进程/副本 | 部署拓扑简述；**每进程各自计数**（进程内共享，跨副本需聚合） |
| 采集方式 | `scripts/collect_domain_router_route_stats.py` 或 `GET /api/core/diagnostics/domain-router/route-stats` |
| 联系人 | |

## 0.2 埋点设计（已扩展现有 `route_stats`）

| 项 | 现状 |
|----|------|
| 权威位置 | `aiPlat-core/core/harness/knowledge/domain_router.py` |
| 进程共享 | ✅ 类级 `_ROUTE_STATS`（修复「每次 `DomainRouter()` 新建导致计数恒空」） |
| 单例入口 | ✅ `get_domain_router()`；`CoreFacade.get_domain_router` / `domain_router_route_stats` |
| HTTP 采数 | ✅ `GET /diagnostics/domain-router/route-stats`（经 CoreFacade；管理端常挂 `/api/core/...`） |
| 运维脚本 | ✅ `scripts/collect_domain_router_route_stats.py`（JSONL + markdown 表行；多 `--base` 可 `--aggregate`） |
| 字段 | `total` / `t1_hits` / `t2_hits` / `t3_hits` + 占比；`t3_latency_ms_p50` / `p95`；`t2_boundary_hits` / `t2_reject_hits`（旁路计数，不进 total）；`stats_uptime_s` |
| 不做 | 不落盘用户原文；不开 `decision_shadow`；不改 `classify()` 返回语义 |

快照诚实字段：`scope=process`；`honesty` 标明重启清零、旁路计数语义、≠ 影子延迟、≠ accuracy、≠ Go。

**T2 边界定义（有条件 Go）**：T1 未命中且 T2 **接受**，但 `score < min_conf + boundary_score_slack`（默认 0.05）或 `margin < min_margin * boundary_margin_factor`（默认 2.0）。`t2_reject_hits` = 有 embedding 信号但未过阈值、将走 T3。

## 0.3 / 0.4 采集表（待现网窗口填数）

| 环境 | 窗口 | total | t1% | t2% | t3% | t3_n | T3 p50 ms | T3 p95 ms | t2_boundary | t2_reject | 备注 |
|------|------|------|-----|-----|-----|------|-----------|-----------|-------------|-----------|------|
| | | | | | | | | | | | |

### 运维采数（推荐）

**先确认 core 已部署含 PR #612 的二进制**（本机旧进程 OpenAPI 可能尚无 `route-stats` → 需重启/重部署）。

```bash
# 单副本 → 打印可粘贴进上表的 markdown 行，并追加 JSONL
python3 scripts/collect_domain_router_route_stats.py \
  --base "${CORE_BASE:-http://127.0.0.1:8002}" \
  --env staging \
  --window '2026-11-01..2026-11-08' \
  --jsonl .aiplat/ollaya_phase0/route_stats.jsonl

# 多副本：每副本一行；可选 --aggregate 加总命中（延迟 p50/p95 不跨副本合并）
python3 scripts/collect_domain_router_route_stats.py \
  --base http://core-a:8002 --base http://core-b:8002 \
  --env prod --aggregate --jsonl .aiplat/ollaya_phase0/route_stats.jsonl
```

同进程 Python（调试用，**新开 CLI 进程计数为 0**）：

```bash
python3 -c "
from core.api.core_facade import domain_router_route_stats
print(domain_router_route_stats())
"
```

## 0.5 意图路由 `classify_with_llm` 调用链 ✅

| 项 | 结论 |
|----|------|
| 定义位置 | `aiPlat-core/core/harness/routing/classifier.py` |
| 生产调用方 | **未发现**：`classify_with_llm(` 仅命中定义 |
| 宣讲约束 | **禁止**「引入 Ollaya 即可省线上意图 LLM fallback」 |

```bash
rg -n 'classify_with_llm\(' --glob '*.py'
```

## 0.6 阶段 1 工程约束评审包（待会签）

设计正文：实施方案 §5–§6。本表供评审会勾选；**未签字前禁止合并影子代码**。

| # | 检查项 | 设计约定 | 评审结论 |
|---|--------|----------|----------|
| C1 | 影子关闭时 `classify` 返回语义不变 | 钩子仅 fire-and-forget；默认关 | ☐通过 ☐有条件 ☐驳回 |
| C2 | 主路径无 await 决策 HTTP | 禁止在 `_llm_classify` 同步调决策服务 | ☐通过 ☐有条件 ☐驳回 |
| C3 | 队列满/超时仅 drop | 有界队列；失败不冒泡 | ☐通过 ☐有条件 ☐驳回 |
| C4 | `decision_shadow.enabled` 默认 false | YAML/配置默关 | ☐通过 ☐有条件 ☐驳回 |
| C5 | 审计字段 ⊆ 白名单；默认无原文 | `store_raw_text=false`；TTL 短 | ☐通过 ☐有条件 ☐驳回 |
| C6 | 可一键关闭 | env/配置热更新或重启策略书面化 | ☐通过 ☐有条件 ☐驳回 |
| C7 | 隐私/脱敏策略已批 | 字段表见方案 §5.4 / §6 | ☐通过 ☐有条件 ☐驳回 |
| C8 | 有人维护决策服务 | 值班/健康检查入口明确 | ☐通过 ☐有条件 ☐驳回 |

| 字段 | 填写 |
|------|------|
| 评审日期 | |
| 与会人 | |
| 纪要链接/附件 | |
| 会签（试点负责人） | ☐签字 |

## 0.7 Go / No-Go（建议默认阈值 · 立项会可改）

| 结论 | 建议默认条件（可改） |
|------|----------------------|
| **Go 阶段 1** | 0.1 填实；0.3/0.4 表有真实窗口；0.6 C1–C8 会签通过；且窗口内 **`t3_hits ≥ 100`** **或** **`t3_llm_pct ≥ 5%` 且 total ≥ 500** |
| **有条件 Go** | T3 未达标，但 **`t2_boundary_hits ≥ 100`**，且书面约定影子 trigger 仅 `t2_boundary`（或等价） |
| **No-Go** | T3 与 boundary 均远低于阈值；或 C5/C7/C8 任一驳回；或无人维护决策服务 |
| **意图叙事** | 维持 0.5：禁止「省线上意图 LLM fallback」 |

**当前书面结论**：❌ 未开 Go（缺现网窗口数据与 0.6 会签）。

## 明确不交付

影子延迟、Ollaya 准确率、线上替换、`decision_shadow` 包。

## 下一步

1. **重启/重部署** 含 route-stats 端点的 core，再跑 collector 填 0.3/0.4。  
2. 负责人填 0.1；召开 0.6 评审 → 按 0.7 出书面 Go/No-Go。  
3. **仅 Go 后** 才允许实现阶段 1 影子。
