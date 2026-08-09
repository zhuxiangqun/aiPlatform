# AI 应用工厂 — 设计文档

> 最后更新: 2026-08-09
> 覆盖范围: Pipeline 生命周期、HITL 审批、前端状态管理、配置驱动、故障恢复

---

## 1. 架构总览

```
浏览器 → Management:8000 → Platform:8003 → Core:8002
          (前端代理)        (业务逻辑)      (AI 引擎)
```

### 1.1 单一引擎 + Event 驱动

Core 持有唯一 `PipelineEngine` 实例，全局注册表 `_running_pipelines: Dict[str, PipelineEngine]`（key = project_id）。

HITL 审批通过 `asyncio.Event` 实现挂起/唤醒：
- `_resume_event.wait()` — 挂起管道，等待审批
- `engine.approve()` / `engine.reject()` — 同步唤醒，设置 `_resume_event.set()`

### 1.2 单一真相源

SQLite (`pipeline_runs.db`) 是唯一的状态存储。**禁止**使用 `builder_states/{id}.json` 等多文件状态。

表结构：
- `pipeline_runs` — run 级状态（phase, _current_stage_idx, _hitl_*）
- `pipeline_stages` — stage 级详情（agent_id, output_artifact, hitl, hitl_phase, 完整 config）

---

## 2. Pipeline 生命周期

### 2.1 阶段顺序

由 `~/.aiplat/teams/default.yaml` 的 `stages[].order` 字段驱动：

```
order 0: pm_agent          → prd           🔴 HITL (审核)
order 1: architect_agent   → architecture  🔴 HITL (审核)
order 2: agent_engineer    → agent_app     (自动)
order 3: frontend_developer → frontend_pages (自动)
order 4: qa_agent          → test_cases    🔴 HITL (审核)
order 5: test_executor     → test_report   (自动)
```

### 2.2 状态机

```
executing → (stage 完成 + hitl=true) → paused → approve → executing → ...
                                                       reject  → executing (重跑当前 stage)
                                     → (stage 完成 + hitl=false) → executing → ...
executing → (全部完成) → done
executing → (异常) → failed
```

### 2.3 关键状态字段

| 字段 | 来源 | 用途 |
|------|------|------|
| `_current_stage_idx` | 引擎维护 | 当前执行到第几个 stage |
| `_hitl_stage_id` | 引擎写入 | 暂停在哪个 stage（如 `canvas_node_2`） |
| `_hitl_output_artifact` | 引擎写入 | 暂停 stage 的产出物 key（如 `architecture`） |
| `_hitl_phase_name` | 引擎写入 | HITL 阶段名（如 `review`） |

**前端匹配规则**：用 `hitlOutputArtifact === stageKey` 直接定位审批按钮，**不要**用 `id` 或 `agent_id` 字符串匹配。

---

## 3. 配置驱动

### 3.1 团队配置

文件：`~/.aiplat/teams/default.yaml`

```yaml
stages:
  - agent_id: pm_agent
    order: 0
    output_artifact: prd
    skill_name: requirement_analysis
    hitl: true
    hitl_phase: review
```

**设计原则**：引擎层（`pipeline_engine.py`）零硬编码业务概念。所有行为分叉来自 `PipelineStageConfig` 字段。

| ❌ 禁止 | ✅ 应做 |
|--------|--------|
| `if agent_id == "architect_agent"` | `if stage.hitl` |
| `state.get("architecture")` | `state[stage.output_artifact]` |
| 硬编码 `["pm_agent","architect_agent",...]` | 从 YAML 读取 |

### 3.2 新增审核点

1. 编辑 `~/.aiplat/teams/default.yaml`，在对应 stage 加 `hitl: true` + `hitl_phase: review`
2. 前端 **不需要改** — `isHITL` 由 `hitlOutputArtifact` 驱动，自动适配

### 3.3 数据一致性与原子写入

#### 审批操作的 DB 写入顺序

`approve()` / `reject()` 必须遵循以下顺序（`pipeline_engine.py`）：

1. **幂等防御**：`if self._state.get("phase") != "paused": return`
2. **更新内存** `self._state`（phase、HITL 字段）
3. **先同步写 DB** — 同一事务更新 `phase` + `_hitl_stage_id` + `_hitl_phase_name` + `_hitl_output_artifact` + `_current_stage_idx`
4. **DB 确认落盘后**，才执行 `self._resume_event.set()` 唤醒引擎

