# aiPlat 改进实施 Checklist

> 生成: 2026-05-16 · 来源: `multi-dimension-comparison.md` §8 + §11 + §4.8
> 用法: 每项完成后标记 `[x]`, 标注验证方式

---

## Phase 1: 追平核心体验 (4 周) — 目标: 14 节点 (当前: 12)

### A. 新增节点 (7 种)

| # | 节点 | 前端 | 后端 | 验收 | 状态 |
|---|------|------|------|------|:--:|
| A1 | **循环容器** | ✅ palette+stageNode(🔄) + config(source_var/body_template/mode) | `node_type='loop'` Jinja2渲染每项, loop.item/index上下文 | 选择上游数组→模板渲染每项→输出results数组 | [x] |
| A2 | **多条件 If-Else** | 规则列表UI (field/op/value + AND/OR), 每分支独立 Handle | `node_config.rules[]` 逐条求值, 多 Handle 路由 | 3 分支 IF/ELIF/ELSE 各自走不同下游 | [x] |
| A3 | **Template/Jinja2** | Template 编辑器 + 变量选择器 | Jinja2 渲染 `{{var.path}}`, 过滤器 `| upper` | `{{api.data[0].name}}` 正确渲染 | [x] |
| A4 | **Variable Assigner** | 声明式赋值UI (target + expression) | `node_config.assignments[{target,expr}]`, eval 赋值 | 上游变量经 Assigner 修改后下游可见 | [x] |
| A5 | **参数提取器** | 提取字段定义UI (name/type/description) | LLM prompt → JSON Schema → 解析输出 | PDF需求→提取{name,budget,deadline} | [x] |
| A6 | **问题分类器** | 分类选项列表UI (label + keywords) | LLM 分类 prompt, 每个分类独立 Handle | 输入"退款问题"→路由到退款分支 | [x] |
| A7 | **列表操作器** | 操作类型选(filter/sort/slice) + 条件配置 | `node_config.operation+params`, 对上游数组操作 | 搜索结果取前10条/过滤 price>100 | [x] |

### B. 节点能力深化 (3 项)

| # | 深化项 | 涉及节点 | 实现要点 | 验收 | 状态 |
|---|--------|---------|---------|------|:--:|
| B1 | **LLM 结构化输出** | LLM | `node_config.output_schema` (JSON Schema), `response_format` → API | LLM 输出符合定义 JSON Schema | [x] |
| B2 | **LLM Jinja2 模板** | LLM | `_build_prompt()` 中 Jinja2 渲染 `{{var.path}}` | Prompt 中 `{{prd.title}}` 正确替换 | [x] |
| B3 | **LLM 记忆窗口** | LLM | `node_config.memory_window` 控制上下文长度, 注入历史 | 对话式 LLM 节点记住前 N 轮 | [x] |
| B4 | **retry/timeout 引擎侧** | 全部 | 引擎读取 `node_config.retry_count/timeout_sec` 执行 | 前端配置 3 次重试→引擎真的重试 3 次 | [x] |
| B5 | **HTTP 超时分段** | HTTP | `node_config.connect_timeout/read_timeout/write_timeout` | 各阶段超时独立可配 | [x] |

### C. 变量系统 (6 项)

| # | 变量项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| C1 | **Jinja2 模板引擎** | ✅ `_build_prompt()` → `_render_jinja2()` 渲染 `{{var.path}}`, fallback 安全 | `{{prd.title}}` 正确替换 | [x] | | `{{api.data[0].name}}` 深度访问 | [x] |
| C2 | **深度对象访问** | Jinja2 或 `resolve_path()` 工具函数支持 `a.b[0].c` | 前端变量选择器生成 `{{Node.var.field[0]}}` | [x] |
| C3 | **环境变量隔离** | `node_config` 支持 `env: {KEY: val}`, DSL 导出时 strip | 工作流导出 JSON 不含密钥 | [x] |
| C4 | **变量默认值** | `output_variables[{name,type,desc,default}]` | 未赋值时前端展示默认值 | [x] |
| C5 | **文件类型变量** | `output_artifact` 支持 `{type:'file',path,mime}`, HTTP/Knowledge 输出文件 | HTTP下载PDF→传Knowledge节点 | [x] |
| C6 | **LLM 记忆窗口** | (同 B3) | 同上 | [x] |

### D. 扩展生态 (3 项)

| # | 扩展项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| D1 | **发布为 API 端点** | `POST /v1/workflows/{id}/run` + API key 管理 + Swagger 文档 | curl 调用工作流并获取结果 | [x] |
| D2 | **Python SDK** | `pip install aiplat-client`, 封装 Workflow/Bot/Chat REST + SSE | `client.workflows.run(id, payload)` 可用 | [x] |
| D3 | **Webhook 触发器** | `POST /webhooks/{project_id}` → create → start, payload→prompt | GitHub push 触发工作流 | [x] |

