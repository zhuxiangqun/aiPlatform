# aiPlat-management - AI Platform 管理系统

> 独立的运维管理系统 - 横切四层架构的统一管理平面

---

## 0. 文档说明（设计正确 vs 实现现状）

本 README 的“模块能力描述”用于表达 **management 的目标设计（To‑Be）**。  
当前仓库实现可能仍处于原型阶段，已实现与未实现项请以：

- `docs/IMPLEMENTATION_STATUS.md`

为准。

## 📖 概述

aiPlat-management 是 AI Platform 的**独立管理系统**，横切四层业务架构，提供：

- **Dashboard（总览）**：四层健康状态总览、拓扑可视化与关键指标聚合
- **Monitoring（监控）**：指标采集、时序存储、监控图表、性能分析
- **Alerting（告警）**：告警规则、多渠道通知、告警历史与处理闭环
- **Diagnostics（诊断）**：健康检查、链路追踪、日志聚合与问题诊断
- **Config（配置）**：配置管理、版本控制、发布、回滚与审计

---

## 🏗️ 架构定位

### 与业务系统的关系

| 系统 | 角色 | 职责 |
|------|------|------|
| **infra** | 业务层 Layer 0 | 基础设施服务 |
| **core** | 业务层 Layer 1 | AI 核心能力 |
| **platform** | 业务层 Layer 2 | 平台服务 |
| **app** | 业务层 Layer 3 | 用户应用 |
| **management** | **管理系统** | **运维管理** |

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│              aiPlat-management (Management System)          │
│          管理平面 - 监控、诊断、配置、告警                      │
└────────────┬─────────────────────────────────────────────────┘
             │ 管理接口
             ║
    ┌────────╨─────────┬─────────┬─────────┬────────────┐
    │                  │         │         │            │
    ▼                  ▼         ▼         ▼            ▼
┌────────┐       ┌────────┐ ┌────────┐ ┌────────┐
│ Layer 3│       │ Layer 2│ │ Layer 1│ │ Layer 0│
│  app   │       │platform│ │  core  │ │ infra  │
└────────┘       └────────┘ └────────┘ └────────┘
 管理 API         管理 API    管理 API   管理 API
