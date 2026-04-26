# 技能系统 (Skills)（设计真值：以代码事实为准）

> ⚠️ **实现状态提示（As-Is vs To-Be）**：Phase 7 已修复 `SkillManager ↔ SkillRegistry` 桥接断裂，`SkillExecutor` 可从 Registry 执行 Skill；Skill “进化引擎（CAPTURED/FIX/DERIVED）”仍为 To-Be。  
> 完整状态与证据链参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。

> 技能系统定义和管理智能体可执行的能力单元，是智能体完成任务的具体手段。

---

## 模块定位

Skills 模块为 Agent 提供可复用的技能能力单元。

**代码位置**：`core/apps/skills/`

**目录化技能（SKILL.md）位置（engine vs workspace）**：
- engine 默认：`aiPlat-core/core/engine/skills/`
- workspace 默认：`~/.aiplat/skills/`

可覆盖（按 scope 分开配置）：
- `AIPLAT_ENGINE_SKILLS_PATH` / `AIPLAT_ENGINE_SKILLS_PATHS`
- `AIPLAT_WORKSPACE_SKILLS_PATH` / `AIPLAT_WORKSPACE_SKILLS_PATHS`

> `core/apps/skills/` 是 **技能系统引擎代码**（parser/registry/executor 等），不是目录化技能的存放位置。

**核心能力**：
- 技能定义与注册
- 技能发现与匹配
- 技能执行与监控
- 技能版本管理
- 技能权限控制

**详细架构设计**：[Skill 架构设计](./architecture.md)

---

## 模块结构

```
apps/skills/
├── __init__.py              # 模块入口
├── base.py                  # Skill 基类 + 内置技能
│   ├── TextGeneration       # 文本生成
│   ├── CodeGeneration       # 代码生成
│   └── DataAnalysis         # 数据分析
├── registry.py              # SkillRegistry（注册、版本、绑定统计）
├── executor.py              # SkillExecutor（执行、超时、跟踪；inline/fork）
├── discovery.py             # SKILL.md 发现/解析、加载器、匹配器（用于目录化技能 To-Be/部分现用）
├── script_runner.py         # 确定性脚本执行器（sandboxed）
└── types.py                 # SkillManifest/SandboxConfig 等类型
```

> **注意**：当前架构正在向 Agent Skill 模式演进，详见 [Skill 架构设计](./architecture.md#二架构演进从基础到-agent-skill-模式)

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **Skill** | 技能，是智能体可执行的能力单元 |
| **SkillRegistry** | 技能注册表，管理所有可用技能 |
| **SkillExecutor** | 技能执行器，负责技能的具体执行 |
| **SkillContext** | 技能执行上下文，包含输入参数、环境信息等 |

---

## 技能类型

| 类型 | 说明 |
|------|------|
| **生成类技能** | 文本生成、代码生成、图像生成等 |
| **分析类技能** | 文本分析、代码分析、数据分析等 |
| **转换类技能** | 格式转换、语言翻译、代码重构等 |
| **检索类技能** | 知识检索、文档搜索、信息抽取等 |
| **执行类技能** | 命令执行、API 调用、工作流触发等 |

---

## Skill Factory 标准化开发流程（To-Be）

Skill Factory 属于 To-Be 的工程化能力，当前仓库尚未形成可验收闭环：

1. **需求分析**：根据需求定义技能规格
2. **模板生成**：自动生成 skill.yaml 和 SKILL.md
3. **原型实现**：基于原型类型填充代码
4. **质量检查**：自动化校验和测试

---

## 设计原则

- 技能应该是无副作用的纯函数（除非明确标记）
- 技能应该有清晰的输入输出定义
- 技能应该支持幂等执行
- 技能应该支持超时控制
- 脚本优先：确定性逻辑（如 curl 抓取、文件处理）写成脚本，不占上下文，执行更可靠

---

## Skill 自动进化（To-Be）

> 未来方向：让 AI 从执行轨迹中自动蒸馏、生成和优化 Skill。

**EvoSkills 概念（规划）**：

| 阶段 | 说明 | 状态 |
|------|------|------|
| **手动编写** | 人工定义 SKILL.md + handler.py | ✅ 当前 |
| **自动发现** | 扫描目录，自动加载 Skill | 📋 规划 |
| **自动蒸馏** | 从执行轨迹中自动提取 Skill | 📋 未来 |
| **自我进化** | AI 自我生成/优化 SKILL.md | 📋 未来 |

**进化触发条件**：

| 条件 | 说明 | 默认值 |
|------|------|--------|
| 最小样本 | 需要积累足够执行数据 | 10 次 |
| 性能阈值 | 成功率低于此值触发优化 | 70% |
| 进化间隔 | 避免频繁进化 | 1 小时 |

**进化内容**：
- 参数调整：温度、top_p、max_tokens 等参数
- 策略切换：调整工具选择、记忆检索策略
- 能力扩展：注册新技能、启用新工具
- 结构优化：自动重构 SKILL.md 结构

> 详细进化机制见 [Skill 生命周期](./lifecycle.md)

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **harness** | 使用 Harness 的执行循环 |
| **tools** | 技能可以使用工具 |
| **models** | 技能可以使用模型 |
| **agent** | Agent 调用技能完成任务 |

---

## 相关文档

- [Skill 架构设计](./architecture.md) - 详细架构（组件、执行模型、版本管理、Agent Skill模式）
- [Skill 生命周期](./lifecycle.md) - Skill 进化机制 (CAPTURED/FIX/DERIVED)
- [Skill Packs（技能包）](./skill-packs.md) - 技能包的 manifest / publish / install / 安装生效
- [Skill 规范模板 v2（管理台生成 → 开发者精修）](./skill-spec-v2.md)
- [Agent 架构设计](../agents/architecture.md) - Agent 如何调用 Skill
- [Harness 索引](../harness/index.md) - 智能体框架

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- Registry：`core/apps/skills/registry.py`
- Executor（inline/fork）：`core/apps/skills/executor.py`
- 目录化技能发现（SKILL.md parser/loader/matcher）：`core/apps/skills/discovery.py`
- 确定性脚本执行：`core/apps/skills/script_runner.py`
