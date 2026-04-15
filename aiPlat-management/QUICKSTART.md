# aiPlat-management 快速启动指南

## 系统要求

- Python 3.10+
- pip

## 安装

```bash
cd aiPlat-management
pip install -e .[dev]
```

## 服务管理

### 启动服务

```bash
./start.sh
```

### 停止服务

```bash
./stop.sh
```

### 重启服务

```bash
./restart.sh
```

### 手动运行

```bash
# 方式一：使用 Python 模块
python -m management.server

# 方式二：使用 uvicorn（开发模式，带热重载）
uvicorn management.server:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

## 访问服务

服务启动后，可以访问：

| 端点 | 说明 |
|------|------|
| http://localhost:8000 | 首页（Web界面） |
| http://localhost:8000/health | 健康检查 |
| http://localhost:8000/docs | API 文档 (Swagger UI) |
| http://localhost:8000/redoc | API 文档 (ReDoc) |

## 首页功能

首页提供：
- 系统总览（四层架构状态）
- 各层健康状态
- API 端点导航
- 自动刷新（30秒）

## API 端点

### Dashboard API

```bash
# 获取各层状态
curl http://localhost:8000/api/dashboard/status

# 健康检查
curl http://localhost:8000/api/dashboard/health

# 获取指标
curl http://localhost:8000/api/dashboard/metrics
```

### Monitoring API

```bash
# 获取 infra 层指标
curl http://localhost:8000/api/monitoring/metrics/infra

# 获取所有层指标
curl http://localhost:8000/api/monitoring/metrics/all

# 列出可用层级
curl http://localhost:8000/api/monitoring/metrics
```

### Diagnostics API

```bash
# 获取 infra 层健康状态
curl http://localhost:8000/api/diagnostics/health/infra

# 获取所有层健康状态
curl http://localhost:8000/api/diagnostics/health/all

# 获取系统概览
curl http://localhost:8000/api/diagnostics/system

# 运行诊断
curl -X POST http://localhost:8000/api/diagnostics/check/infra
```

### Alerting API

```bash
# 获取告警列表
curl http://localhost:8000/api/alerting/alerts

# 获取告警规则
curl http://localhost:8000/api/alerting/rules

# 创建告警规则
curl -X POST http://localhost:8000/api/alerting/rules \
  -H "Content-Type: application/json" \
  -d '{"name":"high_cpu","layer":"infra","metric":"cpu_usage","condition":">","threshold":80,"duration":300,"severity":"warning"}'
```

## 配置

配置文件位于 `config/management.yaml`，可以修改：

```yaml
management:
  layers:
    infra:
      endpoint: "http://localhost:8001"
      enabled: true
      timeout: 30
    # ... 其他层级

server:
  host: "0.0.0.0"
  port: 8000
```

## 测试

运行测试：

```bash
cd aiPlat-management
pytest tests/ -v
```

## 目录结构

```
aiPlat-management/
├── management/
│   ├── dashboard/          # Dashboard 模块
│   │   ├── aggregator.py
│   │   ├── infra_adapter.py
│   │   └── ...
│   ├── monitoring/          # Monitoring 模块
│   │   ├── collector.py
│   │   ├── infra_collector.py
│   │   └── ...
│   ├── diagnostics/        # Diagnostics 模块
│   │   ├── health.py
│   │   ├── infra_health.py
│   │   └── ...
│   ├── alerting/           # Alerting 模块
│   │   ├── rules.py
│   │   ├── notifier.py
│   │   └── ...
│   ├── config/             # Config 模块
│   │   └── manager.py
│   ├── api/                # API 端点
│   │   ├── dashboard.py
│   │   ├── monitoring.py
│   │   ├── alerting.py
│   │   └── diagnostics.py
│   ├── main.py             # 主入口
│   └── server.py           # FastAPI 服务器
├── tests/                  # 测试文件
│   ├── test_infra_adapter.py
│   ├── test_infra_collector.py
│   └── test_infra_health.py
├── config/                 # 配置文件
│   └── management.yaml
├── docs/                   # 文档
├── pyproject.toml          # 项目配置
└── start.sh               # 启动脚本
```

## 下一步

查看完整文档：

- [主文档](docs/index.md) - Management 系统总览
- [Dashboard](docs/dashboard/index.md) - Dashboard 模块
- [Monitoring](docs/monitoring/index.md) - Monitoring 模块
- [Alerting](docs/alerting/index.md) - Alerting 模块
- [Diagnostics](docs/diagnostics/index.md) - Diagnostics 模块