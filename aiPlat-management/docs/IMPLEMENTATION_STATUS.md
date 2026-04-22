# aiPlat-management 实施状态（As-Is vs To-Be）

日期：2026-04-16  
适用范围：`aiPlat-management/`（管理平面）

> 本文件用于**澄清“设计正确（To‑Be）”与“当前实现（As‑Is）”**的差异，避免把原型代码误认为已完成的生产实现。

## 1. 设计原则（To‑Be，作为规范）

1) **管理平面 vs 业务平面**：management 只做聚合、编排、治理与审计；业务逻辑与资源操作必须由各层（infra/core/platform/app）实现。  
2) **数据来源单一**：management 通过 **HTTP 调用各层管理 API** 获取 status/metrics/health/diagnostics；不在自身进程内做“本机探测”或业务判断。  
3) **统一入口/统一状态**：management 内部对象（aggregator、engine、config_manager、clients）必须由应用级依赖注入统一管理（例如 `app.state`），避免模块级重复实例导致行为不一致。  
4) **可观测与审计优先**：对配置变更、告警规则、诊断动作应记录 author/trace_id/时间戳，并具备可回放查询。

## 2. 模块实施矩阵

| 模块 | To‑Be（设计目标） | As‑Is（当前代码） | 主要差距/风险 |
|---|---|---|---|
| API Gateway（统一入口） | 所有管理动作统一从 management 入口进入；向下游转发/聚合；鉴权与审计在此落点 | `management/api/infra.py`、`management/api/core.py` 已有 HTTP client 转发；鉴权/审计缺失 | 缺少 authn/authz；部分功能绕开 app.state 形成重复实例 |
| Dashboard（总览） | 聚合四层 status/metrics/health；数据来自各层 API；统一计算 overall_status | `DashboardAggregator` 存在；但 `dashboard/infra_adapter.py` 走本机探测，core/platform/app 多为 stub | 违反边界；数据口径不统一；配置不生效风险 |
| Monitoring（采集） | 定时采集 metrics 写入时序存储（InfluxDB 等）；对外提供图表查询 | collector 框架存在；存储/调度未形成闭环 | “指标采集→存储→查询”断裂 |
| Alerting（告警） | 规则持久化 + 生命周期 + 去重/抑制 + 通知通道 + 历史查询 | `AlertEngine`/`active_alerts` 纯内存原型 | 重启丢失；无通知；无历史/审计 |
| Diagnostics（诊断） | 诊断逻辑在各层；management 聚合/标准化输出；支持 trace/logs 链接 | `api/diagnostics.py` 存在；`diagnostics/*` 大量 mock；`trace` 接口未实现 | 诊断结果不可信；tracing/logging 断裂 |
| Config（配置） | 版本控制/发布/回滚；配置落库；对各层下发并记录审计 | `ConfigManager` 内存版本链；无下发 | 重启丢失；无法治理；与文档承诺不符 |

## 2.1 已落地能力补充（As-Is，2026-04-23）

近期已落地并可用的“核心能力层治理/学习/诊断”能力（management 前端）：

- Runs（Diagnostics）
  - `run_id` 查询、run_events 浏览
  - 自动评估（auto-eval）触发与结果阅读（PASS/FAIL、issues、证据跳转）
  - 全局策略/项目策略编辑（evaluation_policy）
- Learning Artifacts（Core → Learning）
  - artifacts 列表过滤（kind/status/target/run_id/trace_id）
  - URL 固定以便分享与复现查询
  - Artifact 详情摘要（evaluation/evidence/diff/policy/run_state）与 evaluation_report 的 Issues 专用 Tab

对应说明文档：
- `docs/core/learning.md`

## 3. 推荐里程碑（从 As‑Is 迁移到 To‑Be）

**M0（P0）**：统一依赖注入（所有 API 使用 `app.state`），移除路由模块的重复实例。  
**M1（P0）**：Dashboard/Diagnostics 全部改为 HTTP 数据源（各层 status/metrics/health），移除 management 本机探测与 mock。  
**M2（P1）**：Config/Alerting 最小落库（SQLite 即可）+ 审计字段（author/trace_id）+ 回滚能力。  
**M3（P1/P2）**：鉴权与审计打通；tracing/logs 在 UI 与 API 中可见并可关联到 core 的 trace/run/checkpoint。
