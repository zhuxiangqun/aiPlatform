---
name: code_generation
display_name: 代码生成
description: '根据需求描述生成代码（## FILE: 格式）。触发条件：用户要求写代码、生成项目、实现功能、修复Bug。跳过条件：纯文本生成(text_generation)、SQL查询(sql相关)、配置修改时由对应
  Skill 处理。'
category: generation
uses_file_output: true
version: 1.0.0
skill_model_purpose: code_gen
status: enabled
protected: true
idempotent: false
completion_criterion: |
  1. 输出符合 ## FILE: 格式规范
  2. 每个文件包含完整可运行代码
  3. 所有依赖项已声明，所有外部引用已校验
execution_mode: handler
execution_type: prompt
triggers:
  - 写代码
  - 实现
  - 编写
  - 生成代码
  - 帮我写
permissions:
- llm:generate
effects:
- type: write
  resources:
  - filesystem:~
  idempotent: false
  rollback_available: true
input_schema:
  requirement:
    type: string
    required: true
output_schema:
  $ref: "code"
  type: string
  required: true
  description: 面向人阅读的 Markdown 输出，与结构化字段一致
metadata:
  trigger_conditions:
  - 生成代码
  - 写代码
  - 编写函数
  - 实现功能
  - 代码生成
  - 创建模块
  - 编写程序
  - 写个API
  - 生成类
  - 实现接口
  keywords:
    objects:
    - 代码
    - 函数
    - 类
    - 模块
    actions:
    - 生成
    - 编写
    - 实现
    - 创建
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 根据需求生成高质量可执行代码
sop_flow:
  - "代码生成（Engine）"
  - "解析需求：输入语言、框架、代码风格、测试要求。"
  - "生成代码：## FILE: 格式，每文件包含完整实现。"
  - "自检：语法正确、导入完备、安全无注入。"
  - "根据需求生成高质量可执行代码"
  - "[ ] 输出格式符合规范"
  - "[ ] 正确处理错误和边界条件"
  - "[ ] 返回结果包含引用和来源标注"
keywords:
  objects:
  - 代码
  - 函数
  - 类
  - 模块
  - API
  - 脚本
  - 测试
  actions:
  - 生成
  - 编写
  - 实现
  - 创建
  constraints:
  - 语言
  - 框架
  - 代码规范
trigger_conditions:
- when: 用户要求生成代码
  query: 写代码/实现/创建API/开发
- when: 不应用场景
  description: 跳过条件：用户仅询问概念、对比工具而非实际写代码时不触发。
skip_when: 跳过条件：用户仅询问概念、对比工具而非实际写代码时不触发。
---



# 代码生成（Engine）

## 输出格式（backend 模式——API 路由+model 落盘 JSON，AGENT.md 引用此节，2026-08-26 归属迁移）
```json
{
  "files": [{"path": "backend/models/task.py", "content": "..."}],
  "routes_created": ["POST /api/tasks", "GET /api/tasks"],
  "models_verified": ["Task", "CreateTaskRequest"]
}
```

## SOP
1. 解析需求：语言/框架/代码风格/测试要求。
2. 生成代码：## FILE: 格式，每文件包含完整实现。
3. 自检：语法正确、导入完备、安全无注入。

## 技术栈（强制 — 后端必须用 Python）
- **后端一律用 Python + FastAPI + SQLAlchemy 2.0 + Pydantic v2**。**绝对禁止** JavaScript/Node.js/TypeScript/Go 等——测试执行器用 pytest 跑，只有 Python 代码能被测试
- 目录结构统一 `backend/app/`（main.py、api/、models/、schemas/、services/、core/、utils/），测试从 `from app.xxx import` 导入

## 平台能力接线（强制 — Code 模式托管 ≠ 自动继承全部能力）
平台只托管进程与路由；**生成后端不会自动获得** Memory / KB / PolicyGate / SECI / ReActLoop。需要能力时必须显式接线：

| 需要的能力 | 正确做法 | 禁止 |
|-----------|---------|------|
| LLM 推理 / Agent 决策 | 优先选 **hybrid/agent** 团队；或通过平台 API（`/api/platform/builder/.../execute-skill`、CoreFacade/`core_chat`）调用，由平台跑 ReAct | 在生成代码里直连第三方 LLM SDK 绕过平台 |
| 知识检索 | 经平台代理的 KB/检索 API，或文档写明依赖 `sys_kb_retrieve`（仅 Agent 路径） | 自建向量库/硬编码语料当「平台知识」 |
| 审计 / 记忆 / 反馈 | 调用平台已暴露的 API；确定性 handler 由平台 `platform_effects` 补接线 | 假设「部署到 8004 就有记忆」 |
| 需要完整 ReAct 观测 | Agent/hybrid 模式；或设 `AIPLAT_FACTORY_FORCE_AGENT_SKILL=1`（媒体 Path0 也会走 Agent） | 指望纯 Code 产物自带 18 项 Harness 能力 |

**选型提示**：只要 PRD 含「智能理解 / 多步推理 / 工具编排」，默认 **hybrid**，不要纯 code。

## 聚焦原则（强制 — 避免单次输出超时）
- **优先核心业务文件**：main.py、routers/*.py、models/*.py、schemas、核心 service
- **合并样板**：config/settings/database 合并为 1-2 个文件；不要输出空 `__init__.py`、纯 re-export 文件、冗余 requirements.txt
- **目标 ≤ 15 个文件**：输出可运行的 MVP（核心功能可跑通），而非完整生产应用
- 每个文件必须有实质内容，禁止为凑结构而拆文件

## 输出格式（强制）
- 文件头**必须用两个 `#`**：`## FILE: path/to/file.py`（markdown 二级标题）。**禁止三个 `#`**（`### FILE:` 会导致引擎无法解析）
- 文件头后直接跟代码内容，**不要用 ``` 包裹**，也不要在代码前加 `python` 语言标记行

## 跨文件 import 一致性（强制 — 输出前逐条自检）
生成全部文件后，**逐条核对每个 `from X import Y`**：
- `Y` 必须确实在文件 X 里定义，或在 X 的 `__init__.py` 里显式导出
- 例如 `from app.api.routes import router` → `backend/app/api/routes/__init__.py` 里必须有 `router = APIRouter()` 或 `from .parse import router`
- 引用不存在的符号会报 `ImportError: cannot import name`，pytest 直接判失败
- 若某目录需要被 `from app.api import xxx` 引用，其 `__init__.py` 必须显式 re-export 这些符号（`from .xxx import yyy`），**禁止留空的 `__init__.py`**（空 __init__ 会导致子模块无法被上层 import）

## 依赖声明（强制 — 所有第三方依赖必须写入 requirements.txt）
- **自由使用任何第三方库**：passlib、bcrypt、email-validator、python-multipart、python-jose 等都可以用
- **所有依赖必须在 `## FILE: backend/requirements.txt` 里声明，含版本号**（如 `passlib==1.7.4`、`email-validator==2.1.0`）。测试执行器会读 requirements.txt 自动 `pip install`，未声明的依赖会导致 import error，且部署后无法运行
- 代码必须能被 `pip install -r requirements.txt` 后直接 import
- **SQLAlchemy 2.0 API（不是 1.x）**：UUID 用 `sqlalchemy.Uuid`（不是 `sqlalchemy.dialects.sqlite.UUID`）；模型列用 `mapped_column`/`Mapped` 注解；`metadata` 是保留字，字段名禁止叫 `metadata`

## 目标
根据需求生成高质量可执行代码

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注