# A2.3 看板+Cron 定时调度 — 设计文档

> 框架一 A2 轴（自调度编排）从 L3→L4 的关键缺口。现有 `KanbanEngine`（kanban_engine.py）和 `CronScheduler`（scheduler/cron.py）已就绪，A2.3 是**接线任务**：把 H4 的 `distribution.yaml` Cron 条目 → CronScheduler → KanbanEngine 状态流转。

last_synced: 2026-07-07
status: design
owner: A2-axis (framework_one)
depends_on: H4 配置分发（distribution.yaml Cron 格式已定义）

---

## 0. 现状

| 已有模块 | 文件 | 能力 | 缺什么 |
|---------|------|------|------|
| `KanbanEngine` | `coordination/kanban_engine.py:23` | SQLite 看板：6态（pending→todo→running→blocked→done→archived），依赖链，Profile 隔离，重试计数，`_transition()`/`get_pending_tasks()`/`get_tasks_by_profile()` | 缺 Cron 触发入口，缺 HTTP API |
| `CronScheduler` | `scheduler/cron.py:39` | asyncio cron：`register()`/`start()`/`stop()`/`get_status()`, `CronJob` dataclass，间隔秒级精度 | 缺 `distribution.yaml` Cron 条目 → `register()` 的桥，缺 Kanban 状态写回 |
| `distribution.yaml` | H4 设计（§1, cron 条目格式已定义） | `cron: [{name, schedule, goal, profile, timeout_s}]` | 需安装时注册到 CronScheduler |

## 1. 数据流

```
distribution.yaml (H4 产出)
    ↓ 安装时解析 cron[] 条目
CronScheduler.register(name, schedule, handler)
    ↓ 每 tick 检查到期的 job
_kanban_cron_wrapper(name, goal, profile)
    ↓ 创建 KanbanEngine task
KanbanEngine.create_task(title=goal, profile_id=profile)
    ↓ 状态流转
pending → todo → running → done (成功) / blocked → retry (失败)
    ↓
HTTP API 暴露 GET|POST|PATCH /kanban/tasks
```

## 2. 设计变更

### 改动 1：`hermes-profile-install.sh` 扩展 — 安装时解析 cron 并启动 Scheduler

在 install.sh 的 `PYEOF` 块末尾（agents/skills/mcp 安装之后），新增：

```python
# ═══ A2.3 新增: Cron 注册到运行中的 Scheduler ═══
if dist.get("cron") and dist["cron"]:
    # 写 Cron 条目文件给下次启动时 CronScheduler load
    cron_dir = os.path.join(target_dir, "cron")
    os.makedirs(cron_dir, exist_ok=True)
    for i, entry in enumerate(dist["cron"]):
        entry_path = os.path.join(cron_dir, f"{entry.get('name', f'cron_{i}')}.yaml")
        import yaml
        with open(entry_path, "w") as f:
            yaml.dump(entry, f, allow_unicode=True)
    print(f"  Cron jobs: {len(dist['cron'])} registered (will be loaded on next restart)")
```

```bash
# 重启后 CronScheduler 自动 load ~/.aiplat/cron/*.yaml
# via aiPlat-core startup hook
```

### 改动 2：`aiPlat-core` 启动时从 `~/.aiplat/cron/*.yaml` 加载 Cron 条目

新增模块 `aiPlat-core/core/harness/scheduler/cron_loader.py`（约50行）：

```python
"""Cron loader — 启动时扫描 ~/.aiplat/cron/*.yaml 并注册到 CronScheduler."""

import os, yaml
from core.harness.scheduler.cron import get_cron_scheduler, CronJob
from core.harness.coordination.kanban_engine import KanbanEngine

def load_cron_from_profile() -> int:
    """Scan ~/.aiplat/cron/*.yaml and register jobs. Returns count registered."""
    scheduler = get_cron_scheduler()
    home = os.path.expanduser(os.environ.get("AIPLAT_HOME", "~/.aiplat"))
    cron_dir = os.path.join(home, "cron")
    if not os.path.isdir(cron_dir):
        return 0

    kanban = KanbanEngine()
    registered = 0
    for entry_file in os.listdir(cron_dir):
        if not entry_file.endswith(".yaml"):
            continue
        with open(os.path.join(cron_dir, entry_file)) as f:
            entry = yaml.safe_load(f)
        if not entry or "name" not in entry:
            continue

        name = entry["name"]
        interval = _cron_to_seconds(entry.get("schedule", ""))  # cron expr → seconds
        goal = entry.get("goal", "")
        profile = entry.get("profile", kanban.DEFAULT_PROFILE)

        async def _handler(g=goal, p=profile, kg=kanban):
            task_id = kg.create_task(profile_id=p, title=g,
                                     description=f"Cron job by '{g}'")
            await _execute_and_transition(kg, task_id, g)

        scheduler.register(name, interval, _handler)
        registered += 1
    return registered


def _cron_to_seconds(expr: str) -> int:
    """Minimal cron → interval seconds. Full parser later."""
    # Standard cron: "0 3 * * *" means daily at 3am
    # For MVP: parse as ISO pattern or default to 3600
    import re
    if expr == "@hourly" or expr == "0 * * * *":
        return 3600
    if expr == "@daily" or re.match(r"^(\d+) (\d+) \* \* \*$", expr):
        return 86400
    return 3600  # fallback
```

