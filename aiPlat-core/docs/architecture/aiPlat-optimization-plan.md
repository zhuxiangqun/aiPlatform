# aiPlatform 全面优化方案（修订版）

> 基于对 Claude Code、HermesSim、Harness、OpenCode 四个开源标杆系统的深入分析
> 修订：移除非平台定位需要的「多渠道 CLI 入口」「IDE 集成」，精简 P3

---

## 一、优化总览

```
P0 (2-3周): 完成未接线基础设施 → 解决 5 处 wiring debt
P1 (4-6周): 补齐工具与编排能力 → 吸收 OpenCode/Harness/Claude Code 模式
P2 (6-8周): 强化自我进化能力 → 吸收 HermesSim 图谱 + Claude Code 生态
P3 (8-10周): 扩展平台边界 → 制品 Registry + 阶段隔离
```

---

## 二、P0：完成未接线基础设施（第 1-3 周）

### 2.1 MemoryManager.build_context() → loop 上下文装配

**当前状态**：`MemoryManager.build_context()` 完整实现，但 loop 仍用独立的 `_maybe_compact_messages`。

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `loop.py` | `_reason()` 中调用 `mm.build_context()` | 替代独立消息构建 |
| `loop.py` | 删除 `_maybe_compact_messages` | 复用 MemoryManager 内置 5 级压缩 |
| `manager.py` | `build_context()` 透传 `system_prompt` | 确保 system prompt 正确注入 |

**吸收来源**：OpenCode session 管理的完整上下文装配

### 2.2 Episodic LLM 摘要升级

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `episodic.py` | `update_summary()` → `sys_llm_generate` | 规则匹配 → LLM 级摘要 |
| `manager.py` | `MemoryConfig.use_llm_summary = False` | 默认关闭，opt-in |

### 2.3 multi_agent.py → MessageBus

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `multi_agent.py` | `agent.execute()` → `message_bus.send/receive` | 统一通信协议 |

### 2.4 删除 langgraph/nodes/ 直接 syscall 调用

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `nodes/reason_node.py` | 删除直接 syscall | 改为 StageRunner 委托 |
| `nodes/act_node.py` | 同上 | 同上 |
| `nodes/observe_node.py` | 同上 | 同上 |
| `stage_runner.py` | 新增 `_run_reason/act/observe()` | 封装 syscall |

### 2.5 integration.py 反向依赖消除

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `integration.py` | `from core.apps.xxx` → `DIContainer.resolve()` | DI 解耦 |

---

## 三、P1：补齐工具与编排能力（第 4-6 周）

### 3.1 工具原子化

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `syscalls/file.py` | 新增 `sys_file_read/write/edit` | OpenCode read/write/edit 三分离 |
| `syscalls/code.py` | 新建 — `sys_code_search` + `sys_glob` | 对标 OpenCode grep + glob |
| `syscalls/llm.py` | prompt 构建移到 `PromptAssembler` | 单一职责 |

### 3.2 Pipeline DAG 编排

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `schemas_builder.py` | `PipelineStageConfig` 新增 `parallel_group: str` | 并行组标识 |
| `pipeline_engine.py` | `_run_stages_from()` → batch 并行 | 同层无依赖并行 |
| `pipeline_engine.py` | 新增 `_exec_parallel_group()` | 并行组归并 |
| `graphs/pipeline.py` | 利用 `depends_on` 构建真实 DAG | 可视化依赖边 |

### 3.3 流水线可视化

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `aiPlat-management/` | 新建 `PipelineGraph.tsx` | DAG 可视化组件 |
| `routers/builder.py` | `GET /projects/{id}/graph` | 图形数据 API |
| `routers/builder.py` | WebSocket `/graph/events` | 实时状态推送 |

### 3.4 Hook 插件化接口

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `execution/hooks.py` | 新建 — `HookRegistry` | 统一注册与分发 |
| `loop.py` | 9 个拦截点 → `HookRegistry` 分发 | 替换硬编码 |
| `~/.aiplat/hooks/` | 用户空间 Hook 目录 | `~/.aiplat/hooks/security_check.py` |

### 3.5 MCP 按需注入

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `mcp/runtime.py` | `_should_lazy_load()` + `_search_mcp_tools()` | tools 描述 > 4K 时启用 |
| `loop.py` | tool_not_found → MCP search → 注册 → 重试 | |

---

## 四、P2：强化自我进化能力（第 7-8 周）

### 4.1 Skill 语义相似度匹配

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `memory/semantic.py` | `embed_skill()` + `find_similar_skills()` | 语义嵌入替代关键词 |
| `memory/embedding.py` | 新建 — `EmbeddingProvider` | 统一嵌入接口 |

