## Jobs / Cron（Roadmap-3）

### 开关与参数
- `AIPLAT_ENABLE_JOBS=true|false`：是否启用后台调度器（默认 true）
- `AIPLAT_JOBS_POLL_SECONDS=2`：轮询间隔
- `AIPLAT_JOBS_BATCH_SIZE=20`：单次拉取 due jobs 数量
- `AIPLAT_JOBS_LOCK_TTL_SECONDS=300`：同一 job 的“重入锁”TTL（防止多实例调度重复执行）
- `AIPLAT_JOBS_DELIVERY_TIMEOUT_SECONDS=10`：webhook 投递超时
- `AIPLAT_JOBS_DELIVERY_RETRIES=2`：webhook 投递重试次数
- `AIPLAT_JOBS_DELIVERY_BACKOFF_SECONDS=1`：重试退避（线性 backoff）

### API（/api/core）
#### 创建 Job
`POST /jobs`

示例（每分钟执行一次 calculator，并投递 webhook）：
```json
{
  "name": "每分钟算一次",
  "kind": "tool",
  "target_id": "calculator",
  "cron": "*/1 * * * *",
  "enabled": true,
  "user_id": "system",
  "session_id": "default",
  "payload": { "input": { "expression": "1+1" } },
  "options": { "toolset": "safe_readonly" },
  "delivery": {
    "type": "webhook",
    "url": "https://example.com/hook",
    "headers": { "Authorization": "Bearer <token>" },
    "include": ["job", "run", "result"]
  }
}
```

#### 手动触发一次
`POST /jobs/{job_id}/run`

#### 查询运行历史
`GET /jobs/{job_id}/runs`

### Webhook payload
当 job_run 结束后（成功或失败），会向 webhook POST：
```json
{
  "type": "job_run",
  "job": { "...": "job fields" },
  "run": { "...": "run fields" },
  "result": { "...": "execution result payload" }
}
```

投递结果会写入 `job_run.result.delivery`（best-effort），便于审计与排障。

### Trace 可追踪字段
调度执行时会在 `payload.context` 注入：
- `source=job`
- `job_id`
- `job_run_id`

这些字段会进入 trace 的 attributes（best-effort），便于从 Traces/Links 反查对应的 Job 与具体 run。