**反模式（禁止）**：
- 先 `set()` event 再写 DB → 引擎提前唤醒，`GET /state` 可能读到旧状态
- 分多次 DB 事务更新（`update_run_progress` → `update_run_phase` → `clear_hitl_fields`）→ 部分成功导致字段矛盾

#### 原子更新方法

`pipeline_run_store.py` 提供 `atomic_update_phase_and_hitl()` 单 SQL 方法，一次 commit 完成上述全部字段更新：

```python
def atomic_update_phase_and_hitl(self, run_id, phase, current_stage_idx, pass_rate,
                                  hitl_stage_id, hitl_phase_name, hitl_output_artifact, error=""):
    now = _time.strftime("%Y-%m-%dT%H:%M:%S")
    finished = now if phase in ("done", "failed", "cancelled", "expired") else ""
    self._execute("""UPDATE pipeline_runs SET
                     phase=?, error_message=?, finished_at=?,
                     current_stage_idx=?, pass_rate=?,
                     _hitl_stage_id=?, _hitl_phase_name=?, _hitl_output_artifact=?,
                     updated_at=?
                     WHERE run_id=?""",
                  (phase, error, finished, current_stage_idx, pass_rate,
                   hitl_stage_id, hitl_phase_name, hitl_output_artifact, now, run_id))
```

禁止在 `_make_store_callback`（`pipeline_execution.py`）中分三次调用独立更新方法。所有状态变更必须经由原子方法一次落盘。

---

## 4. 前端关键模式

### 4.1 _enterExecutingMode() — 乐观过渡

在 `handleApprove` / `handleReject` **开始时**立即调用：

```typescript
setPhase('executing');  // 进度条立即出现
setHitlStageId(null);   // 清 HITL
setHitlOutputArtifact(null);
// 后台拉真实 state 纠正
```

**之前的问题**：等 API 返回后再 `_refreshFromState`，如果 state 还是 `paused`（后端没 transition），`setPhase('paused')` 不变 → 进度条不出现。

### 4.2 _refreshFromState() — 即时刷新

审批 API 返回后立即调用，复用 poll 的输出构建逻辑，消除 0-3 秒空白。

### 4.3 Poll 定时器

```typescript
useEffect(() => {
  if (phase !== 'executing' && phase !== 'paused' ...) return;
  if (!project.project_id) return;
  const id = setInterval(async () => { ... }, 3000);
  return () => { clearInterval(id); };
}, [phase, project.project_id]);
```

**关键**：**不要**在 effect 里用 `pollInterval` 做互斥 guard（`if (pollInterval) return`）。每次 phase 变化自动销毁旧 interval、创建新 interval。旧 guard 会导致 phase 变化后 poll 永远不跑。

### 4.4 HITL 按钮定位

```typescript
const isHITL = hitlOutputArtifact && key === hitlOutputArtifact;
```

**直接按产出物 key 匹配**。不用 `matchedStage.id === hitlStageId`（不同来源的 id 格式不一致）。

### 4.5 stageOutputs 合并策略

| 管道状态 | 策略 | 原因 |
|---------|------|------|
| `executing` | **渐进式** | 只清空 `_current_stage_idx + 1` 之后的产出，保留当前及上游。避免 stage 切换瞬间 UI 空白 |
| `paused` | **渐进式**（有 race guard） | 同上；若 HITL artifact 缺失则延迟重试 |
| `done` / `failed` | **合并**（`prev => ({...prev, ...})`） | 保留最终全部产出 |

**工具函数**：`_applyProgressiveOutputs(outputs, currentStageIdx, allStageKeys)`

- `allStageKeys` 必须从 `teamStages` 的完整顺序列表传入，**禁止**用 `Object.keys(outputs)` 回退（会丢失顺序）
- 实现逻辑：`const keepIdx = Math.min(currentStageIdx + 1, allStageKeys.length);` 仅保留前 `keepIdx` 个 key

**禁止**全量替换 `setStageOutputs(outputs)`——会导致正在执行的 stage 产出从 UI 短暂消失（3 秒轮询空窗期）。

---

## 5. 审批 + Reject Feedback 流程

### 5.1 正常审批