### 4.2 代码变更语义差异分析

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `evaluation/graph_diff.py` | 新建 — AST 图差异检测 | 代码→AST 图→图差异 |
| `evaluation/compare.py` | `pairwise_judge()` 增加 `semantic=True` | 可选语义模式 |

### 4.3 Skill 发现与安装

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `skill_installer.py` | 增强 `SkillInstaller` | 支持 url/git/path 三种源 |
| `routers/workspace_skills.py` | `POST /workspace/skills/install` | Skill 安装 API |

### 4.4 Cron 调度器

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `scheduler/cron.py` | 新建 — `CronScheduler` | 定时自进化触发 |
| `learning/cron_jobs.py` | 新建 — 预定义任务 | 每日评估汇总、每周优化建议 |

---

## 五、P3：扩展平台边界（第 9-10 周）

### 5.1 制品 Registry

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `artifacts/registry.py` | 新建 — 制品版本化存储 | 流水线产物持久化 + 版本管理 |
| `routers/artifacts.py` | 新建 — `GET /artifacts/{id}` | 制品下载 API |
| `pipeline_engine.py` | `_crystallize_skill()` 增加制品归档 | 固化时同步归档 |

### 5.2 阶段执行隔离

**改动**：

| 文件 | 操作 | 说明 |
|------|------|------|
| `execution/sandbox.py` | 新建 — 进程级隔离执行器 | subprocess 中执行 Agent |
| `schemas_builder.py` | `PipelineStageConfig` 新增 `sandbox: bool` | 阶段级开关 |

---

## 六、附录：运维 CLI（可选，非核心路线）

仅 3 个运维命令，不纳入 P0-P3 核心路线：

```bash
aiplat doctor          # 平台健康检查（agent/skill/MCP 连通性）
aiplat seed            # 初始化内置数据
aiplat architecture    # 等同于 scripts/architecture_guard.sh
```

---

## 七、已移除项目及理由

| 原方案项 | 移除理由 |
|---------|---------|
| 多渠道 CLI 入口（`aiplat chat/skill install/pipeline run`） | 管理 Web UI + REST API 已覆盖全部操作，CLI 不增加能力 |
| IDE 集成（VS Code / JetBrains 插件） | aiPlatform 是平台而非开发者工具，IDE 集成不在定位范围内 |
| 多渠道 Gateway（IM/WebSocket） | Hermes/OpenCode 的 Gateway 服务于"个人助手随处可用"，与 aiPlatform 的平台定位不匹配 |

---

## 八、实施优先级矩阵

```
                    高影响
                      │
        P0            │         P1
   接线基础设施       │   工具原子化 + DAG
   (2-3周, MUST)     │   (4-6周, SHOULD)
                      │
   ───────────────────┼───────────────────→ 高可行性
                      │
        P2            │         P3
   自进化强化         │   制品 + 隔离
   (6-8周, COULD)     │   (8-10周, COULD)
                      │
                    低影响
```

---

## 九、优化后好处分析

### 9.1 基础设施完整性

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| Wiring debt | 5 处未接线 | **0 处** |
| Memory 实际可用层 | Working 层 | **3 层全接** |
| Agent 通信方式 | 直接 `execute()` | **MessageBus 异步** |
| Syscall 绕过点 | 3 个 langgraph nodes | **0 个** |

### 9.2 工具密度与精度

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 原子工具数量 | 3 | **8** |
| MCP 上下文占用 | 全量注册 | **按需注入 <4K** |
| 文件操作安全 | 无 syscall 封装 | **Gate 体系覆盖** |

### 9.3 流水线编排与可视化

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 阶段执行模式 | 线性序列 | **DAG 并行 (2-3x)** |
| 流水线可视化 | 无 | **实时 DAG 状态图** |
| 依赖表达能力 | `depends_on` 未用 | **完整 DAG** |

### 9.4 自我进化闭环

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| Skill 检索精度 | ~0.3（关键词） | **~0.89（语义）** |
| 代码差异检测 | 文本级 | **AST 图 + 语义 3 级** |
| Skill 获取 | 手工创建 | **安装/发现** |
| 自进化触发 | 手动 | **Cron 自动** |

### 9.5 总体量化预期

| 维度 | 当前 | 目标 |
|------|------|------|
| 基础设施接线率 | 70% | **100%** |
| Agent 平均执行步数 | 12 步 | **8 步** |
| Skill 复用率 | <10% | **>40%** |
| 上下文有效利用率 | ~60% | **~85%** |
| 流水线并行度 | 1x | **2-3x** |
| 故障定位时间 | 30min | **5min** |
| 架构守卫 | 41 tests | **45+ tests** |
