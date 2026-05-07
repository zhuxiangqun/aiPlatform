---
purpose: aiPlat-management 项目级 AI 编程规约（适用于 Claude Code / Cursor / 其他 Agent）
scope: management + frontend
language: zh-CN
---

# aiPlat-management AI 编程规约（管理端 + 前端）

本文件用于约束 AI Agent 在 aiPlat-management 仓库内的行为，目标是：
- 降低返工（先问清楚再改）
- 控制 diff 外溢（只改需求相关）
- 前端改动必须可构建（`npm run build`）
- 维持模块边界（尤其是 services/ui 的统一出口）

---

## 0. 优先级（从高到低）
1. 正确性与可验证性（build/test 通过）
2. 最小改动面（Surgical Changes）
3. 简单性（Simplicity First）
4. 一致性（风格/组件规范/目录约定）

---

## 1) Think Before Coding：不确定先问
出现任一情况，必须先澄清：
- UI/交互存在多种实现方式（例如 toast/弹窗/页面提示）
- API 返回结构不明确（字段名、错误 envelope、分页参数）
- 涉及权限/审批/租户隔离
- 涉及重构 services、stores、路由结构

输出澄清时请给：
- 歧义点
- 2~3 个可选方案
- 推荐默认方案

### 1.1 代码优先于设计文档（强制）
设计文档（`docs/`）描述目标状态，代码才是当前真实状态。两者冲突时以代码为准，设计文档标注"已过期/已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止仅凭记忆或上次审计的印象做判断，每次结论必须附带代码搜索证据（命中文件路径+行号）。

---

## 2) Simplicity First：最小实现
- 不要为了“更通用”引入新抽象层（除非需求明确）
- 不要引入新依赖（npm 包）除非必要且得到确认
- 不要“顺手升级”库版本或改大量配置

---

## 3) Surgical Changes：手术式改动（强制）
- 不要顺手改无关组件、样式、格式化
- 不要重命名文件/变量只为“更优雅”
- 只清理“你引入的” unused（import/变量）
- 发现无关问题：指出即可，不要顺手修

---

## 4) Goal-Driven Execution：以验收标准闭环
对非 trivial 任务必须：
1. 简短计划（3~6 步）
2. 每步附 verify
3. 最终至少跑一次：
   - 前端：`npm run build`

---

## 5) 项目特定：前端目录与依赖边界（必须遵守）

### 5.1 services 统一出口（避免枢纽文件被直连）
在 `frontend/src` 内：
- **禁止**直接从 `services/coreApi.ts` 引用（会形成高 in-degree 枢纽）
- 统一从 `services/index.ts` 引用 API 与 types：  
  `import { workspaceAgentApi } from '../services'`

### 5.2 UI 统一出口
- UI 相关（toast / gateError 等）优先从 `components/ui` 出口引入
- 避免散落在 `utils/*` 形成“非聚合点高枢纽”

### 5.3 配置驱动：UI 组件不按 artifact key 做特殊分支（来自 core 设计原则延展）

流水线产物的 key（如 `architecture`、`test_report`、`code`）是 `PipelineStageConfig.output_artifact` 配置出来的值，不同团队的流水线可能使用不同的 key。

| 禁止 | 应使用 |
|------|--------|
| `key === 'test_report'` 来判断是否需要特殊显示 | 检查值本身的结构，如 `'recommendation' in val` |
| `session.phase.includes('test_report')` 写死阶段名 | 检查 phase 字符串模式而非硬编码业务阶段名 |
| `visible.findIndex` 推断当前执行阶段 | `raw['_current_stage_idx']` —— 引擎维护的执行指针 |

**原则**：UI 对 pipeline state 的判断逻辑不应依赖"某个特定团队的 artifact key 叫什么"。需特殊处理时，依据 artifact 的**结构特征**（有没有 `recommendation` 字段、有没有 `pass_rate` 字段），而非 **key 的名称**。

### 5.4 Management 层不应包含业务逻辑（来自 `docs/architecture-boundary.md`）

Management 是横切管理平面，职责是**聚合展示、告警、诊断、转发**。

- Management **不应包含**：业务逻辑实现、直接操作 Manager 类、与业务强耦合的数据存储操作
- 需要新数据时：先在目标业务层（core/infra）增加管理 API，management 通过 HTTP adapter/aggregator 调用并聚合
- Management 自身可拥有"管理面元数据"存储（告警规则、配置版本、审计日志），但不得替代业务层状态存储

**设计文档依据**：
- `docs/architecture-boundary.md` 二「aiPlat-management 层不应包含：业务逻辑实现」
- `docs/architecture/system-architecture-contract.md` 1「Management 为横切管理平面，不参与业务调用链」

---

## 6) 输出要求（每次交付必须包含）
- 改动摘要（改了哪些文件）
- 你如何验证（例如 build 通过）
- 若做了重构：说明为什么能降低耦合/减少枢纽依赖