```
用户点 ✅ → _enterExecutingMode() → 进度条出现
         → API 调 Core approve → 管道继续 → poll 跟踪
```

### 5.2 驳回

```
用户点 ❌ → 清空驳回 stage 及下游产出（保留上游）
         → _enterExecutingMode() → 进度条出现
         → API 调 Core reject(feedback) → 引擎重跑当前 stage
```

feedback 注入到 prompt 顶部（不是末尾）：

```
You are architect_agent.

## 🛑 REGENERATE WITH FEEDBACK — YOU MUST FIX THESE ISSUES
You were rejected and must regenerate. Address EVERY issue below.

测试发现Bug: ...
修复建议: ...

---

{scene_context}
{其他上下文...}
```

实现在 `pipeline_engine.py:8442`，`fb` 变量。

---

## 6. 故障恢复

### 6.1 重启后 paused 管道

`cleanup_orphaned_pipelines()` 在 core 启动时运行：

| 管道状态 | 行为 |
|---------|------|
| `executing` | 标记 `failed`（LLM 调用中断，无法恢复） |
| `paused` | 从 DB 重建 PipelineEngine → 注册到 `_running_pipelines` → `_resume_from_hitl()` 重新进入 HITL 等待 |

### 6.2 恢复所需数据

`pipeline_stages` 表存储完整 stage config（`output_artifact`, `hitl`, `hitl_phase`, `agent_name`, `input_artifacts`），用于重启后重建 `PipelineStageConfig` 对象。

### 6.3 单 project 多条 paused run

只恢复最新的一条，旧 pause 标记 `expired`（去重逻辑在 `cleanup_orphaned_pipelines`），同时清空 `_hitl_stage_id`、`_hitl_phase_name`、`_hitl_output_artifact`，并写入 `error_message='旧暂停记录已清理'`。

前端 `getStatus` 对 `expired` 返回灰色"已过期"标签，项目卡片不展示红色"失败"告警，仅显示"重新构建"按钮。

---

## 7. 已知问题与修复汇总 (2026-08-09)

### 实现细节 (8 项)

| # | 问题 | 修复 | 位置 |
|---|------|------|------|
| 1 | poll 定时器在 phase 变化后死亡 | 移除 `if (pollInterval) return` guard | `index.tsx:449` |
| 2 | HITL 按钮不出现 | 改用 `hitlOutputArtifact` 直接匹配 | `index.tsx:988` |
| 3 | HITL 暂停时下游显示旧数据 | `executing/paused` 时替换 stageOutputs | `index.tsx:493` |
| 4 | pass_rate 显示 8300% | 去掉乘 100（pass_rate 已是百分比） | `index.tsx:1494` |
| 5 | 运行时计时器显示 0s | `started_at` 未设置时不显示秒数 | `index.tsx:836` |
| 6 | approve 后不显示进度（无乐观更新） | `_enterExecutingMode()` | `index.tsx:743` |
| 7 | reject 把所有产出清空 | 只清下游，保留上游 | `index.tsx:765` |
| 8 | approve/reject 后等 3s poll | API 返回后立即 `_refreshFromState` | `index.tsx:697` |

### 设计修复 (4 项)

| # | 问题 | 修复 | 位置 |
|---|------|------|------|
| 1 | 重启后管道消失 | DB 存完整 config + 启动时重建引擎 | `pipeline_execution.py:47` |
| 2 | Feedback 不生效 | 注入到 prompt 顶部 + 强制指令格式 | `pipeline_engine.py:7984,8442` |
| 3 | 重启后 HITL approve 404 | `_resume_from_hitl()` 恢复方法 | `pipeline_engine.py:2374` |
| 4 | 设计文档缺失 → 同样问题反复出现 | 本文档 | 这里 |

### 环境/配置 (3 项)

| # | 问题 | 修复 | 位置 |
|---|------|------|------|
| 1 | macOS gunicorn SIGABRT | `export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` | 启动命令 |
| 2 | Platform 服务器未启动 | 三层都需要起（8000/8002/8003） | 启动脚本 |
| 3 | httpx localhost→IPv6 超时 | 改为 `127.0.0.1` + 超时 60s | `pipeline_orchestrator_client.py` |

### 架构加固 (2026-08-09)

