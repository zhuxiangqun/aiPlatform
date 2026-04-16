# Skill 生命周期管理（To-Be 规划为主）

> ❌ **实现状态（As-Is）**：本文档描述的进化引擎（CAPTURED/FIX/DERIVED）尚未实现（自动进化、触发检测、退化检测均未形成闭环）。  
> ✅ **已实现但不属于“进化引擎”**：Skill 版本管理与回滚语义（active_version 查询、回滚影响后续执行配置）已落地。  
> 本文档主要作为 To-Be 设计参考；完整实现状态参见 [架构实现状态](../ARCHITECTURE_STATUS.md)。

> 基于 OpenSpace 实践的 Skill 自动进化机制

---

## 一、生命周期概念

### 1.1 为什么需要生命周期管理

静态 Skill 面临的问题：
- 工具 API 变化导致 Skill 失效
- 边界场景不断涌现无法预知
- 人工维护成本高，容易过时

**核心思路**：让 Skill 像生物一样具备自我进化能力

### 1.2 三种进化模式

| 模式 | 说明 | 场景 | 版本管理 |
|------|------|------|----------|
| **CAPTURED** | 从成功执行中捕获全新可复用模式 | 发现新的最佳实践 | 全新 Skill，无父级 |
| **FIX** | Skill 出错或过时时就地修复 | 执行失败需要修复 | 同名目录，版本号递增 |
| **DERIVED** | 父 Skill 无法覆盖专用场景时新建分支 | 需要针对特定场景优化 | 新目录，与父 Skill 共存 |

---

## 二、CAPTURED 模式

### 2.1 核心概念

从 Agent 的一次成功执行中，自动提取可复用的 Skill。

**触发条件**：
- 执行成功
- 包含可复用的操作模式
- 非偶然成功（可稳定重现）

### 2.2 捕获流程

```
Agent 执行任务
    │
    ▼
分析执行轨迹
    │
    ├─► 是否成功？ ──→ 否 ──→ 丢弃
    │
    ▼
是 ──→ 是否包含可复用模式？
    │
    ├─► 否 ──→ 丢弃
    │
    ▼
是 ──→ 提取为新 Skill (CAPTURED)
    │
    ▼
写入 Skill 库 → 可被后续任务复用
```

### 2.3 捕获判定标准

| 判定维度 | 说明 |
|---------|------|
| **可重复性** | 同样的输入能否稳定产生同样输出 |
| **通用性** | 能否泛化到其他类似场景 |
| **独立性** | 是否有明确的输入输出边界 |
| **价值** | 节省的 token 或执行时间是否有意义 |

---

## 三、FIX 模式

### 3.1 核心概念

当 Skill 执行失败时，自动进行原地修复，生成新版本。

### 3.2 触发条件

| 条件类型 | 示例 |
|---------|------|
| **工具调用失败** | API 返回错误、权限不足 |
| **执行超时** | 超出预期执行时间 |
| **输出不符合预期** | 格式错误、内容缺失 |
| **回退率升高** | 连续多次执行失败 |

### 3.3 修复流程

```
Skill 执行失败
    │
    ▼
分析失败原因
    │
    ├─► 工具问题 → 尝试其他工具
    ├─► 参数问题 → 修正参数
    ├─► 逻辑问题 → 调整执行流程
    └─► 外部依赖 → 添加降级处理
    │
    ▼
生成修复补丁 (Patch)
    │
    ▼
应用修复 → 生成新版本
    │
    ▼
验证修复有效？
    │
    ├─► 否 → 丢弃，标记为无法修复
    │
    ▼
是 → 写入 Skill 库
```

### 3.4 版本命名规范

```
skill-name/
├── v1.0/           # 原始版本
│   └── SKILL.md
├── v1.1/           # 第一个修复版本
│   └── SKILL.md
├── v1.2/           # 第二个修复版本
│   └── SKILL.md
└── metadata.json   # 版本历史记录
```

---

## 四、DERIVED 模式

### 4.1 核心概念

当现有 Skill 无法满足特定场景需求时，从父 Skill 派生新分支。

**与 FIX 的区别**：
- FIX：修复失败，不改变核心功能
- DERIVED：扩展能力，适应新场景

### 4.2 派生场景

| 场景 | 说明 | 示例 |
|------|------|------|
| **领域扩展** | 通用 Skill 需要针对特定领域优化 | 通用代码审查 → Java 代码审查 |
| **格式定制** | 输出格式需要适配特定需求 | 通用报告 → Markdown 报告 |
| **工具替换** | 需要使用不同的工具集 | OpenAI API → Anthropic API |

### 4.3 版本 DAG

```
document-gen-fallback v1.0 (起点)
    │
    ├── DERIVED: legal-memo-gen
    │   │
    │   ├── DERIVED: california-privacy-memo
    │   └── DERIVED: legal-memo-with-validation
    │
    ├── DERIVED: investigation-report-gen
    │   └── DERIVED: surveillance-report-enhanced
    │
    ├── DERIVED: custody-case-report-gen
    │
    └── DERIVED: document-gen-with-recovery
        │
        ├── DERIVED: multi-format-doc-gen
        └── DERIVED: doc-gen-retry-enhanced
```

