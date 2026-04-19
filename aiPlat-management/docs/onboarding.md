# 初始化向导（Onboarding）

目的：在一个页面内完成“系统可用”的最小闭环：

1. 配置模型 Provider/API Key（落到 core 的 Adapter 配置并持久化）
2. 检查 infra/core/platform/app 全链路健康
3. 触发一次生产级 E2E smoke（可观测/可验证）
4. （增强）设置全局默认 LLM 路由（default adapter/model，需审批）
5. （增强）初始化默认 tenant/policies（需审批）
6. （增强）密钥存储状态提示（AIPLAT_SECRET_KEY）

## 入口

管理台左侧菜单：**初始化向导**

路由：`/onboarding`

## Step 1：配置模型 Adapter

页面会调用 management API：

- `POST /api/onboarding/llm-adapter`

该接口会转调 core：

- `POST /api/core/adapters`（创建 adapter）
- `POST /api/core/adapters/{adapter_id}/models`（可选：添加模型）
- `POST /api/core/adapters/{adapter_id}/test`（连通性测试）

并将 adapter 配置持久化到 core 的 ExecutionStore（SQLite）。

## Step 2：检查全链路健康

页面会调用：

- `GET /api/diagnostics/health/all`

返回 `infra/core/platform/app` 的整体健康状态与组件细节。

## Step 3：运行 E2E Smoke

页面会调用：

- `POST /api/diagnostics/e2e/smoke`

该 smoke 的产物会落到 core 的 Jobs/JobRuns、Audit、Diagnostics（Traces/Runs/Syscalls）等面板中。

## 增强：设为默认路由（全局，需审批）

页面会调用 management API：

- `POST /api/onboarding/default-llm`

该接口转调 core：

- `POST /api/core/onboarding/default-llm`

写入 core 的 `global_settings(key="default_llm")`，并被 core 的 model_injection 在运行时读取，用于选择默认 adapter/model。

如返回 `approval_required`，请到管理台 `Core → Approvals` 批准后，将 `approval_request_id` 填回向导再次提交。

## 增强：初始化默认 tenant/policies（需审批）

页面会调用：

- `POST /api/onboarding/init-tenant`

该接口转调 core：

- `POST /api/core/onboarding/init-tenant`

会创建（或更新）`tenant_id=default`，并写入一份最小可用的 tenant policy（PolicyGate 可识别）。

## 增强：密钥安全存储（AIPLAT_SECRET_KEY）

当配置了 `AIPLAT_SECRET_KEY`（Fernet key）后，core 会将 adapter 的 `api_key` **加密存储**在 ExecutionStore。
向导会展示当前是否已配置该环境变量，并给出生成示例。

## 常见问题

### 1) API Key 会不会明文存储？

当前 MVP 会把 api_key 持久化到 core 的 SQLite（ExecutionStore adapters 表）。如果你希望做加密/脱敏或接入 KMS/Secret Manager，需要再加一层 secrets 抽象（后续可做）。

### 2) “默认模型/默认 adapter”怎么选？

当前 MVP 只负责写入 Adapter 配置与可用性验证；默认路由策略仍由现有的 model injection / policies 决定。下一步可以在向导里增加“设为默认”与“按 tenant 生效”的策略配置。
