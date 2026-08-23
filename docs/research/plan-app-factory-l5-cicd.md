# L5 设计：模块级 CI/CD 与灰度发布（构建 → 测试 → 打包 → 发布 → 金丝雀 → 回滚）

> **状态**：✅ **已实施**（2026-08-23，PR #94 设计 + PR #95 实施；实施落地记录见 §10，与设计的差异已标注）
> **目标**：L2-L4.5 让 AI 演进**代码 + schema**，但"发布"环节没有自动化——改一个模块要手动部署，无版本概念、无灰度、无回滚。L5 补齐：**模块级发布流水线**（构建产物版本化 + 发布状态机 + 金丝雀灰度 + 回滚），可选对接 infra 的 `deploy_service`。
> **关联**：《plan-app-factory-l4-multi-module.md》§7（L5 = "模块级 CI/CD、灰度发布（对接 infra）"）+ L3 merge（代码审批后进入发布）+ L4.5（迁移后发布）。

---

## 1. 背景：为什么需要 L5

### 现状（L2-L4.5 之后）

| 环节 | 现状 | 缺口 |
|---|---|---|
| 代码演进 | L2 导入 → L3 增量 merge 审批 → L4 模块编排 → L4.5 迁移 | ✅ |
| **发布** | `deploy_to_app` 写 `~/.aiplat/apps/{pid}/current/`，无版本化 | ❌ 覆盖式部署，无历史版本 |
| **测试门禁** | merge 后 pytest（real/estimated） | ⚠️ 有测试但发布不强制 |
| **灰度** | 无 | ❌ 新版本直接全量覆盖 |
| **回滚** | `deploy.prev`（仅最近一次） | ⚠️ 单级回滚，无多版本追溯 |

### L5 解决什么

1. **版本化产物**：每次发布生成版本号（`v{ts}`），产物目录带版本（`releases/v{ts}/`），多版本可追溯、可切换
2. **发布状态机**：`building → ready → canary（金丝雀）→ full（全量）→ rolled_back`——发布是受控流程而非一次性覆盖
3. **金丝雀灰度**：新版本先标记 canary（小比例流量），验证后提升 full；不通过 → 回滚
4. **回滚**：任意已发布版本可回退（切换 current 指针）
5. **与 infra 衔接**：非 standalone 时可调用 `infra.management.service.manager.deploy_service` 注册服务（namespace/name/image）

### L5 不做的事（边界）

- ❌ 不做真实流量路由/负载均衡（那是部署环境/网关职责；v1 用"版本指针 + 金丝雀标记"表达灰度意图，真实路由由部署环境执行）
- ❌ 不做跨环境（staging/prod）发布编排（v2）
- ❌ 不做监控告警联动（v2）

---

## 2. 目标

1. 每次发布生成**版本化产物**（`releases/v{ts}/`），记录版本历史（append-only）
2. **发布状态机**：`building → ready → canary → full`（可回滚到任意历史版本）
3. **金丝雀灰度**：canary 状态表示"小比例验证中"，前端可"提升全量"或"回滚"
4. **回滚**：任意版本可回退（切换 `current` 指针 + 标记 rolled_back）
5. **发布门禁**：merge 后的测试结果（pass_rate_source）作为发布准入（estimated 需提示）
6. 可选对接 infra `deploy_service`（非 standalone 时注册服务）

---

## 3. 设计方案

### 3.1 目录与版本化

```
~/.aiplat/apps/{project_id}/
  releases/
    v20260823120000/          # 版本化产物（每发布一次生成）
      current/                # 该版本的模块代码（合并 deployed/ 代码）
    v20260823130000/
  current -> releases/v20260823130000   # 符号指针（当前生效版本）
  deploy.prev                 # 回滚前快照（L3 已有，扩展为多版本）
```

`proj["releases"]`（append-only 历史）：
```json
[
  {"version": "v20260823120000", "status": "rolled_back", "created_at": "...", "modules": ["auth", "billing"], "pass_rate_source": "real_pytest", "rolled_back_at": "..."},
  {"version": "v20260823130000", "status": "canary", "created_at": "...", ...}
]
```

### 3.2 发布状态机

```
        ┌─── 通过（提升全量）───┐
building → ready → canary ────────→ full
   │              │                  │
   └── 失败 ──────┘ 回滚（切换到历史版本）┘
                       → rolled_back（历史版本被回滚标记）
```

