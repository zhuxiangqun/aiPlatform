# aiPlat 设计文档 vs 代码实现：全量复审（含 aiPlat-management）

日期：2026-04-16  
范围：aiPlat-core + aiPlat-management（并参考 aiPlat-infra/aiPlat-platform/aiPlat-app 的接口边界描述）

## 1. 结论总览

### 1.1 aiPlat-core（Layer 1）
**总体判断：设计一致性显著提升，核心闭环已形成**  
你前面列的 7 项架构问题里，1-6 已基本落地；7（Hook 异常用 print）已修复为 logging（hook_manager + lifecycle manager）。

### 1.2 aiPlat-management（管理平面）
**总体判断：设计文档表达为“独立管理平面/统一入口/HTTP 调用各层”，但当前实现更接近“原型/脚手架”，存在较多设计偏差与实现断裂。**

最关键的 5 个偏差：
1) **数据源不一致**：Dashboard 的 InfraAdapter 直接在 management 进程内做本机探测（postgres/redis/milvus/ollama 等），而非通过 infra 层管理 API；Diagnostics 的 infra_health 又是大量 mock 值。  
2) **全局单例与 app.state 双套状态**：`management/server.py` 把 aggregator/alert_engine/config_manager 放入 `app.state`，但 `management/api/dashboard.py` / `management/api/alerting.py` 又各自创建独立实例，导致行为与配置不一致。  
3) **Core/Platform/App Adapter 多为静态假数据**：如 `dashboard/core_adapter.py` 不调用 core API，返回固定 healthy+计数；与“真实系统指标采集”目标不符。  
4) **配置管理/告警引擎不持久化且不下发**：ConfigManager/AlertEngine 都是进程内内存结构；无版本落库、无热更新/回滚对接到各层。  
5) **缺少统一权限/认证边界**：management 作为“统一入口”应至少具备 authn/authz 或透传策略；当前多数端点无鉴权逻辑。

## 2. 设计文档（management）要点摘录

### 2.1 README 目标（aiPlat-management/README.md）
- Dashboard 总览、Monitoring 指标采集、Alerting 规则与通知、Diagnostics 健康检查、Config 配置管理/版本/热更新/回滚
- 独立部署，横切四层架构（infra/core/platform/app）

### 2.2 架构边界（aiPlat-management/docs/architecture-boundary.md）
明确约束：
- management 作为 **统一 API 入口**，通过 **HTTP 调用**各层 API  
- **不应包含**业务逻辑实现、直接操作 Manager 类、数据库/存储操作

## 3. 代码实现核对（management）

### 3.1 API 入口与依赖方式：✅ 方向一致，但存在“重复实例/配置不生效”
- `management/api/infra.py`：通过 `InfraAPIClient` 转发到 `http://localhost:8001` ✅（符合文档）
- `management/api/core.py`：通过 `CoreAPIClient` 转发到 `http://localhost:8002` ✅
- **问题**：`management/server.py` 使用配置文件为 adapter 注入 endpoint，但 `management/api/dashboard.py` 自建 aggregator/adapters，绕开 `app.state.aggregator`，导致“配置写了但不生效”。

### 3.2 Dashboard 聚合：⚠️ 数据源与边界不一致
**设计期望**：adapter → HTTP 调用各层 API（状态、metrics、健康）  
**现实现状**：
- `dashboard/infra_adapter.py`：直接在 management 进程中做本机探测（system_info/service_detector），并不走 infra API。  
  - 这会导致 management 与 infra 的边界混淆：management“知道”了大量 infra 内部实现细节与探测逻辑。
- `dashboard/core_adapter.py` / `platform_adapter.py` / `app_adapter.py`：基本是静态数据（stub），不调用目标层 API。

### 3.3 Diagnostics：⚠️ 目前为 mock/占位实现
- `api/diagnostics.py` 调用 `management/diagnostics/*_health.py`
- `diagnostics/infra_health.py` 大量固定数值（例如连接池 10/100、hit_rate=0.95 等），并非真实探测/HTTP 调用。
- 文档里提到 tracing，但 API 返回 “Tracing not implemented yet”（占位）。

### 3.4 Alerting：⚠️ 内存态、无通知通道对接
- `alerting/rules.py` 的 AlertEngine 仅评估规则，不含规则持久化、去重、告警生命周期、通知发送、告警历史落库。
- `api/alerting.py` 的 active_alerts 也是内存 dict。

### 3.5 Config：⚠️ 内存态且未对接各层
- `config/manager.py`：ConfigManager/ConfigVersion 纯内存版本链；无落库、无对外推送到 infra/core/platform/app。

## 4. 代码实现核对（core）——与设计文档的一致性（摘要）

核心结论：**执行闭环（执行记录/trace/checkpoint/恢复语义/显式 tool/skill 路由）已经能形成可审计的最小生产链路**。  
但管理面要把这套能力“运维化/可观测化”，仍需 management 层完成真实对接与统一入口职责。

## 5. 风险与建议（按优先级）

### P0（阻断“management 可用性”的问题）
1) **统一单例来源**：所有 API 路由必须使用 `app.state` 注入的 aggregator/alert_engine/config_manager（或统一依赖注入容器），移除 `api/dashboard.py` / `api/alerting.py` 的重复实例。  
2) **数据源统一为 HTTP**：Dashboard/Diagnostics 的 Infra/Core/Platform/App Adapter 应优先调用各层 `/api/*` 的 status/metrics/health，而非 management 本机探测/固定 mock。

### P1（提升到“准生产”）
3) **配置/告警持久化**：至少引入 SQLite（或复用 infra 的存储）落库 ConfigVersion、AlertRule、AlertHistory；并提供回滚与审计字段（author/trace_id）。  
4) **认证鉴权策略**：management 作为统一入口，需要最小 authn/authz（token/role），或透传到下游并做审计；否则会成为“未授权超级网关”。  

### P2（体验与运维完善）
5) **Tracing/Observability 对接**：将 core 的 trace/run/checkpoint 查询能力在 management dashboard/diagnostics 中可视化（而不是 “not implemented yet”）。

## 6. 建议落地路线（最小闭环 → 可运营）
1) 先做 **management 的依赖注入/单例治理**（P0-1）  
2) 再做 **HTTP 适配器替换掉 mock/本机探测**（P0-2）  
3) 然后补 **config/alerting 的最小落库与审计字段**（P1-3）  
4) 最后接入 **统一鉴权与追踪可视化**（P1-4/P2-5）

