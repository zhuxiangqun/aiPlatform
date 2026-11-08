# Ollaya 决策层 · 阶段 0 证据包（进行中）

> **状态**：工程可采数已接线 · 默关 `decision_shadow` 骨架已合入并本机探测 · C6 关闭演练草稿已备 · **≠ 开采样影子 · ≠ 挂 classify · ≠ 1b 替换 · ≠ 省 token**  
> **依据**：[ollaya-decision-layer-implementation-plan.md](./ollaya-decision-layer-implementation-plan.md) §4 / §0.7 有条件豁免  
> **日期**：2026-11-08（续 · #616 合入后探测 + C6 附页）

## 0.1 观测窗口与环境说明（模板 · 待负责人填实）

| 字段 | 填写 |
|------|------|
| 环境 | ☑dev ☐staging ☐prod（分表，勿混） |
| 观测窗口起止 | 本机冒烟：`2026-11-08T12:20+08`（重启后即时快照）· **staging/prod ≥7 天窗口仍待填** |
| 进程/副本 | 本机 `gunicorn -w 1` @ `127.0.0.1:8002`（#616 后 SIGHUP 重载）；**每进程各自计数** |
| 采集方式 | `scripts/collect_domain_router_route_stats.py` 或 `GET /api/core/diagnostics/domain-router/route-stats`；影子骨架另见 `GET /diagnostics/decision-shadow/status` |
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
| 不做 | 不落盘用户原文；**不开**采样影子 / **不挂** classify；不改 `classify()` 返回语义（默关骨架可存在） |

快照诚实字段：`scope=process`；`honesty` 标明重启清零、旁路计数语义、≠ 影子延迟、≠ accuracy、≠ Go。

**T2 边界定义（有条件 Go）**：T1 未命中且 T2 **接受**，但 `score < min_conf + boundary_score_slack`（默认 0.05）或 `margin < min_margin * boundary_margin_factor`（默认 2.0）。`t2_reject_hits` = 有 embedding 信号但未过阈值、将走 T3。

## 0.3 / 0.4 采集表（本机冒烟已填 · staging/prod 窗口仍空）

| 环境 | 窗口 | total | t1% | t2% | t3% | t3_n | T3 p50 ms | T3 p95 ms | t2_boundary | t2_reject | 备注 |
|------|------|------|-----|-----|-----|------|-----------|-----------|-------------|-----------|------|
| dev | 2026-11-08T12:20+08 post-restart | 0 | 0.0 | 0.0 | 0.0 | 0 | None | None | 0 | 0 | #613 合入后重启 gunicorn；uptime≈70s；JSONL→`.aiplat/ollaya_phase0/route_stats.jsonl`；全 0 为预期（无 classify 流量）≠ Go |
| dev | 2026-11-08T12:25+08 after-classify-smoke | 10 | 30.0 | 0.0 | 70.0 | 7 | 0.085 | 2.218 | 0 | 3 | 经 `POST /skills/domain_assessor/execute` 打 8 条（含先验 2）；T1=3/T3=7/t2_reject=3；T3 p50 亚毫秒疑似 LLM 快速失败/降级，**≠ 真实 T3 延迟、≠ Go** |
| dev | 2026-11-08T14:06+08 post-616-reload | 0 | 0.0 | 0.0 | 0.0 | 0 | None | None | 0 | 0 | #616 合入后 SIGHUP；uptime≈378s；计数因重载清零（预期）；**另**见 §0.3.1 影子骨架探测 |

### 0.3.1 默关 `decision_shadow` 本机探测（#616）

| 项 | 结果 |
|----|------|
| `GET /api/core/diagnostics/decision-shadow/status` | `ok=true`；`enabled=false`；`classify_hook_wired=false`；`endpoint_configured=false` |
| `POST …/try-enqueue` | `accepted=false`；`drops.disabled=1`（默关拒投） |
| JSONL | `.aiplat/ollaya_phase0/decision_shadow_status.jsonl` |
| 诚实 | **≠** 采样 Go · **≠** classify 钩子 · **≠** 省 token · **≠** 1b |

### 运维采数（推荐）

**本机已确认**：重启后 OpenAPI 含 `/api/core/diagnostics/domain-router/route-stats`（HTTP 200）。staging/prod 仍须部署含 #612+#613 的二进制后再采。

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

### 0.6.1 工程自评草稿（2026-11-08 · **≠ 会签 · ≠ 授权写影子**）

对照 [ollaya-decision-layer-implementation-plan.md](./ollaya-decision-layer-implementation-plan.md) §5–§6。仅工程视角预审设计完备性；**不**勾选上方正式「评审结论」，**不**代替试点负责人/隐私签字。

