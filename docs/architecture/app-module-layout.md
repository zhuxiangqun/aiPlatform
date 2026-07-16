# 业务应用模块目录规范 v1.0

## 适用范围

FDE、Builder、Workbench、Value、Learning、Prompt Management 等所有业务应用模块。

## 核心原则

> 每个业务应用模块有且仅有唯一的目录归属。模块的 REST API、业务逻辑、域名本体、Prompt 模板各自归入正确的架构层。

## 标准目录结构

```
{module_name}/
├── api/                    ← REST/GraphQL 端点定义
│   ├── __init__.py
│   ├── routers.py          ← @router.get / @router.post 等
│   └── schemas.py          ← Pydantic 请求/响应模型
├── service/                ← 业务逻辑（无 HTTP 依赖）
│   ├── __init__.py
│   └── {module}_service.py
├── domain/                 ← 域本体定义 + 种子数据
│   ├── {module}.yaml       ← 本体类定义
│   └── seed.json           ← 种子数据
├── prompts/                ← LLM prompt 模板（模块自管）
│   └── prompts.py
├── skills/                 ← 模块专用 Skill（SKILL.md 或 Python 类）
│   └── {skill_name}/
│       └── SKILL.md
└── agents/                 ← 模块专用 Agent 定义
    └── {agent_name}/
        └── AGENT.md
```

## 分层归属规则

| 文件类型 | 放在哪一层 | 目录路径 |
|---------|:---:|------|
| `@router.get/post` 端点定义 | **Platform** | `aiPlat-platform/apps/{module}/api/` |
| 无 HTTP 依赖的业务逻辑（Agent调用、状态管理） | **Core** | `aiPlat-core/core/apps/{module}/service/` |
| 域本体 YAML + 种子数据 | **Config** | `~/.aiplat/ontologies/` + `~/.aiplat/seed_data/` |
| LLM prompt 模板 | **Module self-managed** | `aiPlat-core/core/apps/{module}/prompts/` |
| 模块专用 Skill | **Core Engine** | `aiPlat-core/core/engine/skills/` 或模块自管 |
| 模块专用 Agent | **Workspace** | `~/.aiplat/agents/` |

## 注册机制

模块通过在 `aiPlat-platform/registry/apps.yaml` 中声明来注册自身：

```yaml
modules:
  fde:
    name: "FDE 现场交付引擎"
    description: "Field Deployment Engineer — 客户诊断与交付工作台"
    api_prefix: "/api/platform/apps/fde"
    api_module: "api.routers"
    service_module: "core.apps.fde.service"
    prompts_module: "core.apps.fde.prompts"
    domains: ["fde-delivery"]
    agents: ["fde_business_analyst", "fde_solution_architect", "fde_delivery_engineer", "fde_delivery_manager"]
    skills: ["customer_profile_creator", "domain_assessor", "field_assessment", "package_builder", "acceptance_checker", "poc_data_inject"]
```

Core 通过读取此注册表动态发现模块，而不是在代码中硬编码模块名称。

## 反模式（禁止）

| ❌ 禁止 | ✅ 应该 |
|--------|--------|
| 模块的 REST 端点定义在 `core/api/routers/{module}.py` | 放在 `platform/apps/{module}/api/routers.py` |
| 模块的 Prompt 模板注册在 `core/harness/utils/prompt_loader.py` 中 | 放在 `core/apps/{module}/prompts/`，由模块自行注册 |
| Harness 层代码硬编码 `module_name` 作为域标识 | 通过 `DomainRouter` 动态发现所有已注册域 |
| 模块之间的跨模块调用绕过 Facade | 通过注册表声明的公开接口调用 |

## 迁移优先级

当新模块首次创建时，遵循此规范。现有模块按以下优先级渐进迁移：

| 批次 | 模块 | 理由 |
|:---:|------|------|
| **星** | **FDE** | 改动最频繁，痛点最明确，作为迁移样板 |
| A | Builder（流水线/工作流） | 与 FDE 耦合最紧 |
| B | Workbench / Overview / Kanban | 用户工作台相关 |
| C | Value / Roles / Safety | 价值评估与权限 |
| D | Learning / Finetune | 学习训练相关 |
| E | Prompt 管理 / Evaluations | Prompt 工具链 |
| F | 其他（code_intel / browser_test 等） | 低频变更模块 |

## 验收标准

```bash
# core/api/routers/ 下无应用模块路由器
ls aiPlat-core/core/api/routers/fde*.py 2>/dev/null
# → 空（或仅含重定向 stub）

# Harness 层无业务模块硬编码
grep -rn "fde-\|builder\|workbench" aiPlat-core/core/harness/ --include='*.py'
# → 空

# 新模块通过 apps.yaml 注册
python3 -c "import yaml; print(yaml.safe_load(open('aiPlat-platform/registry/apps.yaml')))"
# → 包含 fde 模块条目
```

## 参考

- 四层架构定义：`docs/index.md` §Layer 0-3
- 层边界标准：`docs/architecture/boundary-standard.md`
- 系统架构契约：`docs/architecture/system-architecture-contract.md`
- 内容归属规范：`CLAUDE.md` §8
- 核心修改自检规则：`CLAUDE.md` §8
