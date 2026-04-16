# AI Platform 基础设施层 - 测试快速开始指南（As-Is 对齐）

> 说明：本文档提供快速运行测试的 As-Is 命令集合；涉及 docker/compose/CI 的部分若不在本仓库，请视为 To-Be 或外部 ops 仓库内容。

> 5分钟快速上手测试

---

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
cd aiPlat-infra
pip install -e .[dev]

# 启动Docker（集成测试需要）
docker ps
```

### 2. 运行测试（按优先级）

#### ⚡ 最快：单元测试（0.1秒）

```bash
# 所有单元测试
pytest infra/tests/ -v -m "not integration"

# 单个模块
pytest infra/tests/test_database/test_client.py -v
pytest infra/tests/test_messaging/test_messaging.py -v

# 查看覆盖率
pytest infra/tests/ --cov=infra --cov-report=html
open htmlcov/index.html
```

#### 🐳 推荐：数据库集成测试（30秒）

```bash
# 一键运行所有数据库测试
python infra/tests/test_database/run_all_integration_tests.py

# 单个数据库
python infra/tests/test_database/test_postgres_integration.py
python infra/tests/test_database/test_mysql_integration.py
python infra/tests/test_database/test_mongodb_integration.py
```

#### 📨 Messaging测试（5-40秒）

```bash
# Redis Streams（快速，推荐）
python infra/tests/test_messaging/test_redis_streams_integration.py

# 所有Messaging测试
python infra/tests/test_messaging/run_all_messaging_tests.py
```

---

## 📊 测试状态一览表

| 模块 | 单元测试 | 集成测试 | Docker镜像 | 运行时间 | 推荐度 |
|------|---------|---------|-----------|---------|--------|
| **配置管理** | ✅ 9/9 | ❌ | 不需要 | 0.01s | ⭐⭐⭐⭐⭐ |
| **SQLite** | ✅ 9/9 | ✅ 内存DB | 不需要 | 0.05s | ⭐⭐⭐⭐⭐ |
| **PostgreSQL** | ✅ 4/4 | ✅ 真实容器 | postgres:15 | ~10s | ⭐⭐⭐⭐⭐ |
| **MySQL** | ✅ 3/3 | ✅ 真实容器 | mysql:8.0 | ~10s | ⭐⭐⭐⭐⭐ |
| **MongoDB** | ✅ 4/4 | ✅ 真实容器 | mongo:7.0 | ~15s | ⭐⭐⭐⭐ |
| **Redis Streams** | ✅ 17/17 | ✅ 真实容器 | redis:7 | ~5s | ⭐⭐⭐⭐⭐ |
| **RabbitMQ** | ✅ 17/17 | ✅ 框架就绪 | rabbitmq:3.12 | ~15s | ⭐⭐⭐ |
| **Kafka** | ✅ 17/17 | ✅ 框架就绪 | kafka:7.4 | ~40s | ⭐⭐⭐ |
| **Vector存储** | ✅ 24/24 | ❌ | 不需要 | 0.1s | ⭐⭐⭐⭐ |
| **LLM** | ✅ 3/3 | ❌ | 不需要 | 0.05s | ⭐⭐⭐ |

---

## 🎯 按需求选择测试

### 我是开发者（快速迭代）

```bash
# 只运行单元测试（快速反馈）
pytest infra/tests/ -v -m "not integration"

# 只测试修改的模块
pytest infra/tests/test_database/ -v -k "test_client"
```

### 我是CI/CD（自动化验证）

```bash
# 完整测试流程
pytest infra/tests/ -v -m "not integration"  # 单元测试
python infra/tests/test_database/run_all_integration_tests.py  # 集成测试
pytest --cov=infra --cov-report=xml  # 覆盖率报告
```

### 我是测试工程师（全面验证）

```bash
# 所有测试 + 覆盖率
pytest infra/tests/ -v --cov=infra --cov-report=html
python infra/tests/test_database/run_all_integration_tests.py
python infra/tests/test_messaging/run_all_messaging_tests.py
```

### 我是运维（生产部署前）

```bash
# 集成测试（验证环境）
python infra/tests/test_database/run_all_integration_tests.py
python infra/tests/test_messaging/test_redis_streams_integration.py

# 性能测试
pytest tests/performance/ -v -m performance
```

---

## 📦 测试命令大全

### 单元测试命令

```bash
# 运行所有单元测试
pytest infra/tests/ -v

# 运行特定模块
pytest infra/tests/test_database/ -v
pytest infra/tests/test_messaging/ -v

