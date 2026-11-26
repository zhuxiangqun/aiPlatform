---
doc_type: Index
status: active
authority: supporting
doc_id: README_AE2958
last_reviewed: 2026-11-26
---
# 标准索引

## 知识体系标准

- [v4.3.1](./knowledge-system/v4.3.1/README.md) — 已批准，2027-01-01 生效。

## 子系统标准包（已批准 · 结构对齐 KS v4.3.1）

> 正文 + 规范性附录 + `schemas/` + 批准 ADR + 实施计划。  
> **标准包已批准**（2026-11-26；**2026-12-01 生效**）。  
> **标准批准 ≠ 实现 certified**；`exists` / 正式 `core_ready` ≠ `certified`。

| 标准包 | 入口 | 批准 ADR | schemas | 状态 |
|---|---|---|---|---|
| 评测系统 v1.0 | [evaluation-system/v1.0](./evaluation-system/v1.0/README.md) | [ADR](./evaluation-system/v1.0/ADR-EVAL-SYS-v1.0-2026-11-26.md) | [schemas](./evaluation-system/v1.0/schemas/README.md) | active · 2026-12-01 生效 |
| 外援互通 v1.0 | [external-interop/v1.0](./external-interop/v1.0/README.md) | [ADR](./external-interop/v1.0/ADR-EXT-INTEROP-v1.0-2026-11-26.md) | [schemas](./external-interop/v1.0/schemas/README.md) | active · 2026-12-01 生效 |
| FDE 系统 v1.0 | [fde-system/v1.0](./fde-system/v1.0/README.md) | [ADR](./fde-system/v1.0/ADR-FDE-SYS-v1.0-2026-11-26.md) | [schemas](./fde-system/v1.0/schemas/README.md) | active · 2026-12-01 生效 |

诚实边界摘要：

- **评测**：无人工标签不宣称 accuracy；标准批准 ≠ certified；
- **外援**：导入可用 ≠ L2；标准批准 ≠ certified；
- **FDE**：签收唯一；评测绿 ≠ 客户签收；compose 长驻另批；标准批准 ≠ certified。

## 跨层强制规范（已批准）

> 版本以各文件 frontmatter `version` 为准（当前多为 `1.0`）。  
> 目录版式对齐 `knowledge-system/<semver>/` 列为后续；本批不物理迁目录以免断链。

| 规范 | 范围 |
|---|---|
| [app session_id / conversation_key](./规范-app-session_id与conversation_key.md) | aiPlat-app channels/sessions |
| [core run/trace/request ID](./规范-core-run_id-trace_id-request_id.md) | platform + core + management |
| [platform 鉴权与身份透传](./规范-platform-鉴权与身份透传.md) | platform → app/core/management |
| [前端架构与工程](./规范-前端架构与工程.md) | management/frontend 与所有前端 |
| [功能开关与配置](./规范-功能开关与配置.md) | 全部仓库 |
| [命名](./规范-命名.md) | 全部代码 |
| [性能](./规范-性能.md) | 全部代码 |
| [数据与数据库](./规范-数据与数据库.md) | 全部仓库数据层 |
| [独立多租户](./规范-独立多租户.md) | 全部仓库 |
| [错误处理](./规范-错误处理.md) | 全部代码 |