```

**关键特点**：
- ✅ 独立于业务系统，可独立部署和扩展
- ✅ 业务层崩溃时，management 仍可诊断其他层
- ✅ 运维团队可独立开发管理功能
- ✅ 符合管理平面 vs 业务平面架构

---

## 🔒 Core（Layer 1）管理：Engine vs Workspace

为了让“核心能力层稳定可控”与“对外能力可定制可管理”同时成立，management 在 Core（Layer 1）上将目录化资源分成两套 scope：

| scope | 说明 | 前端入口 | API（management 转发） | 默认目录 |
|------|------|----------|------------------------|----------|
| **engine** | 核心能力层内部使用（内置、不可覆盖） | 侧边栏「核心能力层」 | `/api/core/skills`、`/api/core/agents`、`/api/core/mcp/servers` | `aiPlat-core/core/engine/{skills,agents,mcps}` |
| **workspace** | 对外应用库（可编辑可删除） | 侧边栏「应用库」 | `/api/core/workspace/*` | `~/.aiplat/{skills,agents,mcps}` |

说明：
- **执行流程始终由 core 引擎控制**（Harness/Runtime）；scope 仅影响“内容来源/权限边界/管理入口”。
- **禁止覆盖**：workspace 不允许创建与 engine 同名（同 id）的资源。

---

## 🚀 快速开始

### 安装

```bash
cd aiPlat-management
pip install -e .[dev]
```

### 配置

编辑 `config/management.yaml`：

```yaml
management:
  # 各层管理接口地址
  layers:
    infra:
      endpoint: "http://localhost:8001"
    core:
      endpoint: "http://localhost:8002"
    platform:
      endpoint: "http://localhost:8003"
    app:
      endpoint: "http://localhost:8004"
  
  # 监控配置
  monitoring:
    interval: 60  # 采集间隔（秒）
    storage: "influxdb"  # 目标态：InfluxDB/Prometheus 等时序后端（As-Is 可能未接入）
  
  # 告警配置
  alerting:
    rules_file: "config/alert_rules.yaml"
    notifiers:
      - type: "email"
        config:
          smtp_host: "smtp.example.com"
```

### 运行

```bash
# 启动管理服务
python -m management.server

# 访问 Dashboard
open http://localhost:8000/management
```

### 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行带覆盖率的测试
pytest tests/ --cov=management --cov-report=html
```

---

## 📦 核心模块

### Dashboard（总览）

负责聚合各层状态，提供统一视图。

**代码模块**：
- `management/dashboard/aggregator.py` - 聚合器
- `management/dashboard/infra_adapter.py` - Layer 0 适配器
- `management/dashboard/core_adapter.py` - Layer 1 适配器
- `management/dashboard/platform_adapter.py` - Layer 2 适配器
- `management/dashboard/app_adapter.py` - Layer 3 适配器

**示例代码**：

```python
from management.dashboard import DashboardAggregator, InfraAdapter, CoreAdapter

# 创建聚合器
aggregator = DashboardAggregator()
aggregator.register_adapter("infra", InfraAdapter())
aggregator.register_adapter("core", CoreAdapter())

# 聚合状态
status = await aggregator.aggregate()
print(status["overall_status"])  # "healthy", "degraded", "unhealthy"
```

### Monitoring（监控）

负责采集各层监控指标（目标态：采集 → 时序存储 → 查询/图表闭环）。

**代码模块**：
- `management/monitoring/collector.py` - 采集器基类
- `management/monitoring/infra_collector.py` - Layer 0 采集
- `management/monitoring/core_collector.py` - Layer 1 采集
- `management/monitoring/platform_collector.py` - Layer 2 采集
- `management/monitoring/app_collector.py` - Layer 3 采集

**示例代码**：

```python
from management.monitoring import InfraMetricsCollector

# 创建采集器
collector = InfraMetricsCollector()

# 采集指标
metrics = await collector.collect()
for metric in metrics:
    print(f"{metric.name}: {metric.value} {metric.unit}")
```

### Alerting（告警）

负责告警规则管理和通知（目标态：规则持久化、告警历史、通知通道、去重/抑制策略）。

**代码模块**：
- `management/alerting/rules.py` - 告警规则引擎
- `management/alerting/notifier.py` - 通知器

**示例代码**：

```python
from management.alerting import AlertRule, AlertEngine

# 创建告警引擎
engine = AlertEngine()

# 添加告警规则
engine.add_rule(AlertRule(
    name="high_cpu_usage",
    layer="infra",
    metric="cpu_usage",
    condition=">",
    threshold=80.0,
    duration=300,
    severity="warning"
))

# 评估告警
alerts = await engine.evaluate(metrics)
```

### Diagnostics（诊断）

负责健康检查和故障诊断（目标态：诊断逻辑在各层；management 聚合与标准化输出，并提供 trace/logs 入口）。

**代码模块**：
- `management/diagnostics/health.py` - 健康检查基类
- `management/diagnostics/infra_health.py` - Layer 0 检查
- `management/diagnostics/core_health.py` - Layer 1 检查
- `management/diagnostics/platform_health.py` - Layer 2 检查
- `management/diagnostics/app_health.py` - Layer 3 检查

**示例代码**：

```python
from management.diagnostics import InfraHealthChecker

# 创建健康检查器
checker = InfraHealthChecker()

# 执行健康检查
health = await checker.get_health()
print(f"Status: {health['status']}")
```

### Config（配置）

负责配置管理和版本控制。

**代码模块**：
- `management/config/manager.py` - 配置管理器

**示例代码**：

```python
from management.config import ConfigManager

# 创建配置管理器
manager = ConfigManager()

# 获取配置
config = await manager.get_config("infra")

# 更新配置
version = await manager.update_config(
    "infra",
    {"database": {"max_connections": 200}},
    author="admin"
)

# 回滚配置
await manager.rollback("infra", "v1")
```

---

## 📚 文档

### 各层管理文档

- [infra 管理文档](docs/infra/index.md) - Layer 0 管理
- [core 管理文档](docs/core/index.md) - Layer 1 管理
- [platform 管理文档](docs/platform/index.md) - Layer 2 管理
- [app 管理文档](docs/app/index.md) - Layer 3 管理

### 业务系统文档

- [aiPlat-infra 文档](../aiPlat-infra/docs/index.md) - Layer 0 文档
- [aiPlat-core 文档](../aiPlat-core/docs/index.md) - Layer 1 文档
- [aiPlat-platform 文档](../aiPlat-platform/docs/index.md) - Layer 2 文档
- [aiPlat-app 文档](../aiPlat-app/docs/index.md) - Layer 3 文档

---

## 🛠️ 开发

### 代码结构

```
aiPlat-management/
├── management/           # 核心代码
│   ├── dashboard/       # Dashboard 模块
│   ├── monitoring/      # Monitoring 模块
│   ├── alerting/        # Alerting 模块
│   ├── diagnostics/     # Diagnostics 模块
│   ├── config/          # Config 模块
│   └── api/             # 管理 API
├── docs/                # 文档
│   ├── infra/           # Layer 0 管理文档
│   ├── core/            # Layer 1 管理文档
│   ├── platform/        # Layer 2 管理文档
│   └── app/             # Layer 3 管理文档
├── tests/               # 测试
├── config/              # 配置
├── pyproject.toml       # Python 项目配置
└── README.md            # 本文档
```

### 代码规范

- 使用 Python 3.10+ 特性
- 遵循 PEP 8 规范
- 使用 type hints
- 编写单元测试

### 提交代码

```bash
# 安装开发依赖
pip install -e .[dev]

# 运行格式化
black management/

# 运行 lint
ruff management/

# 运行测试
pytest tests/
```

---

## 📊 API 端点

### Dashboard API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/dashboard/status` | GET | 获取各层状态 |
| `GET /api/dashboard/health` | GET | 获取健康检查 |
| `GET /api/dashboard/metrics` | GET | 获取所有指标 |

### Monitoring API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/monitoring/metrics/{layer}` | GET | 获取指定层指标 |

### Alerting API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/alerting/alerts` | GET | 获取告警列表 |
| `POST /api/alerting/rules` | POST | 创建告警规则 |

### Diagnostics API

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /api/diagnostics/health/{layer}` | GET | 检查层级健康 |
| `GET /api/diagnostics/trace/{layer}` | GET | 获取链路追踪 |

---

## 🤝 贡献

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📝 许可证

MIT License

---

## 👥 维护者

AI Platform Team

---

*最后更新:2026-04-11  
**版本**：v1.0
