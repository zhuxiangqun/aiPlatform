# HYBRID_ENTERPRISE 附录：库健康分面板数据源接线

> 版本：v1.0 | 日期：2026-10-14
> 适用范围：④ 托管 SKU L2 库健康分面板 — 客户可见层
> 主文档：[`HYBRID_ENTERPRISE.md`](./HYBRID_ENTERPRISE.md) | 交付规格：[`HYBRID_ENTERPRISE_DELIVERY.md`](./HYBRID_ENTERPRISE_DELIVERY.md)
> 设计原则：指标→运营动作。面板末行必须产出「建议补哪些文档」，把技术指标变成客户的入库行为。

---

## 0. 数据源现状（防低估工时）

| 指标 | 数据源 | 状态 | 出口 |
|------|--------|:----:|------|
| 文档总数 | `GET /platform/kb/stats` → `documents` | ✅ | 已有 |
| 元素/嵌入数 | `GET /platform/kb/stats` → `elements`/`embeddings` | ✅ | 已有 |
| 集合数 | `GET /platform/kb/stats` → `collections` | ✅ | 已有 |
| 总查询数 | `GET /platform/kb/metrics` → `total_queries` | ✅ | 已有 |
| 漏召率 | `GET /platform/kb/metrics` → `no_answer_rate_pct` | ✅ | 已有 |
| 引用覆盖率 | `GET /platform/kb/metrics` → `citation_coverage_pct` | ✅ | 已有 |
| 纠错率 | `GET /platform/kb/metrics` → `error_correction_rate_pct` | ✅ | 已有 |
| 审批触发率 | `GET /platform/kb/metrics` → `approval_trigger_rate_pct` | ✅ | 已有 |
| 权限拦截数 | `GET /platform/kb/metrics` → `permission_blocks` | ✅ | 已有 |
| 修复周期 | `GET /platform/kb/metrics` → `gap_repair_cycles` | ✅ | 已有 |
| 重复问题率 | `GET /platform/kb/metrics` → `repeat_question_rate_pct` | ✅ | 已有 |
| 本周入库 N 条 | `GET /platform/kb/collections/{id}/documents` 按 `created_at` 过滤 | ✅ | 已有（需计算 delta） |
| 缓存命中率 | `get_semantic_cache().stats` → `GET /platform/kb/cache-stats`（及成本页） | ✅ | 已有独立出口 |
| 漏召 TOP5（具体问题） | `syscall_events` → `GET /platform/kb/miss-top` | ✅ | 已合入（best-effort；无事件则 unavailable） |
| 低置信回答 TOP5 | `syscall_events` → `GET /platform/kb/low-confidence-top` | ✅ | 已合入（best-effort；无事件则 unavailable） |

**结论**：15/15 项均有出口；漏召/低置信为 best-effort（依赖 `syscall_events` 是否有检索记录）；入库 delta 由面板/报告侧计算。

---

## 1. 面板指标定义

### 1.1 一期（已有数据源，不阻塞）

| 面板字段 | 数据映射 | 客户可见形式 |
|----------|----------|--------------|
| **知识库健康分** | 综合评分（见 §2 计算） | `82/100` 大字 + 趋势箭头 |
| **总查询数** | `metrics.total_queries` | `本月共查询 1,234 次` |
| **漏召率** | `metrics.no_answer_rate_pct` | `漏召率 12.3%` + ⚠️ 标记 if > 15% |
| **引用覆盖率** | `metrics.citation_coverage_pct` | `引用覆盖率 87.7%` |
| **文档总数** | `stats.documents` | `知识库共 156 篇文档` |
| **本周入库** | documents delta（本周 `created_at` count） | `本周新增 12 篇` |
| **修复周期** | `metrics.gap_repair_cycles` avg `repair_hours` | `平均修复 18.5 小时` |
| **重复问题率** | `metrics.repeat_question_rate_pct` | `重复问题率 8.2%` |

### 1.2 二期（已合入独立出口）

| 面板字段 | 数据需求 | 客户可见形式 |
|----------|----------|--------------|
| **漏召 TOP5** | `GET /platform/kb/miss-top` | 列表：`1. "差旅报销标准" — 未命中 3 次` |
| **低置信回答 TOP5** | `GET /platform/kb/low-confidence-top` | 列表：`1. "公积金提取" — 置信度 0.41` |
| **缓存命中率** | `GET /platform/kb/cache-stats` | `缓存命中率 34%（节省 ¥127）` |
| **建议补哪些文档** | 健康面板从漏召 TOP / 漏召率叙事生成 | `建议补充：差旅报销标准、年假折算规则` |