### 4.4 派生规则

```
派生条件：
1. 父 Skill 无法直接满足当前场景
2. 需要保留父 Skill 的核心能力
3. 新增能力有明确边界

派生约束：
1. 不修改父 Skill 的核心逻辑
2. 新增内容标注清晰来源
3. 允许跨分支合并
```

---

## 五、三触发器引擎

### 5.1 触发器概览

| 触发器 | 触发时机 | 作用 |
|--------|---------|------|
| **Post-Execution Analysis** | 每次任务完成后 | 分析执行记录，发现优化机会 |
| **Tool Degradation Detection** | 工具成功率下降时 | 自动定位依赖该工具的 Skills |
| **Metric Monitor** | 周期性扫描 | 检测 Skill 健康指标异常 |

### 5.2 Post-Execution Analysis

```python
async def post_execution_analysis(execution_record):
    # 分析执行轨迹
    success_patterns = find_success_patterns(execution_record)
    failure_patterns = find_failure_patterns(execution_record)
    
    # 生成进化建议
    if success_patterns:
        yield CAPTURED(success_patterns)
    
    if failure_patterns:
        # 判断是否可修复
        if can_fix(failure_patterns):
            yield FIX(failure_patterns)
        else:
            yield DERIVED(failure_patterns)
```

### 5.3 Tool Degradation Detection

```
工具成功率监控
    │
    ▼
检测到工具 A 成功率下降 (从 95% → 70%)
    │
    ▼
查找所有依赖工具 A 的 Skills
    │
    ├─→ Skill-1 (高优先级，直接修复)
    ├─→ Skill-2 (中优先级，分析后修复)
    └─→ Skill-3 (低优先级，标记待处理)
    │
    ▼
触发进化流程
```

### 5.4 Metric Monitor

| 指标 | 阈值 | 处理 |
|------|------|------|
| **执行成功率** | < 70% | 触发 FIX |
| **回退率** | > 30% | 触发 FIX |
| **平均执行时间** | 增长 50% | 触发优化分析 |
| **Token 消耗** | 增长 30% | 触发效率分析 |

---

## 六、版本管理

### 6.1 版本存储结构

```
skills/
├── document-gen/
│   ├── v1.0/
│   │   ├── SKILL.md
│   │   ├── scripts/
│   │   └── templates/
│   ├── v1.1/
│   │   └── SKILL.md
│   └── metadata.json
│
├── code-review/
│   ├── v1.0/
│   └── v1.1/
│
└── index.json          # Skill 索引
```

### 6.2 metadata.json 结构

```json
{
  "skill_id": "document-gen-fallback",
  "current_version": "v1.2",
  "evolution_history": [
    {
      "version": "v1.0",
      "mode": "CAPTURED",
      "source": "initial_import",
      "created_at": "2026-01-15T10:00:00Z",
      "trigger_task": null
    },
    {
      "version": "v1.1",
      "mode": "FIX",
      "source": "execution_failure",
      "reason": "json_output_parse_error",
      "created_at": "2026-02-20T14:30:00Z",
      "trigger_task": "task_123"
    },
    {
      "version": "v1.2",
      "mode": "DERIVED",
      "source": "legal-memo-gen",
      "reason": "需要法律文档格式支持",
      "created_at": "2026-03-10T09:15:00Z",
      "trigger_task": "task_456"
    }
  ],
  "usage_stats": {
    "total_executions": 1250,
    "success_rate": 0.92,
    "avg_duration_ms": 3200,
    "avg_tokens": 15000
  }
}
```

### 6.3 版本回溯

任意版本可精确回溯：
- 读取历史版本内容
- 查看差异 (diff)
- 恢复到历史版本

---

## 七、Skill 检索

### 7.1 混合检索管线

```
用户任务描述
    │
    ▼
BM25 词法检索 (粗排)
    │
    ▼
Embedding 语义重排 (精排)
    │
    ▼
LLM 最终筛选
    │
    ▼
加载匹配 Skill
```

### 7.2 渐进式披露

| 级别 | 加载时机 | Token 开销 | 内容 |
|------|---------|-----------|------|
| **元数据** | 启动时 | ~100 | 名称 + 描述 |
| **指令** | 触发时 | <5k | SKILL.md 正文 |
| **资源** | 按需 | 无上限 | 脚本、模板 |

---

## 八、相关文档

- [Agent 设计模式](../framework/patterns.md) - 6种核心模式
- [Context 管理](./harness/context.md) - 上下文与记忆
- [Harness 基础设施](./harness/index.md) - 运行时系统

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- Skill 版本/回滚：`core/apps/skills/registry.py`
- Skill 执行（inline/fork）：`core/apps/skills/executor.py`
