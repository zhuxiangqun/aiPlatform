# Worker 拆分方案（渐进式）

> 状态：proposed · last_synced: 2026-08-14
> 结论：**当前不拆分**，单进程 asyncio 已满足现状；拆分是「性能出现瓶颈」后的可选演进，非当下目标。

---

## 1. 现状（代码证据）

| 维度 | 现状 | 证据 |
|------|------|------|
| 执行模型 | 单进程 asyncio（FastAPI + uvicorn） | `aiPlat-platform/api/server.py` |
| 流水线调度 | `PipelineEngine` 内部串行/并行调度 | `core/harness/execution/pipeline_engine.py` |
| 长任务进度 | 前端 2s 轮询 `/state` | `_persist_callback` 即时写盘 + 轮询 |
| 横向扩展 | 无独立 worker 进程 | 无 Celery/Redis 依赖 |

## 2. 为什么不现在拆分

依据 `docs/archive/multi-dimension-comparison.md:601-608` 的既定结论：

1. **大部分场景是串行流水线**，单进程 asyncio 已并发处理多请求，无需 worker 池。
2. **引入 Redis + Celery 与「0 依赖单进程」定位冲突**——增加运维复杂度与单点（Redis）。
3. **长工作流通过 2s 轮询获取进度对当前场景足够**，无需消息队列解耦。

## 3. 渐进式三阶段方案

| 阶段 | 触发条件 | 动作 | 复杂度 |
|:--:|------|------|:---:|
| **阶段1（现状）** | — | 单进程 asyncio + 2s 轮询 | 0 |
| **阶段2** | 用户反馈「一条流水线太慢」 | `uvicorn --workers N` 或 `gunicorn + uvicorn workers`（GIL 约束下多进程） | 低（改启动命令） |
| **阶段3（远期）** | 多流水线并行 + 独立扩展需求 | Celery/Redis 独立 worker（API↔Worker 通过 Redis 松耦合） | 高（需评估 Redis 单点 + 调试复杂度） |

## 4. 决策规则

- **默认停在阶段1**，不主动升级。
- 升级到阶段2 的唯一信号：出现「单流水线执行慢」的真实用户反馈。
- 升级到阶段3 需满足：① 多租户并发流水线成为常态 ② 接受引入 Redis 运维成本 ③ 单进程 GIL 瓶颈被实测验证。

## 5. 与决策溯源图 / 成本预算的关系

Worker 拆分（P2-A）是**横向扩展**维度，与 B（决策溯源，纵向诊断）和 C（成本预算，纵向治理）正交。B/C 先落地（P0），Worker 拆分延后（P2）——先纵向把「单流水线做对、做省」，再横向把「多流水线做快」。