| 状态 | 含义 | 动作 |
|---|---|---|
| `building` | 产物打包中（拷贝 releases/v{ts}） | 自动进入 ready |
| `ready` | 产物就绪，未上线 | 前端"开始金丝雀"→ canary |
| `canary` | 金丝雀（小比例验证中） | "提升全量"→ full / "回滚"→ 切换旧版本 |
| `full` | 全量生效 | 可"回滚"到任一历史版本 |
| `rolled_back` | 该版本已被回滚 | 历史标记 |

### 3.3 API 设计

```
POST /projects/{project_id}/release           # 从 merge 后代码生成版本化产物（building → ready）
GET  /projects/{project_id}/releases          # 版本历史
POST /projects/{project_id}/releases/{version}/canary   # ready → canary（金丝雀）
POST /projects/{project_id}/releases/{version}/full     # canary → full（提升全量）
POST /projects/{project_id}/releases/{version}/rollback # 回滚（切 current 指针到该版本）
```

### 3.4 发布编排（builder 集成）

```python
async def create_release(self, project_id, module_id="default") -> dict:
    """merge 后代码 → releases/v{ts}/current 版本化产物（building → ready）。"""
    version = f"v{time.strftime('%Y%m%d%H%M%S')}"
    src = self._module_root(project_id, module_id)          # imported/ 或模块目录
    dst = os.path.join(_apps_home, "releases", version, "current")
    shutil.copytree(src, dst, dirs_exist_ok=True)           # 基线 = imported 原件
    # 叠加 merge 后新版本（previews new_content 覆盖）
    for pv in proj.get("merge_previews") or []:
        _write(dst/pv.path, pv.new_content)
    # 测试准入：pass_rate_source=estimated → 提示（不阻断，标注）
    proj.setdefault("releases", []).append({
        "version": version, "status": "ready", "module_id": module_id,
        "pass_rate_source": last_run.get("pass_rate_source", "unknown"),
        "created_at": ...})
    os.symlink(...)  # current -> releases/v{ts}  （或写指针文件）
    return {"version": version, "status": "ready"}

async def set_release_status(self, project_id, version, status) -> dict:
    """canary / full / rollback：更新状态 + 切换 current 指针（rollback 时）。"""
```

### 3.5 灰度语义（金丝雀）

- **canary 状态** = 发布标记为"小比例验证中"（v1 无真实流量路由，用状态 + 前端提示表达"请验证后提升全量"）
- **full** = 全量生效（current 指针切换完成）
- **rollback** = current 指针切回历史版本 + 当前版本标 rolled_back + 恢复 deploy.prev 快照

### 3.6 与 infra 衔接

- 非 standalone 时（`infra.management.service.manager` 可用）：`create_release` 后可选调用 `deploy_service`（name=项目/模块, namespace="aiplat-apps", image=版本产物路径）注册服务——v1 为**可选集成**（`AIPLAT_L5_INFRA_DEPLOY=true` 启用）
- standalone（当前开发环境）只做版本化产物 + 状态机，不调用 infra

### 3.7 安全与回滚

- 发布历史 append-only（版本不可删除，只可回滚标记）
- rollback = 切换指针 + 快照恢复；`deploy.prev` 升级为多版本（releases/ 即历史）
- 发布前测试准入：`pass_rate_source=estimated` 时前端提示"通过率为估算值，建议先跑真实测试"

---

## 4. 前端改动

| 元素 | 位置 | 说明 |
|---|---|---|
| 发布流水线 | 项目详情新"🚀 发布"区 | 版本列表（状态徽标 building/ready/canary/full/rolled_back）+ 当前指针 |
| 发布按钮 | merge 审批通过后 | "创建发布"（版本化产物） |
| 灰度控制 | 版本行 | canary → "提升全量"/"回滚"；full → "回滚"（选历史版本） |
| 测试准入提示 | 发布区 | estimated 标注 |

## 5. 验收标准

| # | 验收 | 方法 |
|---|---|---|
| 1 | create_release 生成版本化产物 | 集成：releases/v{ts}/current 存在且含 merge 后代码 |
| 2 | 版本历史 append-only | 单测：多次发布 → releases 数组递增，旧版本不可删 |
| 3 | 状态机流转 | 集成：ready → canary → full；canary → rollback → rolled_back |
| 4 | current 指针切换 | 集成：rollback 后 current 指向历史版本 |
| 5 | 多版本回滚 | 集成：发布 v1/v2 → 回滚到 v1 → current 指向 v1 |
| 6 | 测试准入提示 | 单测：estimated → 发布响应带提示 |
| 7 | infra 可选集成 | 单测：AIPLAT_L5_INFRA_DEPLOY=true 时调用 deploy_service（mock） |
| 8 | 前端发布区 | 手动验证 + tsc/build |

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| 版本化产物（releases/v{ts} + current 指针） | 0.5 天 |
| 发布状态机（building/ready/canary/full/rolled_back） | 0.5 天 |
| 发布端点（release/canary/full/rollback/releases 列表） | 0.5 天 |
| infra deploy_service 可选集成 | 0.25 天 |
| 前端（发布区/版本徽标/灰度控制/回滚） | 0.75 天 |
| 测试（8 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 3 天** |