# 运行特定测试类
pytest infra/tests/test_database/test_client.py::TestPostgreSQL -v

# 运行特定测试方法
pytest infra/tests/test_database/test_client.py::TestPostgreSQL::test_connection -v

# 并行运行（需要pytest-xdist）
pytest infra/tests/ -v -n auto

# 只运行失败的测试
pytest infra/tests/ -v --lf

# 停止于第一个失败
pytest infra/tests/ -v -x
```

### 集成测试命令

```bash
# 数据库集成测试
python infra/tests/test_database/test_postgres_integration.py
python infra/tests/test_database/test_mysql_integration.py
python infra/tests/test_database/test_mongodb_integration.py

# Messaging集成测试
python infra/tests/test_messaging/test_redis_streams_integration.py
python infra/tests/test_messaging/test_rabbitmq_integration.py  # 需要镜像
python infra/tests/test_messaging/test_kafka_integration.py     # 需要镜像

# 一键运行
python infra/tests/test_database/run_all_integration_tests.py
python infra/tests/test_messaging/run_all_messaging_tests.py
```

### 覆盖率命令

```bash
# HTML报告
pytest infra/tests/ --cov=infra --cov-report=html

# 终端报告
pytest infra/tests/ --cov=infra --cov-report=term

# XML报告（用于CI）
pytest infra/tests/ --cov=infra --cov-report=xml

# 特定模块覆盖率
pytest infra/tests/test_database/ --cov=infra.database --cov-report=term
```

### 标记测试

```bash
# 只运行单元测试
pytest infra/tests/ -v -m "not integration"

# 只运行集成测试
pytest infra/tests/ -v -m integration

# 只运行性能测试
pytest tests/performance/ -v -m performance

# 只运行安全测试
pytest tests/security/ -v -m security

# 运行特定标记
pytest infra/tests/ -v -m "database and not integration"
```

---

## 🐛 故障排查速查表

### 问题1: 找不到模块

```
ModuleNotFoundError: No module named 'infra'
```

**解决方案:**
```bash
cd /Users/apple/workdata/person/zy/aiPlatform/aiPlat-infra
pip install -e .
```

### 问题2: Docker未运行

```
Error: Cannot connect to Docker daemon
```

**解决方案:**
```bash
# macOS
open -a Docker

# Linux
sudo systemctl start docker

# 验证
docker ps
```

### 问题3: 端口被占用

```
OSError: [Errno 48] Address already in use
```

**解决方案:**
```bash
# 查看占用端口的进程
lsof -i :5432

# 杀掉进程
kill -9 <PID>

# 或使用Testcontainers自动分配端口
```

### 问题4: 测试超时

```
TimeoutError: Test timed out after 60s
```

**解决方案:**
```bash
# 增加超时时间
pytest infra/tests/ -v --timeout=120

# 或在pytest.ini中配置
[pytest]
timeout = 120
```

### 问题5: 权限错误

```
PermissionError: [Errno 13] Permission denied
```

**解决方案:**
```bash
# 检查文件权限
ls -la

# 修改权限
chmod +x script.sh