| # | 问题 | 修复 | 位置 |
|---|------|------|------|
| P0 | approve 后内存/DB 状态不一致（三次独立事务导致 phase 与 HITL 字段矛盾） | 原子 SQL 事务 `atomic_update_phase_and_hitl` + 先写 DB 再 `set()` event | `pipeline_engine.py`, `pipeline_run_store.py`, `pipeline_execution.py` |
| P1 | stage 切换时产出闪烁（全量替换清除当前 stage 产出） | 渐进式清理：`_applyProgressiveOutputs` 只清 `idx+1` 之后的 key | `index.tsx` |
| P2 | 旧审批被标记为 `failed`，前端显示红色"失败" | 独立 `expired` 状态 + 灰色标签 + 清空 HITL 字段 | `pipeline_execution.py`, `index.tsx` |

---

## 8. 关键文件索引

| 文件 | 职责 |
|------|------|
| `aiPlat-core/core/harness/execution/pipeline_engine.py` | Event 驱动引擎：run(), approve(), reject(), _resume_from_hitl(), _invalidate_downstream(), feedback 注入 |
| `aiPlat-core/core/api/routers/pipeline_execution.py` | REST 端点：/run, /state, /hitl-resolve, cleanup_orphaned_pipelines() |
| `aiPlat-core/core/harness/execution/pipeline_run_store.py` | SQLite store：schema, upsert_stage(), get_full_state(), list_paused_runs() |
| `aiPlat-platform/builder/builder_project_service.py` | 平台层：rebuild_project(), regenerate_stage(), approve_stage() |
| `aiPlat-platform/builder/pipeline_orchestrator_client.py` | Core HTTP 客户端：trigger_run(), get_state(), resolve_hitl() |
| `aiPlat-management/frontend/src/pages/App/Factory/index.tsx` | 前端主页面：poll, _enterExecutingMode, _refreshFromState, render |
| `~/.aiplat/teams/default.yaml` | 团队配置：stages, hitl, output_artifact |

---

## 9. 开发约定

### 9.1 新增 stage

1. 在 `~/.aiplat/teams/default.yaml` 添加 stage 定义
2. 创建对应 agent 的 `AGENT.md`（含 SOP）
3. 创建对应 skill 的 `SKILL.md`
4. **不需要改前端** — stage 列表由 `teamStages` 驱动

### 9.2 修改 HITL

1. 编辑 `~/.aiplat/teams/default.yaml` 的 `hitl: true/false`
2. **不需要改前端** — 按钮由配置驱动

### 9.3 修改 approve/reject 流程

1. 如果改动涉及后端：改 `pipeline_engine.py` 的 `approve()` / `reject()` / `_resume_from_hitl()`
2. 如果改动涉及前端过渡：改 `_enterExecutingMode()` 和 `_refreshFromState()`
3. **不要**在 handler 里散落 setState 调用

### 9.4 启动命令

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES

# Core (8002)
cd aiPlat-core && gunicorn -c gunicorn.conf.py -w 1 --threads 2 core.server:app

# Platform (8003)
cd aiPlat-platform && gunicorn -c gunicorn.conf.py -w 1 --threads 2 api.rest.routes:app

# Management (8000)
cd aiPlat-management && gunicorn -c gunicorn.conf.py -w 1 --threads 2 management.server:create_app
```

### 9.5 测试检查清单

新增/修改 pipeline 相关代码后，必须测试：
- [ ] 新项目 → PM → 审核 → 架构师 → ... → done
- [ ] 重建 → PM → 审核 → ... → done
- [ ] 审批通过 → 进度条出现（< 1s）
- [ ] 驳回 → 上游产出保留 → 当前 stage 重跑
- [ ] 重启 core → paused 管道状态保留 → approve 正常
- [ ] npm run build 通过

---

## 10. 未来改进

| 方向 | 现状 | 改进 |
|------|------|------|
| 多 worker | `-w 1`，LLM 执行期间 HTTP 阻塞 | 3+ workers + 会话亲和 |
| 推送通知 | 3s 轮询 | WebSocket 推送 phase 变化 |
| 管道进度 | `_progress` 字段偶尔缺失 | 每个 stage 入口/出口强制写入 |
| DB 持久化 | SQLite 单文件 | 可切换 PostgreSQL（已有 schema） |
| 测试覆盖 | 手动 E2E | 自动化 pipeline 测试套件 |
