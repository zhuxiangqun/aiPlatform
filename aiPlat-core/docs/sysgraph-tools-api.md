# sysgraph 工具 API 文档

16 个代码图谱 MCP 工具，供 AI Agent 探索代码库结构。

## 工具列表

### sysgraph_context
获取任务相关的代码图谱上下文（相关文件、健康评分、统计）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `task` | string | — | 任务描述或问题 |
| `question` | string | — | `task` 别名 |

返回：`{ stats, health, related_files, orphan_files }`

---

### sysgraph_search
按文件名/路径搜索代码库中的文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `query` | string | ✅ | 搜索关键词（≥2 字符） |
| `q` | string | — | `query` 别名 |
| `limit` | integer | — | 最大结果数（默认 10） |

---

### sysgraph_impact
计算文件修改的影响范围（BFS 前向遍历）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 文件路径（相对仓库根目录） |
| `path` | string | — | `file` 别名 |

返回：可达文件列表（blast radius）

---

### sysgraph_callers
查找反向依赖：哪些文件导入了指定文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 文件路径 |
| `limit` | integer | — | 最大结果（默认 20） |

返回：调用方文件列表

---

### sysgraph_node
获取文件完整详情：符号、导入、依赖、跨文件调用、代码片段。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 文件路径 |
| `path` | string | — | `file` 别名 |

返回：`{ symbols, imports, dependents, blast_radius, cross_calls, code_snippet }`

---

### sysgraph_affected_tests
查找受指定文件变更影响的测试文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `files` | string[] | ✅ | 变更文件路径列表 |

返回：受影响的测试文件及其关联原因

---

### sysgraph_review
聚合代码审查上下文：变更文件 × 架构守卫规则检查。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `files` | string[] | ✅ | 待审查文件路径列表 |

返回：`{ changed_files, guard_violations, related_tests }`

---

### sysgraph_deps
返回文件的完整依赖树（双向，可配置深度）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 根文件路径 |
| `depth` | integer | — | 最大深度（默认 3） |
| `direction` | string | — | `both` / `imports` / `dependents`（默认 `both`） |

返回：缩进树形结构 + 跨文件调用列表

---

### sysgraph_diff
对比两个文件的依赖配置文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file_a` | string | ✅ | 第一个文件路径 |
| `file_b` | string | ✅ | 第二个文件路径 |
| `a` | string | — | `file_a` 别名 |
| `b` | string | — | `file_b` 别名 |

返回：`{ shared_imports, unique_a, unique_b, shared_callers, cross_calls, symbol_overlap }`

---

### sysgraph_related
查找与指定文件关联的文件（共享导入、同目录、符号重叠）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 文件路径 |
| `limit` | integer | — | 最大结果（默认 10） |

返回：按相关性排序的文件列表 + 评分原因

---

### sysgraph_stats
返回代码库全局统计。

参数：无

返回：
```json
{
  "total_files": 1154,
  "total_edges": 17385,
  "import_edges": 2367,
  "cross_calls": 15018,
  "total_symbols": 10067,
  "cycles": 20,
  "health_score": 52,
  "health_grade": "D",
  "layers": { "core": 459, "management": 280, "infra": 174, "app": 155, "platform": 86 },
  "top_imported": [...],
  "top_dependents": [...]
}
```

### sysgraph_tests
查找文件的测试文件，或发现未测试的源文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | — | 源文件路径，查找其测试文件 |
| `untested` | boolean | — | 列出未测试文件（默认 file 为空时为 true） |
| `limit` | integer | — | 最大结果（默认 15） |

返回：匹配的测试文件列表 + 测试覆盖率百分比

---

### sysgraph_hotspots
识别代码热点：被依赖最多的文件、依赖最多的文件、问题最多的文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `metric` | string | — | `indegree` / `outdegree` / `issues` / `symbols`（默认 indegree） |
| `limit` | integer | — | 最大结果（默认 10） |
| `layer` | string | — | 按层过滤：core/infra/platform/app/management |

返回：按指标排序的热点文件列表

---

### sysgraph_find
全局查找函数/类定义位置。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `name` | string | ✅ | 函数/类/符号名 |
| `kind` | string | — | 过滤：function / class / async_function |
| `limit` | integer | — | 最大结果（默认 20） |

返回：每个定义的文件路径、行号、kind + 代码片段

---

### sysgraph_churn
查看最近修改的文件（git log + mtime）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `limit` | integer | — | 最大结果（默认 15） |
| `commits` | integer | — | 分析最近 N 个 commit（默认 30） |

返回：git log 变更频率 + 最近修改时间

---

### sys_lsp_fix
Agent 自修正工具：读取 LSP 错误上下文，修复后重新验证。

| 参数 | 类型 | 必填 | 说明 |
|------|------|:--:|------|
| `file` | string | ✅ | 有错误的文件路径 |
| `line` | integer | ✅ | 错误行号 |
| `rule` | string | — | pyright 规则码 |
| `verify` | boolean | — | 修复后重新运行 pyright 验证 |

返回：上下文模式（错误行前后代码）或验证模式（✅/⚠️ + 剩余问题数）

---

## 使用模式

1. **探索代码库**：`sysgraph_search("login")` → `sysgraph_node(file)` → `sysgraph_deps(file)`
2. **评估变更影响**：`sysgraph_impact(file)` → `sysgraph_affected_tests(files)` → `sysgraph_review(files)`
3. **查找关联代码**：`sysgraph_related(file)` → `sysgraph_diff(file_a, file_b)`
4. **全局概览**：`sysgraph_stats` / `sysgraph_context(task)`
5. **测试覆盖**：`sysgraph_tests(file)` / `sysgraph_tests(untested=true)`
6. **热点分析**：`sysgraph_hotspots(metric="indegree")` → `sysgraph_hotspots(metric="outdegree", layer="core")`

## 注册信息

所有工具通过 `core.apps.tools.sysgraph_tools` 注册到 `ToolRegistry`，Agent 通过 `sys_tool_call` 调起。