# 或使用sudo
sudo pytest infra/tests/ -v
```

---

## 📈 性能基准

### 单元测试性能

| 模块 | 测试数量 | 执行时间 | 平均耗时 |
|------|---------|---------|---------|
| Config | 9 | 0.02s | 0.002s |
| Database | 29 | 0.05s | 0.002s |
| Messaging | 17 | 0.05s | 0.003s |
| Vector | 24 | 0.05s | 0.002s |
| Utils | 6 | 0.01s | 0.002s |

### 集成测试性能

| 测试 | Docker镜像 | 启动时间 | 执行时间 | 总时间 |
|------|-----------|---------|---------|--------|
| PostgreSQL | 100MB | 2s | 5s | 7s |
| MySQL | 150MB | 3s | 5s | 8s |
| MongoDB | 700MB | 5s | 5s | 10s |
| Redis | 30MB | 1s | 3s | 4s |
| RabbitMQ | 200MB | 3s | 5s | 8s |
| Kafka | 1GB | 10s | 10s | 20s |

---

## 🎯 测试目标

### 单元测试目标

- ✅ **代码覆盖率**: > 80%
- ✅ **执行时间**: < 1秒
- ✅ **并行执行**: 支持
- ✅ **失败重试**: 支持

### 集成测试目标

- ✅ **容器隔离**: 每个测试独立容器
- ✅ **数据隔离**: 每个测试独立数据库
- ✅ **执行时间**: < 30秒/容器
- ✅ **并行执行**: 支持

### E2E测试目标

- ✅ **场景覆盖**: 核心业务流程
- ✅ **执行时间**: < 5分钟
- ✅ **环境隔离**: 独立测试环境
- ✅ **报告生成**: 自动生成

---

## 📚 相关文档

### 快速导航

- 🏃 **快速开始**: 本文档
- 📖 **详细指南**: [SYSTEM_TESTING_GUIDE.md](./SYSTEM_TESTING_GUIDE.md)
- ✅ **最佳实践**: [TESTING_GUIDE.md](./TESTING_GUIDE.md)
- 📋 **检查清单**: [TESTING_CHECKLIST.md](./TESTING_CHECKLIST.md)
- 📊 **集成测试报告**: [INTEGRATION_TEST_REPORT.md](../infra/tests/test_database/INTEGRATION_TEST_REPORT.md)
- 🎉 **完成总结**: [TESTCONTAINERS_FINAL_REPORT.md](../TESTCONTAINERS_FINAL_REPORT.md)

### 文档结构

```
aiPlat-infra/
├── docs/
│   ├── TESTING_QUICKSTART.md      ← 本文档（快速开始）
│   ├── SYSTEM_TESTING_GUIDE.md    ← 系统测试指南（详细）
│   ├── TESTING_GUIDE.md           ← 测试最佳实践
│   └── TESTING_CHECKLIST.md       ← 测试检查清单
│
├── infra/tests/
│   ├── test_database/
│   │   ├── test_client.py          ← 单元测试
│   │   ├── test_postgres_integration.py ← 集成测试
│   │   └── INTEGRATION_TEST_REPORT.md ← 测试报告
│   │
│   ├── test_messaging/
│   │   ├── test_messaging.py        ← 单元测试
│   │   └── test_redis_integration.py ← 集成测试
│   │
│   └── TESTING_GUIDE.md            ← 测试指南
│
└── TESTCONTAINERS_FINAL_REPORT.md  ← 最终总结
```

---

## 💡 提示和技巧

### 提速技巧

```bash
# 并行运行测试
pytest infra/tests/ -v -n auto

# 只运行修改的测试
pytest infra/tests/ -v --lf

# 跳过慢速测试
pytest infra/tests/ -v -m "not slow"

# 使用pytest缓存
pytest infra/tests/ -v --cache-show
```

### 调试技巧

```bash
# 详细输出
pytest infra/tests/ -v -s

# 显示打印语句
pytest infra/tests/ -v --capture=no

# 失败时进入调试器
pytest infra/tests/ -v --pdb

# 显示局部变量
pytest infra/tests/ -v --showlocals
```

### 持续集成技巧

```bash
# JUnit XML报告（用于CI）
pytest infra/tests/ -v --junitxml=report.xml

# 代码覆盖率XML
pytest infra/tests/ --cov=infra --cov-report=xml

# 并行测试（CI推荐）
pytest infra/tests/ -v -n auto --dist=loadscope
```

---

## 🎉 成功标志

### 测试通过标志

```bash
# 单元测试
==================== 46 passed in 0.48s ====================
✅ 成功!

# 集成测试
======================================================================
✅ PostgreSQL      PASSED
✅ MySQL           PASSED
✅ MongoDB         PASSED
======================================================================
✅ 所有测试通过！

# 覆盖率
TOTAL     1250    150   85%
✅ 目标达成：>80%
```

---

## 🆘 获取帮助

### 文档资源

1. **测试文档**: `docs/TESTING_GUIDE.md`
2. **系统测试指南**: `docs/SYSTEM_TESTING_GUIDE.md`
3. **检查清单**: `docs/TESTING_CHECKLIST.md`
4. **集成测试报告**: `infra/tests/test_database/INTEGRATION_TEST_REPORT.md`

### 常见问题

- 查看故障排查章节: `docs/SYSTEM_TESTING_GUIDE.md#故障排查`
- 查看最佳实践: `docs/TESTING_GUIDE.md`
- 查看示例代码: `infra/tests/test_database/test_*.py`

---

**开始测试吧！🚀**

```bash
# 1分钟快速验证
pytest infra/tests/ -v -m "not integration"

# 5分钟完整验证
python infra/tests/test_database/run_all_integration_tests.py

# 查看结果
🎉 所有测试通过！
```

---

*最后更新: 2026-04-11  

---

## 证据索引（Evidence Index｜抽样）

- infra tests：`infra/tests/*`
**文档版本**: v1.0
