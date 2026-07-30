# 常见异常模式库

## Java/Python 后端

| 异常类型 | 匹配模式 | 常见根因 | 典型回归范围 |
|------|------|------|------|
| NullPointerException | `NullPointerException` / `NoneType` | 未做空值校验、数据异常 | 接口层 + Service层 |
| ConnectionRefused | `Connection refused` / `ECONNREFUSED` | 下游服务不可用、端口错误 | 调用方 + 被调用方 |
| TimeoutException | `Timeout` / `timed out` / `504` | 慢查询、死锁、资源耗尽 | SQL + 缓存 + 超时配置 |
| OutOfMemoryError | `OutOfMemory` / `OOM` | 内存泄漏、大对象、缓存无限增长 | 缓存模块 + 数据查询 |
| DuplicateKeyException | `Duplicate entry` / `duplicate key` | 幂等性缺失、并发写入 | 写入接口 + 幂等逻辑 |
| ClassCastException | `ClassCastException` / `cannot be cast` | 类型不匹配、序列化错误 | 序列化模块 + 类型定义 |
| HttpMessageNotReadable | `HttpMessageNotReadable` / `400` | 请求体格式错误 | 接口参数校验 |
| IllegalStateException | `IllegalState` | 状态机非法转换 | 状态管理模块 |
| SocketTimeoutException | `SocketTimeout` / `Read timed out` | 下游响应慢、网络抖动 | RPC调用 + 超时配置 |

## 前端/浏览器

| 异常类型 | 匹配模式 | 常见根因 | 典型回归范围 |
|------|------|------|------|
| TypeError | `TypeError: undefined is not` | 数据未加载完就渲染 | 数据加载 + 组件渲染 |
| ReferenceError | `ReferenceError: X is not defined` | 变量未声明、模块未导入 | 组件 + import |
| NetworkError | `NetworkError` / `Failed to fetch` | API不可达、CORS | API配置 + 跨域 |
| CORS Error | `has been blocked by CORS` | 跨域配置缺失 | 网关 + API配置 |
| Rendering Error | `Error: Minified React error` | 组件异常、状态非法 | 出错组件 + 父组件 |
| SyntaxError | `SyntaxError: Unexpected token` | JSON解析失败、Babel错误 | 数据格式 + 构建配置 |

## 数据库

| 异常类型 | 匹配模式 | 常见根因 | 典型回归范围 |
|------|------|------|------|
| Deadlock | `Deadlock found` / `Lock wait timeout` | 并发事务冲突 | 事务逻辑 + 索引 |
| Disk Full | `No space left` / `disk full` | 磁盘空间不足 | 运维 + 清理策略 |
| Connection Pool Exhausted | `Too many connections` / `HikariPool` | 连接泄漏 | 连接池配置 + DAO |

## 推断规则

| 组合特征 | 推断根因 |
|------|------|
| 发布后 + 新异常类型 | 新代码引入的 Bug（回归范围：本次变更清单） |
| 无发布 + 异常频次陡增 | 外部依赖故障或流量突增（回归范围：受影响模块） |
| 异常A→异常B→异常C 持续出现 | A 是根本原因，B/C 是连锁反应 |
| 仅在特定时间出现 | 定时任务、流量高峰、第三方服务限时 |
