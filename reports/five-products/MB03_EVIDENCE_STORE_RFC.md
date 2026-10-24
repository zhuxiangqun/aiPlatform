# MB-03 RFC：诊断 MVP 证据持久化选型（草案）

> **效力**：独立 RFC 草案（MODULE_BACKLOG 允许「Gate 2 或独立 RFC」）。  
> **不是**开工令：本文不批准改生产默认存储、不迁数据、不换 API 语义。  
> **日期**：2026-10-24  
> **现状真源**：`slice_evidence.py` → `$AIPLAT_HOME/five_products_slice/evidence/*.json`

---

## 1. 问题

首切片诊断 MVP 已用本地 JSON 文件满足 E3。扩大复用或多实例时会出现：

| 缺口 | 说明 |
|------|------|
| 无多租户隔离键 | 路径仅按 `AIPLAT_HOME`，无 tenant |
| 无 TTL / GC | ingest/report 只增不删 |
| 无跨机权威 | 文件在单机 home，不可作为集群真相源 |
| API 已版本化入口 | `ingest` / `report` / `ingest-jsonl` 形状可保留；换后端应透明 |

---

## 2. 非目标（本 RFC）

- 诊断全功能 / Evaluation 二期  
- 新建「诊断中台」微服务或新库  
- Gate 2 模块化搬迁、改生产默认路径  
- 在未选型批准前改 `slice_evidence._store_root()` 行为  

---

## 3. 方案对比（推荐默认）

| 方案 | 做法 | 优点 | 缺点 | 建议 |
|------|------|------|------|------|
| **A. 文件保留 + 契约冻结** | 维持 JSON；文档标明「单租户/单机 MVP」 | 零成本；已接线 | 不可水平扩展 | **现状默认** |
| **B. SQLite 同进程** | `$AIPLAT_HOME/.../evidence.db`；表 `ingest`/`report`；API 不变 | 可查询/GC；零新服务 | 仍单机 | **下一实现候选** |
| **C. 复用 platform 已有 store** | 挂现有 execution_store / ActionStore 风格 aiosqlite | 运维一致 | 需证明不污染其它域 | 若 B 落地时优先评估复用 |
| **D. 外部 DB** | Postgres 等 | 多实例 | 超切片范围；需运维与 Gate2 | **延期** |

**推荐决策（待架构×诊断临时 R 联签后再生效）**：保持 **A** 为生产默认，直至有第二消费者或多租户需求；届时按 **B（优先评估 C 复用）** 实现，对外 HTTP/CoreFacade 签名不变，仅换 `_store_root` 后端。

---

## 4. 若批准 B/C 的最小契约

不变：

- `status ∈ {ok,unknown,stale,fail}`；禁默认 healthy  
- `report_id` / `ingest_id` 稳定字符串  
- fp- signoff 仍只要求 report **存在**（除非另开变更）  

新增（可选字段，向后兼容）：

- `tenant_id`（缺省 `""` = 单租户）  
- `expires_at` / GC 策略配置（YAML，非 .env 行为开关）  

回滚：feature 开关或环境变量指向文件后端；DB 文件可丢弃（MVP 无强一致承诺）。

---

## 5. 验收（仅当实现 PR 时）

1. 现有 `test_slice_five_products` / fault injection 全绿  
2. 文件→SQLite 双后端切换测试：同一 ingest 语义  
3. `architecture_guard` / 无新平行 ingest API  
4. CAPABILITIES + capability_registry 同步  

---

## 6. 签署（未签）

| 角色 | 状态 |
|------|------|
| 架构决策 owner | 未签「批准实现 B/C」 |
| 诊断临时 R | 未签 |
| 业务场景 owner | 知晓即可（非客户验收） |

**当前生效**：仅采纳「维持 A + 本文为选型记录」。实现须另开 PR 并引用本 RFC 批准节。