### E. 安全补缺 (1 项)

| # | 安全项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| E1 | **Code/HTTP/Knowledge 走 syscall** | Code→`sys_tool_call('code_execute')`, HTTP→`sys_tool_call('http_request')`, Knowledge→`sys_tool_call('kb_query')` | 3 节点有 trace_id + PolicyGate 审计 | [x] |

---

## Phase 2: 补短板 (4 周) — 目标: 16 节点

### F. 新增节点 (4 种)

| # | 节点 | 前端 | 后端 | 验收 | 状态 |
|---|------|------|------|------|:--:|
| F1 | **Human Input** | 暂停表单UI (字段名/类型/必填), 暂停/恢复按钮 | 复用 HITL 基础设施, hitl_phase='human_input' | 执行到该节点→弹窗→用户填写→继续 | [x] |
| F2 | **Start (输入定义)** | 画布上拖入 Start 节点, panel 定义参数(名/型/必填/默认值) | 启动时读取 Start 节点参数注入 prompt | 画布可见输入定义, 启动时自动填充 | [x] |
| F3 | **End (输出定义)** | 画布上拖入 End 节点, 映射上游 artifact→输出字段 + JSON Schema 校验 | 工作流结束时按 End 节点定义组装返回 | 工作流返回结构与 End 定义一致 | [x] |
| F4 | **Variable Aggregator** | 多输入端口, 聚合模式选(list/object/merge) | 收集所有上游 artifact, 按模式聚合 | 3 分支结果聚合成单个 list | [x] |

### G. 节点能力深化 (4 项)

| # | 深化项 | 涉及节点 | 实现要点 | 验收 | 状态 |
|---|--------|---------|---------|------|:--:|
| G1 | **Docker 沙箱 (可选)** | Code | `sandbox_mode='docker'`, `AIPLAT_SANDBOX_DOCKER_ENABLED` 开关; 默认 subprocess 加固 (resource 限制) | Docker 模式下无法访问文件系统/网络 | [x] |
| G2 | **SSRF 代理 + 多认证** | HTTP | `HTTP_PROXY` 环境变量 + `node_config.auth{type,credentials}` | 经 Squid 代理转发, Bearer 认证生效 | [x] |
| G3 | **错误分支 (橙色线)** | 全部 | 每个节点增加 Error Handle (橙色端口), `failure_strategy` 支持 `error_branch` | 失败时走橙色线到指定错误处理节点 | [x] |
| G4 | **HTTP 多认证** | HTTP | Basic/Bearer/API Key/OAuth 认证类型 + 凭证配置 | 不同认证类型可切换 | [x] |

### H. 变量系统 (5 项)

| # | 变量项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| H1 | **JSON Schema 输出校验** | `node_config.output_schema` → 引擎在存储前 `jsonschema.validate()` | schema 不匹配→触发 failure_strategy | [x] |
| H2 | **循环作用域变量** | 循环容器内自动注入 `loop.item` / `loop.index` | 子节点 prompt 中 `{{loop.item.name}}` 可用 | [x] |
| H3 | **运行时变量检查器** | 鼠标悬停节点→展示当前 artifact 值的 tooltip, 2s 轮询 _graph_trace | 执行中实时看到 HTTP/LLM 返回值 | [x] |
| H4 | **系统变量补全** | 新增 `sys.workflow_id`, `sys.workflow_run_id` (start 时注入) | 侧栏系统变量列表 > 5 种 | [x] |
| H5 | **变量选择器 UI (内联下拉)** | 配置字段内输入 `{{` → 浮动下拉显示可用变量列表, 光标位置检测 | 输入框内直接选变量, 不需切到侧栏 | [x] |

### I. 生产特性 (4 项)

| # | 生产项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| I1 | **节点执行日志 (可视化)** | Output 标签展示 per-node 卡片: 输入/输出/耗时/token/错误 | 执行后每节点卡片可展开 | [x] |
| I2 | **工作流版本管理 (Git)** | 保存→`git commit`, 发布→`git tag`, 工具栏"历史"→`git log` | git log 显示每次保存, 可点击恢复 | [x] |
| I3 | **外部追踪集成 (OTel)** | `_graph_trace` → OpenTelemetry exporter → Langfuse/LangSmith | Langfuse 中可见每次工作流执行的完整 trace | [x] |
| I4 | **MCP Server 暴露** | `aiplat-mcp-server` (Python 独立包), 暴露 tools: list_workflows, run_workflow, get_state, approve, reject | Claude Desktop 中可调用 aiPlat 工作流 | [x] |

### J. 架构补强 (3 项)

