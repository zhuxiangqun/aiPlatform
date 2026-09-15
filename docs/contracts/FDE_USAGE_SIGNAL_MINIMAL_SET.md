# 使用信号采集最小集

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-USAGE-SIGNAL-2026-09` |
| 版本 | v0.3 |
| 状态 | **已落地** S1–S4 聚合 + `/usage-signal` + Tab⑧；基线表/趋势图可选 |
| 关联 | [`FDE_BUSINESS_METRIC_HANDOVER.md`](./FDE_BUSINESS_METRIC_HANDOVER.md) §3 · [`FDE_ESCORT_EXIT_CHECKLIST.md`](./FDE_ESCORT_EXIT_CHECKLIST.md) §C · [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md) §5 · `audit_schema.v1.yaml` |
| 定位 | 只列平台侧现有数据源能直接采的信号；客户侧数据不纳入本集 |
| 实现落点 | `ActionStore`（`core/harness/infrastructure/action_store.py`）· CoreFacade · `/api/platform/apps/fde` · Tab⑧ |

---

## 0. 本集是什么 / 不是什么

| 是 | 不是 |
|----|------|
| 平台侧可观测的最小使用信号集 | 客户侧业务指标 / ROI |
| 来自 `action_audit` 的聚合 | 需要客户 ERP/CRM 的数据 |
| 护航退出清单 §C 的数据支撑 | 完整使用分析平台 |
| 4 个信号，可在同一 store 内查询 | 新建并行 ActionStore |

**原则：能采的必须真采；采不到的诚实标 `not-available`，不造数据。人审通过率 / 使用信号均不得单独作个人 KPI（D6 精神）。**

---

## 0.1 代码事实（交叉验证 2026-09-15）

| 声明 | 证据 |
|------|------|
| 表名 `action_audit` | `action_store.py` `CREATE TABLE IF NOT EXISTS action_audit` |
| 域列已存在：`domain_id TEXT NOT NULL` | 同上；**无需再「加 domain_id 列」** |
| 操作者列名是 **`actor`**（非 `actor_id`） | 列定义 + `insert_audit`；`audit_schema.v1` 逻辑字段 `actor_id` → 列 `actor` |
| 时间列名是 **`created_at`**（非 `timestamp`） | 列 `DEFAULT (datetime('now'))` |
| Action 名列是 **`action_id`**（非 `action_name`） | 列定义 |
| Store 类名是 **`ActionStore`**（异步 aiosqlite；非 `SqlActionStore`） | `action_store.py` |
| 成功态写入可能为 `executed` / `success` / … | Registry 映射：`executed|done|completed|success|ok` → schema `success`；失败 `failed` → `failure` |

**聚合时成功判定（建议）：**

```text
result_status IN ('success', 'executed', 'done', 'completed', 'ok')
```

失败 / 非成功计入分母；`NULL` 行排除或单独计数。

---

## 1. 信号定义

| # | 信号 | 定义 | 数据源 | 健康阈值（建议） |
|---|------|------|--------|------------------|
| S1 | 日活操作人数 | 当日去重 `actor` 数 | `action_audit.actor` | ≥ 2 |
| S2 | Action 日调用量 | 当日行数 | `action_audit` | ≥ 基线 70% |
| S3 | Action 成功率 | 当日成功态 / 总次数 | `result_status` | ≥ 95% |
| S4 | 活跃天数 | 最近 30 天有 Action 的天数 | `created_at` | ≥ 20 / 30 |

---

## 2. SQL 聚合（SQLite；列名以 §0.1 为准）

### 2.1 分窗口查询（推荐落地）

```sql
WITH today AS (
  SELECT actor, result_status
  FROM action_audit
  WHERE domain_id = :domain_id
    AND created_at >= date('now', 'start of day')
),
last30 AS (
  SELECT created_at
  FROM action_audit
  WHERE domain_id = :domain_id
    AND created_at >= date('now', '-30 days')
)
SELECT
  (SELECT COUNT(DISTINCT actor) FROM today) AS dau_today,
  (SELECT COUNT(*) FROM today) AS calls_today,
  (SELECT
     CASE WHEN COUNT(*) = 0 THEN NULL
     ELSE SUM(CASE WHEN result_status IN ('success','executed','done','completed','ok')
                   THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
     END FROM today) AS success_rate_today,
  (SELECT COUNT(DISTINCT date(created_at)) FROM last30) AS active_days_30d;
```

### 2.2 趋势（可选）

```sql
SELECT
  date(created_at) AS day,
  COUNT(DISTINCT actor) AS dau,
  COUNT(*) AS calls,
  SUM(CASE WHEN result_status IN ('success','executed','done','completed','ok')
           THEN 1 ELSE 0 END) * 1.0 / NULLIF(COUNT(*), 0) AS success_rate
FROM action_audit
WHERE domain_id = :domain_id
  AND created_at >= date('now', '-30 days')
GROUP BY date(created_at)
ORDER BY day;
```

### 2.3 索引建议

```sql
CREATE INDEX IF NOT EXISTS idx_action_audit_domain_time
  ON action_audit(domain_id, created_at);

CREATE INDEX IF NOT EXISTS idx_action_audit_domain_actor
  ON action_audit(domain_id, actor, created_at);
```

现有索引：`idx_audit_entity(entity_id, domain_id)`、`idx_audit_action(action_id)` — 不足以覆盖按域+时间的使用信号查询。

---

## 3. API 契约（待实施）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/platform/apps/fde/usage-signal?domain_id=` | S1–S4 当前快照 |
| GET | `/api/platform/apps/fde/usage-trend?domain_id=&days=30` | 按日趋势 |
| GET | `/api/platform/apps/fde/usage-baseline?domain_id=` | 交付后基线（可无） |

**CoreFacade：** `get_fde_usage_signal` / `get_fde_usage_trend`（命名以实施时 Facade 惯例为准）；platform 路由只经 Facade，不直导 `ActionStore`。

**响应骨架：**

```json
{
  "domain_id": "lock-service",
  "dau_today": 2,
  "calls_today": 47,
  "success_rate_today": 0.96,
  "active_days_30d": 22,
  "computed_at": "2026-09-15T04:00:00Z",
  "status": "ok"
}
```

无数据或 store 不可用：`status: "unavailable"`，数值诚实为 0 / null，**禁止造假**。

---

## 4. UI 落点（⑧）

| 项 | 说明 |
|----|------|
| 卡片 | 「使用信号 · {domain_id}」展示 S1–S4 + 健康色 |
| 与现有 KPI | 并列 Quality Bus / Canary / Evolve D6；**正名：使用信号 ≠ 交付质量门** |
| 基线缺失 | 文案「基线未采集」；S2 健康色 = unknown |

健康色建议：S1 ≥2 绿 / 1 黄 / 0 红；S2 ≥基线70% 绿；S3 ≥95% 绿；S4 ≥20/30 绿。

---

## 5. 基线表（可选，Phase 5）

```sql
CREATE TABLE IF NOT EXISTS usage_signal_baseline (
    domain_id TEXT PRIMARY KEY,
    baseline_calls_median REAL,
    baseline_success_rate REAL,
    baseline_active_days INTEGER,
    captured_at TEXT NOT NULL,
    captured_by TEXT
);
```

交付后约 30 天采集一次；不自动滚动更新。

---

## 6. 落地顺序（建议）

1. `ActionStore` 增加 `query_usage_signal` / `query_usage_trend`（async）+ 索引 + 单测  
2. CoreFacade 出口 + `fde` HTTP  
3. Tab⑧ 使用信号卡（可先无折线图）  
4. 台账 §5 KPI：Action 成功率 / 使用信号 → `real`  
5. 基线表 + 采集脚本（护航 30 天复评）

**不做：** 新建 `SqlActionStore`；在 harness 硬编码客户域名；把使用信号当个人 KPI。

---

## 7. 验收标准

- [x] S1–S4 数据来自 `action_audit`，列名与 §0.1 一致（`test_usage_signal.py`）
- [x] 空库返回 0 / null + `ok` 或明确 `unavailable`，不造假
- [x] 按 `domain_id` 隔离
- [x] ⑧ 可见 S1–S4；退出清单 §C 可人工对照
- [x] 台账 / CAPABILITIES / registry 已同步
- [ ] 基线表 `usage_signal_baseline` + 折线图（可选后续）

---

## 8. 风险

| 风险 | 缓解 |
|------|------|
| `result_status` 历史混用 executed/success | 成功集合取并集（§0.1） |
| 演示 actor 全是 `system` | S1 健康阈值按客户约定；记录于交接单 |
| 数据量小波动大 | 退出评估看趋势，不只看单日 |
| 实现骨架误用 `actor_id`/`timestamp` | **以本文件 §0.1 为准**，草稿 SQL 作废 |
| `FdeItemResponse` 吞掉扁平字段 | HTTP 返回 `{"data": payload}`；前端读 `d.data ?? d` |

---

## 9. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1 | 2026-09-15 | 初稿；按 `ActionStore.action_audit` 实列修正字段名与类名 |
| v0.2 | 2026-09-15 | `query_usage_signal` + Facade + `/usage-signal` + ⑧ KPI 已合入 |
| v0.3 | 2026-09-15 | 响应包 `data`；验收勾选 |
