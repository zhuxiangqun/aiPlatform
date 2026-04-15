# aiPlat-infra - AI Platform 基础设施层

> Layer 0 - 基础设施层，管理和抽象所有基础设施资源

---

## 📖 简介

`aiPlat-infra`是AI Platform的基础设施层（Layer 0），提供数据库、消息队列、向量存储、LLM服务等基础设施的统一抽象接口。

**核心职责**：
- 提供统一的数据库访问接口（PostgreSQL/MySQL/MongoDB/SQLite）
- 提供统一的消息队列接口（Kafka/RabbitMQ/Redis Streams）
- 提供统一的向量存储接口（Milvus/FAISS/ChromaDB/Pinecone）
- 提供LLM服务接口（OpenAI/Anthropic/本地模型）
- 提供配置管理、依赖注入等基础能力

**依赖方向**：
```
aiPlat-infra (Layer 0) ← aiPlat-core (Layer 1) ← aiPlat-platform (Layer 2) ← aiPlat-app (Layer 3)
```

---

## 🚀 快速开始

### 安装

```bash
cd aiPlat-infra
pip install -e .[dev]
```

### 运行测试

```bash
# 单元测试（快速）
pytest infra/tests/ -v -m "not integration"

# 数据库集成测试
python infra/tests/test_database/run_all_integration_tests.py

# Messaging集成测试
python infra/tests/test_messaging/run_all_messaging_tests.py
```

---

## 📚 文档导航

### 核心文档

| 文档 | 说明 |
|------|------|
| [完整文档索引](docs/index.md) | 所有模块文档的索引 |
| [架构设计](docs/index.md#🏗️-基础设施层架构) | 架构设计和技术选型 |

### 测试文档

| 文档 | 说明 |
|------|------|
| [测试快速开始](docs/testing/TESTING_QUICKSTART.md) | 5分钟上手测试 👈 |
| [系统测试指南](docs/testing/SYSTEM_TESTING_GUIDE.md) | 完整测试策略 |
| [测试最佳实践](docs/testing/TESTING_GUIDE.md) | 如何写好测试 |
| [测试检查清单](docs/testing/TESTING_CHECKLIST.md) | 质量检查 |

### 测试报告

| 报告 | 内容 |
|------|------|
| [数据库集成测试](docs/testing/reports/DATABASE_INTEGRATION_REPORT.md) | PostgreSQL/MySQL/MongoDB测试 |
| [消息集成测试](docs/testing/reports/MESSAGING_INTEGRATION_REPORT.md) | Redis Streams测试 |
| [Testcontainers总结](docs/testing/reports/TESTCONTAINERS_FINAL_REPORT.md) | 实施总结 |

---

## 🏗️ 模块结构

```
aiPlat-infra/
├── infra/
│   ├── database/          # 数据库模块（PostgreSQL/MySQL/MongoDB/SQLite）
│   ├── messaging/          # 消息队列（Kafka/RabbitMQ/Redis）
│   ├── vector/             # 向量存储（Milvus/FAISS/ChromaDB/Pinecone）
│   ├── llm/                # 大语言模型（OpenAI/Anthropic/Local）
│   ├── storage/            # 对象存储（Local/S3/MinIO）
│   ├── config/             # 配置管理
│   ├── di/                 # 依赖注入
│   ├── utils/              # 工具函数
│   └── tests/              # 测试代码
│       ├── test_database/  # 数据库测试
│       ├── test_messaging/ # 消息队列测试
│       └── ...
│
├── docs/                   # 文档
│   ├── testing/            # 测试文档
│   ├── database/           # 数据库文档
│   └── messaging/          # 消息队列文档
│
└── README.md               # 本文档
```

---

## 📊 测试状态

### 单元测试

| 模块 | 测试数量 | 状态 |
|------|---------|------|
| Database | 29/29 | ✅ 通过 |
| Messaging | 17/17 | ✅ 通过 |
| Vector | 24/24 | ✅ 通过 |
| Config | 9/9 | ✅ 通过 |
| 其他 | 23/23 | ✅ 通过 |

### 集成测试

| 模块 | 测试内容 | 状态 |
|------|---------|------|
| PostgreSQL | CRUD + 事务 | ✅ 通过 |
| MySQL | CRUD + 查询 | ✅ 通过 |
| MongoDB | 文档操作 | ✅ 通过 |
| Redis Streams | 发布/订阅 | ✅ 通过 |

---

## 🎯 按角色查看文档

### 开发者

- [测试快速开始](docs/testing/TESTING_QUICKSTART.md) - 快速上手
- [测试最佳实践](docs/testing/TESTING_GUIDE.md) - 编写好测试
- [数据库使用](docs/database/index.md) - 数据库使用指南
- [消息队列使用](docs/messaging/index.md) - 消息队列使用指南

### 架构师

- [架构设计](docs/index.md#🏗️-基础设施层架构) - 架构概览
- [系统测试指南](docs/testing/SYSTEM_TESTING_GUIDE.md) - 完整测试策略

### 测试工程师

- [系统测试指南](docs/testing/SYSTEM_TESTING_GUIDE.md) - 完整测试体系
- [测试报告](docs/testing/reports/) - 测试结果和覆盖率

### 运维

- [部署指南](docs/by-role/ops/index.md) - 部署和配置
- [监控配置](docs/monitoring/index.md) - 监控和告警

---

##🚀 快速命令

### 开发

```bash
# 安装依赖
pip install -e .[dev]

# 运行单元测试
pytest infra/tests/ -v -m "not integration"

# 运行所有测试
pytest infra/tests/ -v

# 查看覆盖率
pytest infra/tests/ --cov=infra --cov-report=html
```

### 集成测试

```bash
# 数据库测试（需要Docker）
python infra/tests/test_database/run_all_integration_tests.py

# Messaging测试
python infra/tests/test_messaging/run_all_messaging_tests.py

# 单个测试
python infra/tests/test_database/test_postgres_integration.py
python infra/tests/test_messaging/test_redis_streams_integration.py
```

---

## 📈 项目进度

- ✅ 数据库模块（PostgreSQL/MySQL/MongoDB/SQLite）
- ✅ 消息队列模块（Kafka/RabbitMQ/Redis Streams）
- ✅ 向量存储模块（Milvus/FAISS/ChromaDB/Pinecone）
- ✅ 配置管理模块
- ✅ 依赖注入模块
- ✅ 完整测试体系

---

## 🤝 贡献

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建Pull Request

---

## 📞 支持

- **文档**: [docs/index.md](docs/index.md)
- **测试**: [docs/testing/](docs/testing/)
- **问题**: 提交GitHub Issue

---

*最后更新: 2026-04-13*
**版本**: v1.0  
**维护团队**: AI Platform Team