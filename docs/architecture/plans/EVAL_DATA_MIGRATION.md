# EVAL Data Migration & Rollback（B3 前置定义）

> **类型**：契约（B1 前写清；B3 执行）  
> **版本**：v1.0 · 2026-11-02  
> **状态**：Design baseline · **未实施生产迁移**  
> **父方案**：[`eval-production-independent-service.md`](./eval-production-independent-service.md)  
> **诚实性**：B1 仅空库/脱敏；**禁止**无备份/PITR 演练就做生产回填；不翻转 `process_split_authorized`。

---

## 1. 阶段策略

| 阶段 | 数据 |
|---|---|
| **B1** | staging **空库**或 **脱敏样本**；验证 migrations |
| **B3** | 回填 + **dual-read 对账**；可回滚 cohost |
| **B4** | 备份/PITR/故障 live 证据（迁移窗口前必须已有演练清单） |
| **B6** | 授权后切流；仍保留回滚 |

---

## 2. 源清单（盘点对象）

实施前用脚本列出并版本化；下列为初始范围：

| 源 | 内容 | 迁入 |
|---|---|---|
| `packages/aiplat-evaluation` SQLite `eval.store.v0` | sets/tasks/runs/judgments/reports/… + `tenant_id` | Eval PG |
| Platform/Central EvalStore（若共宿表） | 评测集/报告元数据 | Eval PG |
| `execution_store` 中评测相关键 | 证据指针 / 摘要 | URI → Object Store + PG ref |
| `~/.aiplat` 下 eval/gold 文件 | gold YAML、本地报告 | Object Store 或受控导入 |
| KB eval 只读依赖 | **不**复制整库；保留 EvidenceRef / API | 引用 |

**禁止**：迁移 FDE 真源、Ontology 主数据、无关 Central 业务表。

---

## 3. 迁移模式

1. **B1**：`migrate up` 空 schema；加载脱敏 fixture。  
2. **B3 回填**：一次性或分批 ETL（带 `source_id` / `migrated_at`）。  
3. **Dual-read**：同一查询在 cohost 源与 Eval PG 比对。  
4. **不默认双写** v1；若需双写须另补 ADR（避免隐式分叉）。

### 3.1 对账口径

| 检查 | 通过标准 |
|---|---|
| 数量 | sets/tasks/runs/reports 计数一致（或豁免清单） |
| ID | 主键/业务 id 集合一致 |
| 分数 hash | 报告 metrics 规范化后 hash 一致 |
| 租户 | 无跨租户泄漏行 |

不一致 → **停切流**；修 ETL 或标豁免（需签字）。

---

## 4. 回滚到 cohost

| 触发 | 动作 |
|---|---|
| 对账失败 | 停止 B3 切读；API 指回 Central cohost |
| 数据损坏 / 严重回归 | `AIPLAT_EVAL_MODE=cohost` 或关掉 `AIPLAT_EVAL_SERVICE_URL` 代理 |
| 迁移窗口超时 | 预公告回滚；保留 Eval PG 只读取证 |

回滚 **不删** Eval PG 数据（除非单独清理工单）；源 cohost 数据迁移期只读或冻结写入策略在 runbook 写明。

---

## 5. 备份 / PITR（迁移前）

在 **首次生产级回填之前** 必须具备（证据挂 B4，清单本此预定义）：

- [ ] Eval PG 逻辑备份 + 恢复演练  
- [ ] PITR 或托管等价能力说明  
- [ ] Object Store 版本/复制策略  
- [ ] 回滚指挥官与变更窗口  

无勾选 → **禁止** B3 生产数据回填。

---

## 6. 对象存储（与迁移相关）

- 大轨迹/附件：PG 只存 URI + content hash。  
- 加密 at rest；presigned GET 短 TTL。  
- 生命周期：热/冷分层可后置，但红队/PII 前缀 **隔离 bucket 或前缀 ACL**。  
- 迁移校验：抽检 URI 可读且 hash 匹配。

---

## 7. 验收

- [ ] B1：空库/脱敏 migrations 可上可下。  
- [ ] B3：对账报告零未解释差异。  
- [ ] 演练：切读 Eval → 回滚 cohost 成功。  
- [ ] 迁移前备份/PITR 清单已勾选。

---

## 8. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版：源清单、dual-read、回滚、迁移前备份硬门 |