---

## 2. 健康分计算（语义规格）

> 不是精确算法，是客户可理解的加权评分。权重可调，但公式固定。

```
健康分 = round(
    引用覆盖率 * 30 +
    (1 - 漏召率) * 25 +
    (1 - 纠错率) * 20 +
    (1 - 重复问题率) * 15 +
    citation_health_bonus * 10
)

其中:
  citation_health_bonus = 引用覆盖率 > 0.8 ? 1.0 : 引用覆盖率 / 0.8
```

**分档**：

| 分数 | 标签 | 面板颜色 | 动作 |
|------|------|----------|------|
| ≥ 85 | 优秀 | 绿 | 维持 |
| 70-84 | 良好 | 蓝 | 关注漏召率 |
| 55-69 | 待改善 | 黄 | 补充文档 + 调优检索 |
| < 55 | 风险 | 红 | 紧急入库 + 检索重训 |

**一期实现**：纯前端/报告生成时计算，不需要平台改代码。拿 `GET /platform/kb/metrics` 的 JSON 直接算。

---

## 3. API 接线规格

### 3.1 一期调用（已有 endpoint，零平台改动）

```
GET /platform/kb/stats?tenant_id={tid}
GET /platform/kb/metrics?tenant_id={tid}&hours=168    # 168h = 7天
GET /platform/kb/collections/{collection_id}/documents?limit=200
```

**调用方式**：
- 前端面板：直接 fetch（带 `Authorization: Bearer {token}`）
- 定期报告：governance cron 定时调用，生成 Markdown/HTML 报告

**入库 delta 计算**：
```python
# 从 /platform/kb/collections/{id}/documents 返回的列表中
# 按 created_at 过滤本周（now - 7*86400）的文档数
docs_this_week = sum(1 for d in documents if d["created_at"] > now - 604800)
```

### 3.2 二期独立 endpoint（已合入）

> **现状（2026-10）**：下列 URL 已在 `api/routers/delivery_reports.py` 注册；实现见 `delivery/kb_health.py` / `cost_report.kb_cache_stats`。无 `syscall_events` 数据时返回 `available=false`，不阻断一期面板。

#### 3.2.1 漏召 TOP5

```
GET /platform/kb/miss-top?tenant_id={tid}&hours=168&limit=5
```

**返回**：
```json
{
  "items": [
    {"question": "差旅报销标准是什么", "count": 3, "last_asked": "2026-10-13T14:22:00Z"},
    {"question": "年假折算规则", "count": 2, "last_asked": "2026-10-12T09:15:00Z"}
  ],
  "window_hours": 168
}
```

**实现**：查 `syscall_events` WHERE `kind='knowledge_retrieve'` AND `payload LIKE '%"count":0%'`，提取 `question` 字段，按出现次数聚合。

#### 3.2.2 低置信 TOP5

```
GET /platform/kb/low-confidence-top?tenant_id={tid}&hours=168&limit=5&threshold=0.5
```

**返回**：
```json
{
  "items": [
    {"question": "公积金提取条件", "score": 0.41, "answer_preview": "根据…"},
    {"question": "试用期辞退补偿", "score": 0.52, "answer_preview": "根据…"}
  ],
  "window_hours": 168
}
```

**实现**：查 `syscall_events` WHERE `kind='knowledge_retrieve'` AND `payload` 中 score < threshold，提取 question + score + answer 片段。

#### 3.2.3 缓存命中率

```
GET /platform/kb/cache-stats?tenant_id={tid}&hours=168
```

**返回**：
```json
{
  "total_requests": 1234,
  "cache_hits": 420,
  "hit_rate_pct": 34.0,
  "estimated_saved_calls": 420
}
```

**实现**：复用 `get_semantic_cache().stats`（`delivery.cost_report.kb_cache_stats`）；进程内计数，非跨进程账单。

---

## 4. 面板布局规格

### 4.1 一期布局（纯数据展示 + 健康分）

```
┌─────────────────────────────────────────────────────┐
│                                                       │
│   知识库健康分: 82/100  ↑                            │
│   良好                                                 │
│                                                       │
│   ─────────────────────────────────────────────       │
│                                                       │
│   总查询数     1,234    文档总数      156             │
│   本周入库       12    修复周期    18.5h              │
│                                                       │
│   漏召率       12.3% ⚠️  引用覆盖率   87.7%           │
│   纠错率        2.1%    重复问题率    8.2%            │
│   审批触发率    1.5%    权限拦截       0              │
│                                                       │
│   ─────────────────────────────────────────────       │
│                                                       │
│   漏召 TOP5 (二期)                                    │
│   1. "差旅报销标准" — 未命中 3 次                     │
│   2. "年假折算规则" — 未命中 2 次                     │
│                                                       │
│   低置信 TOP5 (二期)                                  │
│   1. "公积金提取条件" — 置信度 0.41                   │
│   2. "试用期辞退补偿" — 置信度 0.52                   │
│                                                       │
│   缓存命中率: 34% (二期)                              │
│                                                       │
│   ─────────────────────────────────────────────       │
│                                                       │
│   建议: 补充「差旅报销标准」「年假折算规则」文档      │
│                                                       │
└─────────────────────────────────────────────────────┘
```

