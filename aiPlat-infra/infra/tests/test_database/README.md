# 数据库集成测试

本目录包含数据库模块的真实功能测试，使用Testcontainers在Docker容器中启动真实数据库。

## 测试类型

### 单元测试 (test_client.py)
- 不需要Docker
- 使用Mock或内存数据库
- 快速执行
- 运行命令：
```bash
pytest infra/tests/test_database/test_client.py -v
```

### 集成测试 (test_integration.py)
- **需要Docker Desktop运行**
- 使用Testcontainers启动真实数据库容器
- 测试真实的数据库操作
- 运行命令：
```bash
# 确保Docker正在运行
docker ps

# 运行集成测试
pytest infra/tests/test_database/test_integration.py -v -s
```

## 支持的数据库

集成测试覆盖以下数据库：

1. **PostgreSQL** (postgres:15-alpine)
   - 连接测试
   - 表创建和CRUD操作
   - 事务提交
   - 事务回滚

2. **MySQL** (mysql:8.0)
   - 连接测试
   - 表创建和CRUD操作

3. **MongoDB** (mongo:7.0)
   - 连接测试
   - 文档插入和查询
   - 文档更新和删除

## 前置要求

### 安装依赖
```bash
pip install testcontainers docker
```

### 启动Docker Desktop
确保Docker Desktop正在运行：
``` bash
# macOS/Linux
docker ps

# 如果没有运行，启动Docker Desktop
# 然后验证
docker ps
```

## 运行测试

### 运行所有数据库测试（包括集成测试）
```bash
# 运行所有测试
pytest infra/tests/test_database/ -v

# 只运行单元测试（不需要Docker）
pytest infra/tests/test_database/ -v -m "not integration"

# 只运行集成测试（需要Docker）
pytest infra/tests/test_database/ -v -m integration

# 运行特定数据库的集成测试
pytest infra/tests/test_database/test_integration.py::TestPostgreSQLIntegration -v
pytest infra/tests/test_database/test_integration.py::TestMySQLIntegration -v
pytest infra/tests/test_database/test_integration.py::TestMongoDBIntegration -v
```

### CI/CD 集成

在CI/CD环境中，确保Docker可用：

```yaml
# GitHub Actions 示例
- name: Run Integration Tests
  run: pytest infra/tests/test_database/test_integration.py -v -m integration
  
- name: Run Unit Tests
  run: pytest infra/tests/test_database/test_client.py -v
```

## 性能考虑

集成测试比单元测试慢，因为需要：
1. 启动Docker容器（首次需要下载镜像）
2. 初始化数据库
3. 运行真实SQL操作
4. 清理容器

建议：
- 开发时运行单元测试（快速反馈）
- CI/CD中运行完整测试套件
- 提交代码前运行集成测试

## 故障排除

### Docker未运行错误
```
Error: Cannot connect to the Docker daemon
```
**解决方案**: 启动Docker Desktop

### 容器启动超时
```
Error: Container did not start within timeout
```
**解决方案**: 
1. 检查网络连接
2. 增加超时时间：`export TESTCONTAINERS_TIMEOUT=120`
3. 清理旧容器：`docker container prune`

### 端口冲突
```
Error: Port 5432 already in use
```
**解决方案**: 
1. 停止本地数据库服务
2. 或者使用随机端口（Testcontainers会自动处理）

## 测试标记

- `@pytest.mark.integration` - 集成测试标记
- `@pytest.mark.slow` - 慢速测试标记

使用这些标记可以灵活控制测试执行：
```bash
# 跳过集成测试
pytest -m "not integration"

# 只运行集成测试
pytest -m integration

# 跳过慢速测试
pytest -m "not slow"
```

## 贡献新测试

添加新的集成测试时，请遵循：

1. 使用现有的fixture（postgres_container, mysql_container等）
2. 标记为`@pytest.mark.integration`
3. 包含清理逻辑（虽然Testcontainers会自动清理）
4. 测试真实的业务场景，而不仅仅是连接

示例：
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_complex_query(self, postgres_container):
    """测试复杂的PostgreSQL查询"""
    from infra.database.postgres import PostgresClient
    from infra.database.schemas import DatabaseConfig
    import urllib.parse
    
    parsed = urllib.parse.urlparse(postgres_container)
    config = DatabaseConfig(
        type="postgres",
        host=parsed.hostname,
        port=parsed.port,
        user=parsed.username,
        password=parsed.password,
        name=parsed.path.lstrip('/')
    )
    
    client = PostgresClient(config)
    await client.connect()
    
    # 你的测试逻辑
    # ...
    
    await client.close()
```

## 参考文档

- [Testcontainers官方文档](https://testcontainers.com/)
- [pytest-asyncio文档](https://pytest-asyncio.readthedocs.io/)
- [PostgreSQL容器](https://hub.docker.com/_/postgres)
- [MySQL容器](https://hub.docker.com/_/mysql)
- [MongoDB容器](https://hub.docker.com/_/mongo)