| # | 工程建议 | 设计锚点 | 残差 / 会前必补 |
|---|----------|----------|-----------------|
| C1 | **建议通过**（设计层） | §5.1 C1；§5.3：`classify` 即将 return 前 `try_enqueue`，立即 return | 默关包 + `classify_hook_wired=false` 已合入（#616）；挂钩后须补「enabled=false vs 无钩子」同输入对照单测 |
| C2 | **建议通过**（设计层） | §5.1 C2；§5.3 禁止在 `_llm_classify` 内同步调决策服务 | code review + 超时注入验收项保留；适配层隔离 HTTP（§5.5） |
| C3 | **建议通过**（设计层） | §5.1 C3；§5.2 `queue_size` / `timeout_ms`；§5.6 drop 计数 | 骨架已有 disabled/queue_full 等 drop；开采样前须补 timeout / endpoint-down 故障注入 |
| C4 | **建议通过**（设计层+骨架） | §5.2 `decision_shadow.enabled` 默认 `false`；本机 status 已证 | 合并门禁：PR 不得将默认改为 true；配置进 YAML、密钥进 env |
| C5 | **建议有条件通过** | §5.2 `store_raw_text=false`；§5.4 字段进审计库列；§6.1–2 白名单+TTL | 条件：隐私角色确认白名单与 TTL 数字；抽样 20 条验收（§6）写进变更单 |
| C6 | **建议有条件通过**（附页已备） | §5.1 C6；见 [ollaya-decision-shadow-kill-switch.md](./ollaya-decision-shadow-kill-switch.md) | 条件：正式会确认「需 SIGHUP/重启」策略；开采样后再做打开→关闭回滚实演 |
| C7 | **待隐私批（工程不可自签）** | §5.4 payload 表；§6 五条合规 | 无隐私签字 → 正式表保持空/有条件；**单独驳回则 No-Go**（§0.7） |
| C8 | **待负责人指定（工程不可自签）** | 方案角色表：决策服务值班/健康检查 | 未指定 owner / 无健康检查入口 → 建议正式会 **驳回或 No-Go** |

**工程总评（草稿）**：默关骨架已合入（有条件豁免）；C1–C4/C6 工程附页就绪。C5 需隐私附页；C7–C8 **未闭环**；staging/prod 窗口未填。在 0.3/0.4 现网窗口与 0.6 正式会签前，**采样 Go / 挂 classify 仍不可开**。

## 0.7 Go / No-Go（建议默认阈值 · 立项会可改）

| 结论 | 建议默认条件（可改） |
|------|----------------------|
| **Go 采样影子** | 0.1 填实；0.3/0.4 真实窗口；0.6 C1–C8 会签；且 **`t3_hits ≥ 100`** 或（`t3_llm_pct ≥ 5%` 且 total ≥ 500）——卡挂钩子/开采样 |
| **有条件 Go（流量）** | T3 未达标但 **`t2_boundary_hits ≥ 100`**，且约定 trigger 仅 `t2_boundary` |
| **有条件豁免（骨架）** | ✅ 已启用：默关包可合入；禁止默认开、禁止未批挂 classify |
| **No-Go（开流/1b）** | T3 与 boundary 均远低于阈值；或 C5/C7/C8 驳回；或无人维护决策服务 |
| **意图叙事** | 维持 0.5：禁止「省线上意图 LLM fallback」；骨架 ≠ 省 token |

**当前书面结论**：
- ✅ **有条件豁免（骨架）**：默关 `decision_shadow/` 可合入（`enabled=false`，`classify_hook_wired=false`）。
- ❌ **未开采样 Go**（本机 smoke `total=10`/`t3_hits=7` 远低于 0.7；缺 staging/prod 窗口与 0.6 正式会签）→ 不得挂 `classify`、不得开采样流量、不得进 1b。

## 明确不交付

影子延迟认证、Ollaya 准确率、线上 T3 替换、默认开启的采样影子。

## 下一步

1. ✅ 本机 core 已重启；collector 冒烟 + classify 流量行已写入 0.3/0.4 + JSONL。  
2. ✅ §0.6.1 工程自评草稿已备（≠ 会签）。  
3. ✅ 默关 `decision_shadow` 骨架合入（#616）+ status/try-enqueue 本机探测（§0.3.1）。  
4. ✅ C6 《一键关闭演练》工程附页：[ollaya-decision-shadow-kill-switch.md](./ollaya-decision-shadow-kill-switch.md)。  
5. staging/prod 部署后跑 collector 填真实窗口；负责人补全 0.1。  
6. 召开 0.6 正式评审 → 书面批准后另批「挂 classify 钩子 + 开采样」。  
7. **仅采样 Go 后** 才允许影子流量；**仅 1b 另案** 才谈替换 T3 / 省 token。