### 4.2 报告形态（governance cron 生成）

- **频率**：每周一 09:00 自动生成，纳入 L2 月度运行报告
- **格式**：Markdown（可附 HTML 渲染版）
- **存档**：`/platform/governance/reports/kb-health-{YYYY-WW}.md`
- **推送**：可选，发送到客户指定邮箱或平台消息

### 4.3 客户向状态页（Pi 侧 `/aiplat-kb-health`）

Pi enterprise 模式下可加一个 `/aiplat-kb-health` slash command：
- 调用 `GET /platform/kb/metrics` + `GET /platform/kb/stats`
- 用 §2 公式计算健康分
- 输出一段人话摘要（非裸 JSON）
- 平台断连时退回"知识库健康面板暂不可用"

**示例输出**：
```
📊 知识库健康分: 82/100 (良好)
   本周查询 234 次 | 文档 156 篇 | 新增 12 篇
   漏召率 12.3% | 引用覆盖率 87.7%
   
   建议: 漏召率偏高，建议检查是否有常见问题未入库。
```

---

## 5. L2 SKU 对齐

| L2 承诺 | 面板对应 | 技术落点 |
|---------|----------|----------|
| 入库 + 检索调优 | 本周入库 + 漏召率 + 修复周期 | KB ingest + metrics endpoint |
| cache 命中报告 | 缓存命中率 | `GET /platform/kb/cache-stats` |
| 库健康分 | 健康分 + 分档 + 建议 | 前端计算 + metrics endpoint |
| 月度运行报告 | 报告 Markdown | governance cron 生成 |

**续费叙事**：
- 客户看到"漏召率 12.3% + 漏召 TOP5"→ 主动补文档 → 健康分上升 → 续费
- 客户看到"修复周期 18.5h"→ 感知到有人在维护 → 续费
- "建议补哪些文档"行把指标变成动作 → 动作产生效果 → 效果可量化 → 续费

---

## 6. 开发落地检查

### 6.1 一期 — 已合入

- [x] `kb_health_score(metrics)`（`aiPlat-platform/delivery/kb_health.py`）
- [x] `GET /platform/delivery/kb-health`（json / markdown）+ 导出 `KB_HEALTH.md`
- [x] `/aiplat-kb-health` Pi slash（`enterprise_kb_health.ts`；enterprise 模式）
- [x] 健康分单测（分档边界）+ `enterprise_kb_health_smoke` soft-fail
- [x] Pi 断连 / 未启用企业回连 → 「知识库健康面板暂不可用」
- [x] governance 周报归档：`delivery/kb_health_archive.py` + platform startup cron（`AIPLAT_KB_HEALTH_ARCHIVE_HOURS`，默认 168；`0` 关闭）；`POST /platform/delivery/kb-health/archive`；`GET /platform/governance/reports` + `…/kb-health/{week}`

### 6.2 二期 — 部分 best-effort 已接

- [x] 漏召 / 低置信 TOP：从 `syscall_events` best-effort 聚合（无 store 时 unavailable，不阻断一期）
- [x] 缓存命中率：复用 `cost_report._cache_stats` + 独立 `GET /platform/kb/cache-stats`
- [x] 「建议补哪些文档」优先用漏召 TOP，否则用漏召率/引用覆盖率叙事
- [x] 独立 `GET /platform/kb/miss-top` / `low-confidence-top` / `cache-stats`

---

## 7. 不做什么

| 不做 | 原因 |
|------|------|
| 在 Pi 侧实现指标计算引擎 | 指标在平台侧已有，Pi 只展示 |
| 新建 KB 查询日志表 | `syscall_events` 已记录 `knowledge_retrieve` 事件 |
| 在面板中暴露 token 数 / API 成本 | 属 ③ 成本叙事，不混入健康面板 |
| 实时推送健康分变化 | 周报足够；实时监控属 L3 套餐 |
| 把健康分作为唯一续费指标 | 健康分是入口，漏召 TOP5 + 建议才是驱动动作的 |