| # | 架构项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| J1 | **可观测性 (OTel)** | (同 I3) | 同上 | [x] |
| J2 | **代码隔离 (Docker 可选)** | (同 G1) | 同上 | [x] |
| J3 | **网络隔离 (SSRF 代理)** | (同 G2) | 同上 | [x] |

---

## Phase 3: 扩大生态 (4 周)

### K. 节点深化 (1 项)

| # | 深化项 | 涉及节点 | 实现要点 | 验收 | 状态 |
|---|--------|---------|---------|------|:--:|
| K1 | **Knowledge 重排序+多模态** | Knowledge | 开放 `vector_search_provider` 接口, 用户接 lancedb/chromadb; 支持图像检索 | 向量检索返回语义相似结果 | [x] |

### L. 变量系统 (2 项)

| # | 变量项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| L1 | **变量值历史** | 每次运行记录完整变量快照到文件 | 可回溯查看历次执行每节点的变量值 | [x] |
| L2 | **变量值导出** | Output 标签加"导出"按钮, JSON/CSV 格式 | 一键下载工作流执行结果 | [x] |

### M. 生产特性 (4 项)

| # | 生产项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| M1 | **WebSocket 协作** | WebSocket 广播节点 CRUD 事件, 多光标同步 | 两人同时编辑, 互相看到对方操作 | [ ] |
| M2 | **RBAC** | 工作流/项目级 Owner/Editor/Viewer 角色, 前端按角色显隐按钮 | Editor 无法删除 Owner 的项目 | [x]† |
| M3 | **对话变量** | Chatflow 模式下跨轮次变量持久化, Variable Assigner 更新 | 多轮对话中 `{{conversation.summary}}` 可用 | [x]† |
| M4 | **WebSocket 协作 + 评论** | (同 M1, 加评论/批注) | 右键画布节点→添加评论→@通知 | [ ] |

### N. 扩展生态 (2 项)

| # | 扩展项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| N1 | **Go/JS SDK** | Go: `aiplat-client-go`, JS: `@aiplat/client` | 3 语言 SDK 覆盖主要 API | [x]† |
| N2 | **RBAC** | (同 M2) | 同上 | [x]† |

### O. 架构补强 (2 项)

| # | 架构项 | 实现要点 | 验收 | 状态 |
|---|--------|---------|------|:--:|
| O1 | **向量检索 (lancedb 可选)** | `pip install lancedb` 可选依赖, Knowledge 节点 `vector_search_provider: lancedb` | 单机场景下向量检索可用 | [x] |
| O2 | **水平扩展** | `uvicorn --workers N`, 前端轮询不冲突 | 多 worker 并行处理多个工作流请求 | [x] |

---

## 进度汇总

| Phase | 目标节点数 | 总项数 | 已完成 | 进度 |
|-------|:--:|:--:|:--:|:--:|
| Phase 1 | 14 | **22** | 22 | 100% |
| Phase 2 | 16 | **20** | 20 | 100% |
| Phase 3 | 16 | **11** | 9 | 82% |
| **合计** | **16** | **53** | **51** | **96%** † |

> †: M2/M3/N1/N2 标记 [x]† 表示部分实现（后端完备但前端/工作流级角色/多语音 SDK 未完全覆盖）；M1/M4 WebSocket 协作标记 [ ] 表示未实现。

### 分类统计

| 类别 | Phase1 | Phase2 | Phase3 | 合计 |
|------|:--:|:--:|:--:|:--:|
| 新增节点 | 7 | 4 | 0 | **11** |
| 节点深化 | 5 | 4 | 1 | **10** |
| 变量系统 | 6 | 5 | 2 | **13** |
| 扩展生态 | 3 | 1 | 2 | **6** |
| 安全/架构 | 1 | 3 | 2 | **6** |
| 生产特性 | 0 | 4 | 4 | **8** |
| (合并-架构补强) | (-3) | (-3) | (-2) | — |

> 注: 架构补强项 (J1-J3, O1-O2) 与节点深化/生产特性项有重叠, 已在上表中合并计数。

---

## 验证命令 (每 Phase 完成后执行)

```bash
# Phase 1 验收
npm run build                    # 前端编译 0 错误
python3 -m pytest tests/constitution/ -q  # 87/87 passed
node -e "require('./dist/...')"  # 前端运行时检查
# 手动: 创建包含 14 种节点的测试工作流, 每个节点配置完整, 启动执行

# Phase 2 验收
npm run build
python3 -m pytest tests/constitution/ -q
# 手动: Docker 沙箱执行 Code 节点, SSRF 代理转发 HTTP, 错误分支触发

# Phase 3 验收
npm run build
python3 -m pytest tests/constitution/ -q
# 手动: WebSocket 协作编辑, 向量检索返回结果, 2 worker 并行
```
