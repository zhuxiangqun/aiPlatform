# B1 / B2 Route Matrix — Eval API · UI · Errors

> **类型**：契约（B1 实施前置）  
> **版本**：v1.0 · 2026-11-02  
> **状态**：Design baseline · **未实施**  
> **父方案**：[`eval-production-independent-service.md`](./eval-production-independent-service.md)  
> **关联**：[`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md)  
> **对照路由**：`aiPlat-platform/apps/eval/api/`  
> **诚实性**：B1 **禁止**在 API 进程跑动态评测（防「换端口共宿」）；`process_split_authorized=false`。

---

## 1. 统一错误体（强制）

凡拒绝执行（B1 未迁移、B2 allowlist 拒绝、需沙箱），**必须**返回可测 JSON（禁止仅有状态码）：

```json
{
  "error": {
    "code": "execution_not_migrated",
    "runner_id": "skill_suite",
    "retryable": false,
    "detail": "execution plane not migrated until B2"
  }
}
```

| `code` | 典型 HTTP | 含义 |
|---|---|---|
| `execution_not_migrated` | **503** | 阶段未迁移到独立执行平面 |
| `sandbox_required` | **503** 或 **422** | runner 需要 B3 沙箱 |
| `runner_forbidden` | **422** / **403** | allowlist 拒绝（enqueue 或 Worker） |

字段 `error.code` / `error.runner_id` / `error.retryable` / `error.detail` 为契约测试与 UI 断言锚点。

---

## 2. 路由族矩阵

| 路由族（示例） | B1 API | B1 UI | B2 API | B2 UI |
|---|---|---|---|---|
| `GET …/healthz` / `readyz` | 独立 API | 正常 | 独立 API | 正常 |
| store CRUD / list reports / get set | 独立 API（PG/SQLite） | 可用 | 同左 | 可用 |
| runs 只读评价 / 已有报告 | 独立只读或 503 若未迁 | 可读则展示 | Worker `replay_trace` 或只读 API | 正常 |
| `POST …/skill-evals/…/run` | **503** `execution_not_migrated` | Banner：「执行平面尚未迁移（B2）」；只读区仍可用 | 入队 → Worker；非 allowlist → 错误体 | 排队/进度 |
| `POST …/prompts/eval` | **503** 同上 | 同上 | allowlist 则入队 | 同上 |
| `…/kb-eval` 执行类 | **503** | 同上 | 只读检索可入队；写禁止 | 同上 |
| `POST …/arena/run` | **503** | 同上 | 仅纯文本 arena；否则 `sandbox_required` | 同上 |
| 长任务同步跑在 API 进程 | **禁止** | — | **禁止**；一律 Worker | — |
| Job enqueue API（若暴露） | 可收 schema 但 **不执行**；forbidden runner 拒绝 | 提示未就绪 | 真正消费 + 双点 allowlist | 任务列表 |

默认：**B1 动态执行 = 503**，不代理 Central 执行（避免假独立）。

### 2.1 `temporary_proxy`（严格例外）

| 规则 | 要求 |
|---|---|
| 声明 | 矩阵行显式 `temporary_proxy=true` + 到期阶段 |
| 行为 | 可把执行转发 Central（仅过渡） |
| **B1 closeout** | 白名单 **必须清零**；残留 = closeout **FAIL**（假独立） |

---

## 3. UI 降级（`/eval`）

| 条件 | UI |
|---|---|
| 动态执行返回 503 + `execution_not_migrated` | 固定文案：「执行平面尚未迁移（B2）」；不空白崩页 |
| 只读 / 评测集 / 报告 | **保持可用** |
| `sandbox_required` | 「该评测需沙箱（B3），当前不可用」 |
| `temporary_proxy` 清零后 | 不得再静默走 Central 执行 |

契约测试：对代表动态路由断言 **状态码 + `error.code` + `error.retryable=false`**。

---

## 4. B1 / B2 验收钩子

- [ ] 动态执行路由 503 + 完整错误体（字段级）。  
- [ ] `/eval` UI 对 503 有降级文案（手工或 E2E）。  
- [ ] store/health 在独立 API 上绿。  
- [ ] B1 closeout：`temporary_proxy` 计数 = 0。  
- [ ] B2：enqueue + Worker 双点拒绝 `skill_suite`（见 Runtime Contract）。

---

## 5. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-02 | v1.0 | 初版：矩阵、统一错误体、UI 降级、temporary_proxy 清零 |