### 改动 3：KanbanEngine 补充 `create_task()` + HTTP API

`kanban_engine.py` 已有完整的 `_init_db()` + `_transition()` + getters。需要补：

```python
# kanban_engine.py 自身新增
def get_all_tasks_by_status(self, profile_id: str = "default") -> dict:
    """Return tasks grouped by status for kanban board display."""
    with self._lock:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT task_id, title, status, priority, scheduled_at, created_at, "
            "retry_count, max_retries "
            "FROM tasks WHERE profile_id = ? ORDER BY priority DESC, created_at ASC",
            [profile_id]
        ).fetchall()
        tasks_by_status = {}
        for r in rows:
            stat = r[2]
            tasks_by_status.setdefault(stat, []).append({ ... })
        return tasks_by_status
```

HTTP API（最小暴露，接入诊断画面/看板 UI）：

| 端点 | 方法 | 作用 |
|------|------|------|
| `GET /kanban/tasks?profile={id}` | GET | 返回该 profile 的所有任务（按状态分组） |
| `POST /kanban/tasks` | POST | 手动创建任务（供 UI 或调试） |
| `PATCH /kanban/tasks/{task_id}/status` | PATCH | 手动状态转换（block/retry/close） |
| `GET /health/kanban` | GET | 看板健康（任务总数/阻塞数/过期数） |

**API 模块**：`aiPlat-core/core/api/routers/kanban.py`（约 100 行），复刻现有 cron 路由模式。

### 改动 4：GoalExecutor wired to Kanban (from distribution cron)

当 CronScheduler 触发 job 后，看板任务创建。`_execute_and_transition` 需要：

```python
async def _execute_and_transition(kb: KanbanEngine, task_id: str, goal: str):
    try:
        kb._transition(task_id, "running")
        # 此处调用 GoalExecutor.execute_goal_by_key(goal) — 需要 GoalGenerator 新增
        success = await _dispatch_goal(goal)
        kb._transition(task_id, "done" if success else "blocked",
                       reason=f"Goal '{goal}' completed" if success else f"Goal '{goal}' failed")
    except Exception as e:
        kb._transition(task_id, "blocked", reason=str(e))
```

## 3. 改动文件清单

| 文件 | 改动 | 工作量 |
|------|------|:---:|
| `scripts/hermes-profile-install.sh` | Cron 条目写入 `~/.aiplat/cron/` | 约 8 行 |
| `aiPlat-core/core/harness/scheduler/cron_loader.py` | **新建** — 启动时加载 Cron 条目 | 约 70 行 |
| `aiPlat-core/core/harness/coordination/kanban_engine.py` | `create_task()` + `get_all_tasks_by_status()` | 约 30 行 |
| `aiPlat-core/core/api/routers/kanban.py` | **新建** — 4 个 HTTP API 端点 | 约 100 行 |
| `aiPlat-core/core/server.py` | hook `load_cron_from_profile()` on startup | 约 3 行 |
| `docs/framework/assessment-spec.yaml` | A2.3.declared_level 从 null→L3 | 1 行 |

## 4. 对框架评分的即时影响

| 轴 | 之前 | 之后 | 原因 |
|:--|:--|:--|:---|
| A2.3 | null (gap) | L3 (declared_level) | Cron 看板 + 状态流转已落地 |
| A2 轴综合 | L3（包含空缺口） | L4 | A2.3 补齐 + A2.4 仍缺口但不再 null |
| 框架一 | 3.91 | 约 4.1+ | A2 轴升级（权重 0.15 × 值 1 提升 = 0.15 贡献增长） |

## 5. 验证

```bash
# 1. 启动
AIPLAT_CORE_ENABLED=true python3 -m aiPlat-core.server &
sleep 5

# 2. 看板 API
curl -s http://localhost:8002/api/core/kanban/tasks?profile=default

# 3. 手动创建任务 → 应触发状态流转
curl -X POST -H "Content-Type: application/json" \
  -d '{"title":"test-task","profile_id":"default","priority":1}' \
  http://localhost:8002/api/core/kanban/tasks

# 4. Cron 加载验证
curl -s http://localhost:8002/api/core/health/kanban | jq

# 5. 重新评估
python3 scripts/compute_assessment.py --quiet \
  && python3 -c "import json; d=json.load(open('docs/framework/assessment-scores.json')); [print(a['id'], a['declared_level']) for a in d['frameworks']['framework_one']['axes'] if a['id']=='A2']"
# → A2 expected: L4
```

## 6. 依赖关系

```
H4 配置分发（distribution.yaml Cron 格式）— 先决条件
    ↓
A2.3 看板+Cron（本文档）
    ↓ Cron 注册格式在此实现
A2.4 Profile 命名空间隔离（远期 — 依赖 Profile 框架就绪）
```