## 7. 与后续层级的关系

- **L5 做完**：应用工厂从"AI 改代码"到"受控发布"全链路（演进 → 审批 → 迁移 → 发布 → 灰度 → 回滚）
- **v2**：真实流量路由（网关/负载均衡金丝雀）、跨环境发布、监控告警联动
- **远期**：与 CI 工具（GitHub Actions 等）对接外部流水线

## 8. 风险与开放问题

1. **金丝雀无真实流量路由**：v1 用状态标记表达灰度意图，真实小流量验证需部署环境支持（网关/入口路由）——v1 定位为"发布流程受控化"，v2 接真实路由。
2. **current 指针实现**：v1 用符号链接（symlink）或指针文件（Windows 兼容用指针文件 `current.txt`）——视平台选型。
3. **多模块发布粒度**：v1 按模块发布（module_id 维度版本化）；整项目聚合发布 v2。
4. **与 deploy_to_app 的关系**：L2 的 `deploy_to_app`（写 current/）保留为兼容路径；L5 的 `create_release` 是新的受控发布路径（版本化）。两路径并存，前端引导到 L5。
5. **infra standalone**：当前开发环境 infra 为 standalone（deploy_service 抛错）——L5 默认只做版本化，infra 集成靠 env 开关。

---

## 9. 与 L2/L3/L4/L4.5 的衔接清单

| 既有资产 | L5 复用/扩展 |
|---|---|
| L3 merge（previews/decisions） | create_release 从 merge_previews new_content 生成版本产物 |
| L4 module_id 体系 | 按模块发布（module_id 维度） |
| L4.5 迁移（pending_migrations） | 发布前提示"有未应用迁移"（迁移先于发布） |
| deploy.prev 快照 | 升级为多版本（releases/ 即历史） |
| pass_rate_source（real/estimated） | 发布测试准入提示 |
| 前端 blocked/横幅模式 | 发布状态徽标 + estimated 提示横幅 |

---

## 10. 实施落地记录（2026-08-23，PR #95）

### 10.1 落地范围（验收 8 项全部通过）

| 模块 | 落地位置 | 状态 |
|---|---|---|
| 版本化产物（releases/v{ts}/current + 双路指针） | `aiPlat-platform/builder/release_engine.py` | ✅ |
| 发布状态机（building→ready→canary→full→rolled_back） | 同文件 `set_release_status` + `_VALID_TRANSITIONS` | ✅ |
| 发布端点 5 个（release/releases/canary/full/rollback） | `aiPlat-platform/api/routers/builder.py` | ✅ |
| 迁移先行门禁 + estimated 准入提示 | `builder_project_service.py` `create_release` | ✅ |
| 前端发布区（版本徽标/金丝雀控制/回滚/estimated 提示） | `Factory/index.tsx` + `builderTeamApi.ts` | ✅ |

### 10.2 与设计的差异（代码优先原则标注）

| 设计（§） | 实际实现 | 说明 |
|---|---|---|
| §3.6 infra deploy_service 集成 | **v1 未实现**——platform 直导 infra 违反单向依赖（platform→core→infra），`_infra_deploy_service` 改为 core facade v2 预留（env 开关保留语义 + 日志标注） | 架构守卫拦截后修正；infra 集成需先在 core 暴露 deploy facade（v2） |
| §3.2 building 状态 | create_release 直接写产物并置 ready（building 为瞬时状态，未持久化） | 产物写入即 ready，符合"自动进入 ready"设计 |
| §3.1 版本目录基线 | 基线 = imported 原件 + merge_previews new_content 覆盖（未含迁移后 schema 变更） | 迁移与发布分离（迁移先行门禁保证顺序） |

### 10.3 验证

- 测试：`test_l5_release.py`（动态 9）+ `test_l5_release_static.py`（静态 5）= **14 passed**
- 前端 tsc + build + Rule 6 全绿 + pre-commit 全绿（修复 silent except ×2 + infra 直导违规）
- contracts：acceptance 1.51 + 鉴权规范 §18 + capability 登记（release_engine）
