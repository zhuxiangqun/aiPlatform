---
title: "aiPlat 安全与治理白皮书"
volume_id: security-governance
type: whitepaper-volume
status: generated
generated_at: "2026-10-15T03:54:35Z"
audience: "CISO、合规、风控"
core_question: "如何可信可控？"
priority: P0
source_status: ready
suite: docs/whitepaper/whitepaper-suite.yaml
suite_sha256: "0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30"
caps_sha256: "6cd3efc3f065537af0d014202c57bc0078568117cf53195cda40bb079a476e3c"
scores_sha256: "96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687"
language: zh-CN
---

<!-- volume_stamp id=security-governance suite_sha256=0907c52c20c69036b0d8cc541668dabb4d8811d1109716aa545cf27a8ff56a30 caps_sha256=6cd3efc3f065537af0d014202c57bc0078568117cf53195cda40bb079a476e3c scores_sha256=96d06b3ea6cd57e5d99085afc78c7877694e8d77b24575577d1537e20a46e687 -->

# aiPlat 安全与治理白皮书

> **可再生成分卷** · 权威源见下文清单 · 勿手改能力数/评分/ROI  
> 体系：[`../WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md) · 清单：[`../whitepaper-suite.yaml`](../whitepaper-suite.yaml)  
> 重生成：`bash scripts/sync_whitepapers.sh` 或 `python3 scripts/generate_whitepaper_volumes.py`

## 0. 卷册元信息

| 字段 | 值 |
|------|-----|
| 卷 ID | `security-governance` |
| 受众 | CISO、合规、风控 |
| 核心问题 | 如何可信可控？ |
| 优先级 | P0 |
| 材料完备度（suite） | `ready` |
| 生成时间 (UTC) | `2026-10-15T03:54:35Z` |
| CAPABILITIES sha256 | `6cd3efc3f065…` |
| assessment-scores sha256 | `96d06b3ea6cd…` |

## 1. 本卷论证目标

本卷面向 **CISO、合规、风控**，围绕「**如何可信可控？**」组织既有权威文档。结论与数字以源文件为准；本卷负责受众叙事框架与可读编排。

## 2. 权威源清单（存在性已校验）

### 2.1 Canonical

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/security/security-architecture.md`](../security/security-architecture.md) | 安全架构 | ✅ |
| [`docs/compliance/eu-ai-act-assessment.md`](../compliance/eu-ai-act-assessment.md) | 合规评估 | ✅ |
| [`docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md`](../aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性定级（L 级，可验证） | ✅ |


### 2.2 Supporting

| 路径 | 角色 | 存在 |
|------|------|:----:|
| [`docs/framework/aiplat-autonomy-framework.md`](../framework/aiplat-autonomy-framework.md) | 自主性框架 | ✅ |
| [`docs/framework/aiplat-complete-assessment.md`](../framework/aiplat-complete-assessment.md) | 完整评估叙述 | ✅ |
| [`docs/framework/assessment-scores.json`](../framework/assessment-scores.json) | 评分机器源 | ✅ |
| [`docs/framework/scoring-detail.md`](../framework/scoring-detail.md) | 评分细则 | ✅ |
| [`docs/framework/verification-protocol.md`](../framework/verification-protocol.md) | 外部验证协议 | ✅ |


## 3. 正文编排（节选权威源）

### 3.0 治理与安全材料

治理卷材料已厚，本卷 suite 状态为 ready，保留以下权威源：

- 评分戳：[`docs/framework/assessment-scores.json`](../framework/assessment-scores.json)
- 安全架构：[`docs/security/security-architecture.md`](../security/security-architecture.md)
- Gate 与安全能力：[`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) 中 Gate / 安全节
- L 级 ADR：[`docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md`](../aiplat-l4-autonomy-assessment-v1.0.0.md)

> 治理卷不新增示意案例，不引用未授权客户数据。

### 3.1 权威评分戳

> generated_at=`2026-07-08T09:51:09` · spec=`1.0.0`

| 框架 | 结果 |
|------|------|
| 8轴自主性成熟度 | **L5** (5.0) |
| 工程落地评估(58项) | **100.0%** |
| 三层企业评估(~110项) | _(见 JSON)_ |

### 3.2 安全架构（节选）

### aiPlat 安全架构 — 纵深防御模型

> 基于零信任原则 (never trust, always verify) 的六层防御体系。

#### 防御层级

| 层 | 名称 | 机制 | 实现 |
|:--:|:---|:---|:---|
| **L1** | 网络边界 | API 网关, TLS, CORS | Management API Gateway (port 8000) |
| **L2** | 身份认证 | JWT Bearer Token | 单用户模式可选, 多租户强制 |
| **L3** | 权限控制 | RBAC + PBAC | PolicyGate (deny-by-default) + Permission Check |
| **L4** | 操作审批 | HITL Approval | ApprovalGate + 审批申请/批准/拒绝 |
| **L5** | 执行沙箱 | Isolated Subprocess | SandboxGate — 工具执行隔离 |
| **L6** | 审计追溯 | SHA-256 Chain | Audit Mixin — 回查每条操作 |

#### 零信任原则落地

| 原则 | aiPlat 实现 |
|:---|:---|
| 持续验证 | PolicyGate 每次 syscall 前检查权限 |
| 最小权限 | deny-by-default 策略, 必须显式授权 |
| 微分段 | Skill/Tool/Agent 权限独立, 互不继承 |
| 假定被破 | SandboxGate 隔离, 工具执行不在主进程 |
| 全程审计 | SHA-256 hash chain, 每次操作不可否认 |

#### 安全边界

```
Internet → Management Gateway (唯一入口)
              ↓ PolicyGate (RBAC 检查)
              ↓ API 路由
              ├── Core (Agent Engine + Pipeline)
              │     ↓ ApprovalGate (高危操作审批)
              │     ↓ SandboxGate (工具执行隔离)
              ├── Infra (Model Management + LLM)
              │     ↓ SecretsManager (AES-256-GCM 密钥)
              └── Platform (Knowledge Base + Builder)
                    ↓ Audit Log (SHA-256 chain)
```

#### GitHub Branch Protection Rules (Recommended)

```yaml
### Apply in GitHub → Settings → Branches → Add rule
branches: [main]
rules:
  - require_pull_request: true
    required_approvals: 1
    dismiss_stale_reviews: true
  - require_status_checks: true
    contexts: ["Lint & Type Check", "Test (pytest)", "L5 Depth Tests"]
  - require_conversation_resolution: true
  - require_code_owner_review: false  # no CODEOWNERS file
  - enforce_admins: true
```

#### 零信任验证清单

| # | 层级 | 验证方式 | 状态 |
|:--:|:---|:---|:--:|
| L1 | 网络边界 | `curl http://localhost:8000/health` — 只有 mgmt 端口暴露 | ✅ |
| L2 | 身份认证 | JWT 无效时返回 401 — `scripts/security-attack-sim.py` S1 验证 | ✅ |
| L3 | 权限控制 | PolicyGate deny-by-default — 未授权 tool 调用被拒绝 | ✅ |
| L4 | 操作审批 | ApprovalGate 高危操作需审批 — change_control.py 验证 | ✅ |
| L5 | 执行沙箱 | SandboxGate 隔离 — 工具执行不在主进程 | ✅ |
| L6 | 审计追溯 | SHA-256 chain 可验证 — `audit_mixin.py verify_integrity()` | ✅ |

#### FDE 部署验证报告

> 外部人员按 deploy-guide.md 从头部署并计时。

| 步骤 | 内容 | 耗时 | 状态 |
|:--:|------|:--:|:--:|
| 1 | git clone + pip install | ~3min | ✅ |
| 2 | 配置 API Key | ~1min | ✅ |
| 3 | `./start.sh` | ~2min | ✅ |
| 4 | `curl /health` 验证 | ~10s | ✅ |
| 5 | 运行第一个 Agent | ~1min | ✅ |
| 6 | `verify-l4-pyramid.sh` 全量验证 | ~10s | ✅ |
| 7 | `verify-deploy.sh` 部署验证 | ~30s | ✅ |
| **总计** | | **~8 分钟** | **从头部署到全量验证通过** |

##### FDE 差距

| 项 | 状态 | 说明 |
|:---|:--:|:---|
| 新手无障碍部署 | ✅ | 8分钟从零到验证 |
| 生产部署就绪 | ✅ | Helm + ArgoCD + 回滚 |
| 外部人验证 | 需要 | 邀请未接触过 aiPlat 的人做盲测 |
| 大规模部署 | 待验证 | 需要 K8s 集群 + 100 并发压力测试 |


### 3.3 CAPABILITIES：安全与治理 / Gate

## 七、安全与治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| build_architecture_health_report | `core/harness/observability/architecture_health.py` | ✅ | 自动同步 | 已合入 |
| truncate_repetition | `core/harness/utils/repetition_guard.py` | ✅ | 自动同步 | 已合入 |
| arch_guard_b84 | `scripts/architecture_guard.sh` | ✅ | 自动同步 | 已合入 |
| PromptAuditRules | `core/harness/audit/prompt_audit_rules.py` | ✅ | 提示词审计规则 | 已合入 |
| coupling_metrics | `scripts/coupling_metrics.py` + `scripts/baselines/coupling_baseline.json` | ✅ | 耦合度量基线：AST import-degree → avg_degree/max_degree(non-agg)/top-20 + baseline ratchet（roadmap §0.2） | 待合入 |
| §94b BOUNDARY 覆盖 | `scripts/architecture_guard.sh` | ✅ | harness 48 一级子目录 BOUNDARY.yaml 全量覆盖检查（roadmap §0.3，缺则 FAIL） | 待合入 |
| ManagedPolicy | `aiPlat-platform/auth/schemas_policy.py` | ✅ | 企业远程托管策略 (managed 键本地不可覆盖, P1-A6) | 已合入 |
| PIIDetector | `harness/infrastructure/pii_detector.py` | ✅ | 自动同步 | 已合入 |
| prompt_auditor | harness/audit/prompt_auditor.py | ✅ | 自动同步 | 已合入 |
| semantic_gate | harness/infrastructure/gates/semantic_gate.py | ✅ | 自动同步 | 已合入 |
| cross_validation_gate | harness/infrastructure/gates/cross_validation_gate.py | ✅ | 自动同步 | 已合入 |
| completion_gate | harness/infrastructure/gates/completion_gate.py | ✅ | 自动同步 | 已合入 |
| audit_trail_gate | harness/infrastructure/gates/audit_trail_gate.py | ✅ | 自动同步 | 已合入 |
| agent_manager | management/agent_manager.py | ✅ | 自动同步 | 已合入 |
| skill_manager | management/skill_manager.py | ✅ | 自动同步 | 已合入 |
| workflow_manager | management/workflow_manager.py | ✅ | 自动同步 | 已合入 |
| DataFormStage | `aiPlat-management/frontend/src/components/AppStages/DataFormStage.tsx` | ✅ | 自动同步 | 已合入 |
| DataTableStage | `aiPlat-management/frontend/src/components/AppStages/DataTableStage.tsx` | ✅ | 自动同步 | 已合入 |
| FileUploadStage | `aiPlat-management/frontend/src/components/AppStages/FileUploadStage.tsx` | ✅ | 自动同步 | 已合入 |
| ProgressPoller | `aiPlat-management/frontend/src/components/AppStages/ProgressPoller.tsx` | ✅ | 自动同步 | 已合入 |
| ResultDashboard | `aiPlat-management/frontend/src/components/AppStages/ResultDashboard.tsx` | ✅ | 自动同步 | 已合入 |
| APP_STAGE_REGISTRY | `aiPlat-management/frontend/src/components/AppStages/index.ts` | ✅ | AppStage 组件注册表：8 种组件映射替代 AppPage 硬编码分发（2026-08-25，新增组件无需改 AppPage） | 待合入 |
| MarkdownViewerStage | `aiPlat-management/frontend/src/components/AppStages/MarkdownViewerStage.tsx` | ✅ | 文本/报告/分析产物 markdown 展示组件（agent 模式新增，2026-08-25） | 待合入 |
| StatCardsStage | `aiPlat-management/frontend/src/components/AppStages/StatCardsStage.tsx` | ✅ | KPI 指标卡片组件（agent 模式新增，2026-08-25） | 待合入 |
| KanbanBoardStage | `aiPlat-management/frontend/src/components/AppStages/KanbanBoardStage.tsx` | ✅ | 看板列状态流转组件（agent 模式新增，2026-08-25） | 待合入 |
| KnowledgeFactoryPage | `aiPlat-management/frontend/src/pages/KnowledgeFactory/KnowledgeFactoryPage.tsx` | ✅ | 自动同步 | 已合入 |
| AppLayout | `aiPlat-management/frontend/src/components/layout/AppLayout.tsx` | ✅ | 自动同步 | 已合入 |
| SystemOverview | `aiPlat-management/frontend/src/pages/SystemOverview/SystemOverview.tsx` | ✅ | 自动同步 | 已合入 |
| ValueDashboard | `aiPlat-management/frontend/src/pages/ValueCenter/ValueDashboard.tsx` | ✅ | 自动同步 | 已合入 |
| ExecutionViewer | `aiPlat-management/frontend/src/components/ExecutionViewer/ExecutionViewer.tsx` | ✅ | 运行图/事件回放；进行中可 `runApi.cancel`；完成后「副作用恢复指引」→ `POST /runs/{id}/undo` 的可解释 409（file checkpoints / 域回滚），链到 `/core/checkpoints` | 已合入 |
| 运行回滚可解释指引 | `harness/execution/run_rollback_guidance.py` + `POST /runs/{id}/undo` | ✅ | 完成后无通用 undo；返回 alternatives + checkpoint 预览；生成物不适用（平台横切） | 已合入 |
| Ontology 种子离线就绪 | `scripts/check_ontology_seeds_offline.py` + `ops_harness_ready_check.sh` | ✅ | 工作区 `workspace_seeds/ontologies/*.yaml` parse 门禁；可选 copy→`~/.aiplat/ontologies`；Graph ingest 仍需 runtime；生成物不适用 | 已合入 |
| 发布习惯门：ops harness ready | `scripts/ops_harness_ready_check.sh` + `.github/workflows/aiplat-contracts-guard.yml`（Ops harness ready）+ Governance「Gold match-only」CTA | ✅ | CI 强制：gold `--match-only` + ontology offline YAML + IDE capture hooks；与 Governance 值班板 `release_habit` / 一键 CTA 同门；install-seeds 最佳努力；生成物不适用（平台横切发布门禁） | 已合入 |
| WorkflowsPage | `aiPlat-management/frontend/src/pages/Core/Workflows/WorkflowsPage.tsx` | ✅ | 自动同步 | 已合入 |
| Credentials | `aiPlat-management/frontend/src/pages/Core/Credentials/Credentials.tsx` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| PolicyGate | harness/infrastructure/gates/policy_gate.py | ✅ | 统一权限检查 + 架构边界实时拦截 | 已合入 |
| resolve_policy_fail_mode | harness/infrastructure/gates/policy_gate.py | ✅ | 权限 infra 降级策略 open/ask/closed（默认 open；生产 ask 灰度；CRITICAL_MODE 可 closed；非关键固定 open+审计） | 已合入 |
| apply_architecture_profile | core/schemas_builder.py | ✅ | 阶段 architecture_profile（oneshot/react_tools/plan_execute/reflect_loop）覆盖 backend+agent_type；upgrade_policy=off\|signals\|aggressive；code_split 后端编码试点 plan_execute；生成物适用（team YAML） | 已合入 |
| ApprovalGate | harness/infrastructure/approval/manager.py | ✅ | approve/deny/pending，双门禁 | 已合入 |
| Prompt 注入防护 | harness/syscalls/llm.py:125 | ✅ | 6条正则+特殊token过滤+覆盖防护指令 | 已合入 |
| 记忆投毒防御 | harness/memory/base.py:39 | ✅ | source_tag/trust_weight/provenance | 已合入 |
| PII 脱敏（全量覆盖） | kb/service.py` → `_mask_pii()` + `services/pii_detector.py | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，全部 6 条入库路径已覆盖 | 已合入 |
| CodeAuditor | harness/security/code_auditor.py | ✅ | 注入/XSS/CSRF/认证/授权检查 | 已合入 |
| RBAC 多租户 | [概念] | ✅ | platform 层 — 架构决策；tenant + actor + scopes 三级隔离 | 待核实 |
| 架构守卫 190 规则 + AST 未定义符号守卫 | [配置] | ✅ | §1-§76 自动扫描 + guard_undefined_names.py（第 17 维"未定义变量"升级为 AST 级，2026-08-19） | 已合入 |
| 190 条 CI 检查 + AST 守卫 | scripts/architecture_guard.sh | ✅ | 零依赖 grep 扫描 + AST 级未定义符号检查 | 已合入 |
| 前端 API 契约检查 | ../../scripts/guard_frontend.py | ✅ | TS fetch ↔ Python data.get 一致性 | 已合入 |
| PII 检测脱敏 | services/pii_detector.py | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，Presidio+正则双引擎 | 已合入 |
| 合规报告 SOC2/ISO27001 | management/compliance_checks.py | ✅ | 12检查 + SOC2 CC/ISO27001 A映射 + 自动报告生成 | 已合入 |
| 架构契约上下文注入 | harness/utils/prompt_loader.py` → `harness/assembly/prompt_assembler.py | ✅ | coding-contract 模板在代码生成前注入 Agent system prompt（6条核心约束） | 已合入 |
| ContextAssembler 上下文组装 | harness/assembly/context_assembler.py | ✅ | PromptContext + TokenBudgetManager：token 预算、压缩阈值、来源归因 | 已合入 |
| Compaction Prompt 压缩模板 | harness/assembly/compaction_prompt.py | ✅ | ReActLoop 可配置压缩 prompt（`get_compaction_prompt` / `AIPLAT_COMPACTION_PROMPT`） | 已合入 |
| 审计日志防篡改 | ../../aiPlat-platform/governance/audit/logger.py | ✅ | SHA-256 链式哈希 + verify_integrity()；生成物不适用（理由：平台横切审计，生成应用由平台侧强制执行） | 已合入 |
| 对象级权限 | policy/object_permission.py | ✅ | 每实体/每动作/每角色细粒度控制，支持本体继承 | 已合入 |
| 字段级安全 | policy/field_level_security.py | ✅ | 单元/字段级数据可见性，Palantir CBAC对齐 | 已合入 |
| 技能签名验证 | security/skill_signature_gate.py | ✅ | Ed25519 签名校验 + 可信公钥注册表 | 已合入 |
| SecretsManager | harness/infrastructure/secrets_manager.py | ✅ | AES-256-GCM 加密存储 + 审计日志 | 已合入 |
| Ed25519 签名 | harness/infrastructure/crypto/signature.py | ✅ | 密钥生成/签名/验签，技能/制品完整性保护 | 已合入 |
| CryptoSecretBox | harness/infrastructure/crypto/secretbox.py | ✅ | 对称加密盒，运行时密钥保护 | 已合入 |
| DI 容器 | harness/infrastructure/di/__init__.py | ✅ | 依赖注入容器，12/18服务调用已转换 | 已合入 |
| Config Settings | harness/infrastructure/config/settings.py | ✅ | 层级配置管理 + 环境变量覆盖 | 已合入 |
| SSO/OIDC 集成 | ../../aiPlat-platform/auth/identity_provider.py | ✅ | Keycloak/Azure AD/Okta，discovery/jwks映射 + login/callback/token API | 已合入 |
| CrisisDetector | harness/security/crisis_detector.py | ✅ | 自伤/暴力/危急三級检测，WARN/BLOCK/SILENT 模式 | 已合入 |
| CrisisGate | harness/security/crisis_gate.py | ✅ | syscall 边界危机拦截，ALLOW/WARN/FLAG/BLOCK/ESCALATE | 已合入 |
| EmotionTracker | harness/security/emotion_tracker.py | ✅ | 跨会话情绪弧追踪 + 过度依赖检测 | 已合入 |
| ApprovalGate (危险命令) | harness/infrastructure/gates/approval_gate.py | ✅ | 25规则危险操作检测，CRITICAL/HIGH/MEDIUM/LOW 四级，集成 PolicyGate | 已合入 |
| SkillsGuard (威胁扫描) | harness/infrastructure/gates/skills_guard.py | ✅ | 78威胁模式，skill注册前安全扫描，11类别全覆盖 | 已合入 |

---


## 十二、Gate 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| parse_app_page_payload | `core/harness/execution/app_page_skill_inject.py` | ✅ | 自动同步 | 已合入 |
| skill_routing_context_block | `core/harness/execution/app_page_skill_inject.py` | ✅ | 自动同步 | 已合入 |
| extract_ui_bindings | `core/harness/execution/app_page_skill_inject.py` | ✅ | 自动同步 | 已合入 |
| extract_skill_routing | `core/harness/execution/app_page_skill_inject.py` | ✅ | 自动同步 | 已合入 |
| infer_emotion_from_energy | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| transcribe_speech_asr | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| detect_speech_language | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| enrich_keyframes_with_captions | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| describe_frame_image | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| merge_vad_segments | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| pad_keyframes_for_density | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| infer_duration_hint | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| coerce_media_invoke_params | `core/harness/media_ops.py` | ✅ | 自动同步 | 已合入 |
| suggest_platform_media_skill | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| resolve_media_handler_name | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| is_prompt_only_skill_name | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| resolve_platform_media_skill | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| list_platform_media_skill_names | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| HANDLERS | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| execute_media_skill | `core/harness/media_skill_handlers.py` | ✅ | 自动同步 | 已合入 |
| evaluate_result_asserts | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| enrich_media_invoke_from_asserts | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| classify_execution | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| check_file_rules | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| is_blocked_url | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| run_platform_check | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| run_true_test_case | `core/harness/execution/true_test_runtime.py` | ✅ | 自动同步 | 已合入 |
| find_structured_requirements | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| collect_upstream_blobs | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| extract_real_http_routes | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| resolve_architecture_mode | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| pick_routing_blob | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| compare_bloat | `core/harness/execution/factory_bloat_metrics.py` | ✅ | 自动同步 | 已合入 |
| write_bloat_metrics | `core/harness/execution/factory_bloat_metrics.py` | ✅ | 自动同步 | 已合入 |
| resolve_coding_intensity | `core/harness/utils/coding_intensity.py` | ✅ | 自动同步 | 已合入 |
| build_coding_policy_block | `core/harness/utils/coding_intensity.py` | ✅ | 自动同步 | 已合入 |
| normalize_coding_intensity | `core/harness/utils/coding_intensity.py` | ✅ | 自动同步 | 已合入 |
| infer_followups | `core/harness/utils/output_style.py` | ✅ | 自动同步 | 已合入 |
| estimate_reply_tokens | `core/harness/utils/output_style.py` | ✅ | 自动同步 | 已合入 |
| record_digest_view | `core/harness/team_digest.py` | ✅ | 自动同步 | 已合入 |
| build_team_digest | `core/harness/team_digest.py` | ✅ | 自动同步 | 已合入 |
| apply_stage_skill_subscription | `core/harness/utils/team_skill_subscription.py` | ✅ | 自动同步 | 已合入 |
| filter_skills_by_subscription | `core/harness/utils/team_skill_subscription.py` | ✅ | 自动同步 | 已合入 |
| list_local_learnings | `core/harness/team_friction.py` | ✅ | 自动同步 | 已合入 |
| confirm_friction_share | `core/harness/team_friction.py` | ✅ | 自动同步 | 已合入 |
| note_regenerate | `core/harness/team_friction.py` | ✅ | 自动同步 | 已合入 |
| record_friction_event | `core/harness/team_friction.py` | ✅ | 自动同步 | 已合入 |
| resolve_culture_enabled | `core/harness/utils/team_culture.py` | ✅ | 自动同步 | 已合入 |
| inject_team_culture | `core/harness/utils/team_culture.py` | ✅ | 自动同步 | 已合入 |
| compose_prose_overlays | `core/harness/utils/team_culture.py` | ✅ | 自动同步 | 已合入 |
| build_culture_overlay | `core/harness/utils/team_culture.py` | ✅ | 自动同步 | 已合入 |
| resolve_writing_profile | `core/harness/utils/writing_profile.py` | ✅ | 简洁交接文风 profile（STE 精神，非全量词表） | 已合入 |
| build_writing_overlay | `core/harness/utils/writing_profile.py` | ✅ | 工厂对话 ephemeral overlay；序 hard→Culture→style→writing | 已合入 |
| apply_concise_prose | `core/harness/utils/writing_profile.py` | ✅ | 确定性精简；保护代码符号/报错原文 | 已合入 |
| apply_error_message | `core/harness/utils/writing_profile.py` | ✅ | 运维/算子错误文案；pipeline_engine 接线 | 已合入 |
| apply_handoff_fields | `core/harness/utils/writing_profile.py` | ✅ | handoff summary/verify/next；不改 artifact_ref | 已合入 |
| apply_project_writing_meta | `core/harness/utils/writing_profile.py` | ✅ | 项目 metadata 持久化 writing_profile | 已合入 |
| build_run_structure_diagram | `core/harness/execution/run_structure_diagram.py` | ✅ | 确定性 stage Mermaid（tool_result；无 LLM 编节点） | 已合入 |
| write_structure_diagram | `core/harness/execution/run_structure_diagram.py` | ✅ | run 结束写入 state[_structure_diagram] | 已合入 |
| stages_to_mermaid | `core/harness/execution/run_structure_diagram.py` | ✅ | depends_on + artifact 边 → flowchart | 已合入 |
| build_run_evidence_page | `core/harness/execution/run_evidence_page.py` | ✅ | 模板+JSON 可丢弃证据页（TTL/只读/禁编码部署） | 已合入 |
| write_evidence_page | `core/harness/execution/run_evidence_page.py` | ✅ | run 结束写入 state[_evidence_page] | 已合入 |
| collect_evidence_data | `core/harness/execution/run_evidence_page.py` | ✅ | stage/handoff/error/gates(done_verify+bloat) → tool_result JSON | 已合入 |
| render_evidence_html | `core/harness/execution/run_evidence_page.py` | ✅ | 固定模板注入 JSON；无 LLM 脚本 | 已合入 |
| is_evidence_expired | `core/harness/execution/run_evidence_page.py` | ✅ | 默认 24h TTL 过期判定 | 已合入 |
| resolve_ttl_hours | `core/harness/execution/run_evidence_page.py` | ✅ | TTL 1..168h；env/state 可配 | 已合入 |
| merge_evidence_metrics | `core/harness/execution/run_evidence_page.py` | ✅ | 验证指标累加（source_click/input_change/…） | 已合入 |
| empty_evidence_metrics | `core/harness/execution/run_evidence_page.py` | ✅ | evidence_metrics.v1 空结构 | 已合入 |
| verification_success | `core/harness/execution/run_evidence_page.py` | ✅ | ≥1 验证信号即 verified | 已合入 |
| resolve_factory_sanitize_file | `core/harness/team_factory_seeds.py` | ✅ | 自动同步 | 已合入 |
| resolve_team_yaml_candidates | `core/harness/team_factory_seeds.py` | ✅ | 自动同步 | 已合入 |
| rollback_team_factory_seeds | `core/harness/team_factory_seeds.py` | ✅ | 自动同步 | 已合入 |
| apply_team_factory_seeds | `core/harness/team_factory_seeds.py` | ✅ | 自动同步 | 已合入 |
| is_autosync_enabled | `core/harness/team_harness.py` | ✅ | 自动同步 | 已合入 |
| apply_configured_sources | `core/harness/team_sources.py` | ✅ | 自动同步 | 已合入 |
| merge_source_tree | `core/harness/team_sources.py` | ✅ | 自动同步 | 已合入 |
| configure_team_harness | `core/harness/team_harness.py` | ✅ | 自动同步 | 已合入 |
| pull_team_harness | `core/harness/team_harness.py` | ✅ | 自动同步 | 已合入 |
| materialize_team_harness_schema | `core/harness/team_harness.py` | ✅ | 自动同步 | 已合入 |
| load_team_harness_schema | `core/harness/team_harness.py` | ✅ | 自动同步 | 已合入 |
| summarize_stage_outcome_samples | `core/harness/execution/stage_outcome_samples.py` | ✅ | 自动同步 | 已合入 |
| query_stage_outcome_samples | `core/harness/execution/stage_outcome_samples.py` | ✅ | 自动同步 | 已合入 |
| record_stage_outcome_sample | `core/harness/execution/stage_outcome_samples.py` | ✅ | 自动同步 | 已合入 |
| resolve_output_style | `core/harness/utils/output_style.py` | ✅ | 自动同步 | 已合入 |
| inject_output_style | `core/harness/utils/output_style.py` | ✅ | 自动同步 | 已合入 |
| format_handoff_regenerate_feedback | `core/harness/execution/stage_handoff.py` | ✅ | 自动同步 | 已合入 |
| normalize_handoff | `core/harness/execution/stage_handoff.py` | ✅ | 自动同步 | 已合入 |
| mode_to_team_template | `core/harness/execution/team_planner.py` | ✅ | 自动同步 | 已合入 |
| normalize_factory_profile | `core/harness/execution/factory_profile.py` | ✅ | 自动同步 | 已合入 |
| apply_factory_profile_to_stages | `core/harness/execution/factory_profile.py` | ✅ | 自动同步 | 已合入 |
| apply_stage_output_sanitizers | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| ensure_manifest_ui_binding_pair | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| ensure_manifest_dual_ui_bindings | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| enrich_media_true_test_questions | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| sanitize_test_cases_artifact | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| sanitize_architecture_artifact | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| ensure_dual_component_stages | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| ensure_dual_ingest_stages | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| strip_reasoning_preamble | `core/harness/execution/factory_artifact_sanitize.py` | ✅ | 自动同步 | 已合入 |
| set_prd_markdown_parser | `core/harness/execution/prd_quality_gate.py` | ✅ | 自动同步 | 已合入 |
| parse_prd_markdown | `core/harness/execution/prd_markdown.py` | ✅ | 自动同步 | 已合入 |
| seed_confirmed_prd_into_state | `core/harness/execution/prd_quality_gate.py` | ✅ | 自动同步 | 已合入 |
| factory_finalize_prd | `core/harness/execution/prd_quality_gate.py` | ✅ | 自动同步 | 已合入 |
| materialize_prd_gate_seeds | `core/harness/execution/prd_gate_loader.py` | ✅ | 自动同步 | 已合入 |
| load_prd_gate_packs | `core/harness/execution/prd_gate_loader.py` | ✅ | 自动同步 | 已合入 |
| render_prd_markdown | `core/harness/execution/prd_quality_gate.py` | ✅ | 自动同步 | 已合入 |
| matched_packs_for_text | `core/harness/execution/prd_

…

_(节选)_


### 3.4 自主性定级 ADR（节选）

### aiPlat 自主性分级评估：L5 组织者级

> **评估原则**：平台的总体等级由其**最低分能力轴**决定，因为最薄弱的环节限制整体系统表现。

---

#### 1. 评估方法论

##### 来源

分级体系参考以下权威研究框架：

| 来源 | 贡献 |
|------|------|
| MIT《2025 AI Agent Index》 | 自主性 L1-L5 分级 |
| 剑桥/哈佛/斯坦福联合报告 | 30 个主流系统分为对话式/企业工作流/浏览器三类 |
| 陈德里/DeepSeek | L1-L5 自主分级体系（L4: 受限领域全自主 / L5: 自主选题） |
| arXiv 十大能力轴 | 多维度评估框架 |
| Redis 上下文工程模型 | 五阶段成熟度（ad hoc → optimized） |

##### 六大能力轴

| 能力轴 | 说明 | 评估方法 |
|:---|:---|:---|
| **A. 自主性（Autonomy）** | 完成任务需要多频繁地回头找人类确认 | 每轮任务中人类介入次数 |
| **B. 上下文感知（Context Awareness）** | 能感知和利用多少信息源 | 上下文窗口利用率、信息源数量 |
| **C. 工具掌握（Tool Mastery）** | 能调用多少工具、如何发现和选择 | 工具数量、调用成功率、动态发现能力 |
| **D. 记忆系统（Memory）** | 跨会话、跨任务的信息保持能力 | 记忆层级、版本管理、冲突解决 |
| **E. 协作能力（Coordination）** | 多 Agent 之间的通信与分工 | 并行度、角色分工、冲突解决 |
| **F. 自进化（Self-Evolution）** | 系统能否从执行中学习和优化 | 策略搜索-评估-比较-回滚闭环 |

##### 评估原则

> 平台的总体等级由其**最低分能力轴**决定。六轴取最低分。

---

#### 2. 六轴逐项分析

##### A. 自主性 — L4（高）

> **定义**：自主循环执行直到完成，人类仅关键点介入

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| 自主重试循环 | `_retry_loop` — 6 种退出条件（预算耗尽/停滞/收敛/超时/评分回归/重试耗尽） | `pipeline_engine.py:3185-3297` |
| 自愈决策 | `_meta_optimize` — Phase 24 策略路由：根据 ErrorTranslator 诊断自动选择 rotate_credential / compress_retry / backoff / skip / escalate | `pipeline_engine.py:4519-4555` |
| 运维决策 | `OperatorAgent` — 接收故障信息 → 评估 severity/impact/can_continue → 输出结构化动作建议 | `operator_agent.py` |
| HITL 分级 | `AIPLAT_OPERATOR_CONFIRMATION_LEVEL` — L1(静默)/L2(确认)/L3(全量)/L4(关闭) | `constitution/operator_agent.py` |
| Pipeline 暂停/恢复 | `BuilderSessionPhase.paused` + `POST /pipelines/{id}/hitl-resolve` | `pipeline_engine.py` + `routers/agents.py` |

**验证**：

```bash
grep -c 'async def _retry_loop' core/harness/execution/pipeline_engine.py
### → 1
grep -c 'AIPLAT_OPERATOR_CONFIRMATION_LEVEL' core/apps/agents/operator_agent.py
### → 1
```

**差距（→ L5）**：仍需人类设定目标和启动 pipeline。未到 L5"自主选题、定义研究议程"。

---

##### B. 上下文感知 — L4（强）

> **定义**：全量上下文 + 跨轮次状态 + 跨域知识图谱

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| 运行时上下文注入 | `RunContext` — 三层数据源（API caller / DataSource 实时桥接 / GraphIndex 实体遍历），序列化 ~80 token 注入 system prompt | `kernel/types.py` |
| 本体感知路由 | `_ontology_routing_hint` — 两遍式算法：子串匹配实体 → 邻居计数 ≥ 3 则路由到 graph 引擎 | `execution/router.py` |
| 领域路由 | `DomainRouter.classify` — 3 层级联（T1 倒排索引 <1ms / T2 域向量余弦 ~50ms / T3 LLM 二分类 ~300ms） | `knowledge/domain_router.py` |
| CRAG 3 级回退 | 本体优先检索 → FTS5 关键词 → HyDE 假设答案重检 | `apps/agents/materials_chat.py` |
| 多域本体引擎 | `OntologyEngine` — 23 模块（~6800 行），13 步管线，YAML 驱动 | `ontology_engine/engine.py` |
| 上下文压缩 (P0) | 温度感知剪枝（高温保留 60% / 低温 15%）+ 语义相关性排序（InfraEmbeddingAdapter + LRU 缓存） | `memory/compression.py` |

**验证**：

```bash
grep -c 'class RunContext' core/harness/kernel/types.py
### → 1
grep -c 'CRAG\|HyDE' core/apps/agents/materials_chat.py
### → 多次命中（CRAG 3 级回退 + HyDE 重检）
find core/harness/ontology_engine/ -name '*.py' | wc -l
### → 26
```

**差距（→ L5）**：跨系统实时上下文（MES/ERP）虽有 DataSource 桥接，但尚未深度集成。

---

##### C. 工具掌握 — L4（20+，动态发现）

> **定义**：20+ 工具，自动选择，动态发现

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| API 端点 | 813 个 REST 端点，覆盖全系统 | `api/routers/` |
| Engine Skill | 32 个内置 Skill，SKILL.md frontmatter 注册 + execution_type 声明 | `engine/skills/` |
| MCP 动态发现 | 启动时自动扫描 `server.yaml` → 注册到 `ToolRegistry` | `apps/mcp/server.py` |
| Skill 路由 | disabled skill 可搜索（`sys_skill_corpus_search`），按需激活 | `execution/stage_runner.py` |
| 工具权限 | PolicyGate + ApprovalGate 双重门禁，deny-by-default | `infrastructure/gates/policy_gate.py:1039` |
| 安全沙箱 | `SandboxGate` — isolated subprocess，危险命令拦截 | `infrastructure/gates/sandbox_gate.py` |

**验证**：

```bash
wc -l < core/harness/infrastructure/gates/policy_gate.py
### → 1039
wc -l < core/harness/infrastructure/gates/approval_gate.py
### → 361
grep -c 'class.*Sandbox' core/harness/infrastructure/gates/sandbox_gate.py
### → 2
```

**差距（→ L5）**：不支持"自举创建新工具"（Agent 自主生成代码 → 注册为 Skill）。

---

##### D. 记忆系统 — L4（强，接近上限）

> **定义**：全栈记忆 + 版本管理 + 冲突解决 + 反馈闭环

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| Working Memory | 30K token 滑动窗口，温度感知剪枝 | `memory/working.py` |
| Episodic Memory | 规则摘要 + TTL 自动清理 (`cleanup_expired` 每 10 次 build_context) | `memory/episodic.py` |
| Semantic Memory | SQLite FTS5 + 动态续期 + 软删除 + 5 维 Jaccard 矛盾检测 (`_resolve_semantic_conflict`) | `memory/semantic.py` |
| Task Skills | Pipeline 完成自动晶体化（pass_rate ≥ 85% → SkillRegistry） | `memory/manager.py` |
| 反馈闭环 | 捕获 `_feedback_action` → access_count 动态降权 | `memory/manager.py` |
| Memory OS Agent | 独立实体，4 工作流（cleanup/conflict/fusion/prune） | `~/.aiplat/agents/memory_os/AGENT.md` |
| 物理熔断 | per-tenant SQLite，不可回退 | Phase 18.4 |

**验证**：

```bash
grep -c 'build_context\|save_interaction\|cleanup_expired' core/harness/memory/manager.py
### → 5
grep -c '_resolve_semantic_conflict' core/harness/memory/semantic.py
### → 2
grep -c 'cleanup_expired' core/harness/memory/episodic.py
### → 1
test -f ~/.aiplat/agents/memory_os/AGENT.md && echo exists
### → exists
```

**差距（→ L5）**：缺少"蜂群共享记忆"和"组织级知识沉淀"（跨 Agent 实例的知识同步）。

---

##### E. 协作能力 — L4（多 Agent 编队）

> **定义**：多角色分工 + 并行执行 + 语义通信

**表现**：

| 能力 | 实现 | 代码位置 |
|------|------|---------|
| Pipeline 多角色编队 | PM → Architect → FE → BE → QA，每个 Agent 独立 AGENT.md + role | `schemas_builder.py` |
| 子 Agent 协调 | `SubagentCoordinator` — 父 Agent 创建子 Agent，独立 run_id，返回摘要 | `apps/agents/multi_agent.py` |
| 并行执行 | `ParallelExecutor` — Map-Reduce 并发，Semaphore 控制，异常隔离 | `apps/agents/parallel_executor.py` |
| 语义通信桥 | `EmbeddingBridge` — 子 Agent 间通过向量传递核心语义，Token -30~40% | `apps/agents/parallel_executor.py` |
| 集成总线 | `integration.py` — 统一出口，8 gates 集中管理（3595 行） | `harness/integration.py` |

**验证**：

```bash
wc -l < core/harness/integration.py
### → 3595
```

**差距（→ L5）**：固定 Pipeline stage 顺序（配置驱动但顺序预定义），未到 L5 的"动态组队、自主分工"。

---

##### F. 自进化 — L5

> **定义**：UCB1 搜索-评估-比较-回滚闭环 + 数据驱动的策略路由 + 自主工具创建 + 动态组队

**表现**：

| 能力 | 实现 | Phase | 代码位置 |
|------|------|:---:|---------|
| 错误诊断 | `ErrorTranslator` — 7 级 19 类错误 | 24 | `error_translator.py` |
| UCB1 策略搜索 | `StrategySearchEngine` — 多臂老虎机收敛到最优策略 | 29 | `optimization/search_engine.py` |
| 可重现执行快照 | `ExecutionSnapshot` — 策略执行前后全状态保存+对比 | 25 | `execution/snapshot.py` |
| 策略效果跟踪 | `StrategyEffectivenessTracker` — 数据驱动路由 + 评分排名 | 26 | `optimization/strategy_tracker.py` |
| 跨实例知识共享 | `SharedKnowledgePool` — 跨 Session pub/sub | 27 | `memory/shared_pool.py` |
| 自主目标生成 | `GoalGenerator` — 五类缺口扫描改进提案 | 28 | `optimization/goal_generator.py` |
| 自主闭环执行 | `GoalExecutor` — 低风险提案自动执行 | 30 | `optimization/goal_executor.py` |
| 自举工具创建 | `ToolBootstrapEngine` — gap→generate→validate→register | 31 | `optimization/tool_bootstrap.py` |
| 动态组队 | `DynamicOrchestrator` — 能力缺口检测 + 子 Agent 动态生成 | 32 | `coordination/dynamic_orchestrator.py` |

**验证**：
```bash
grep -c 'class StrategySearchEngine' core/harness/optimization/search_engine.py
### → 1（Phase 29: UCB1 搜索-评估-比较-回滚闭环）
grep -c 'class GoalExecutor' core/harness/optimization/goal_executor.py
### → 1（Phase 30: 自主闭环执行器）
grep -c 'class ToolBootstrapEngine' core/harness/optimization/tool_bootstrap.py
### → 1（Phase 31: 自举创建工具）
grep -c 'class DynamicOrchestrator' core/harness/coordination/dynamic_orchestrator.py
### → 1（Phase 32: 动态组队引擎）
```

**差距（→ L6）**：UCB1 是收敛算法而非持续优化的在线学习。ToolBootstrap 是基于 prompt 的技能创建，非完整代码生成→部署→注册闭环。DynamicOrchestrator 是基于模式匹配的注册表查询，非 emergent swarm 行为。

---

##### 能力对照矩阵（结论）

| 能力轴 | 级别 | 状态 |
|:---|---:|:--:|
| A. 自主性 | L4（高） | 6 种退出条件的自主循环 + 分级 HITL |
| B. 上下文感知 | L4（强） | CRAG + 23 模块本体引擎 + RunContext 三层注入 |
| C. 工具掌握 | L4 | 813 端点 + 32 Skill + MCP 动态发现 |
| D. 记忆系统 | L4（强） | 四层记忆 + 矛盾检测 + TTL + 反馈闭环 |
| E. 协作能力 | L4 | Pipeline 编队 + 子 Agent 协调 + 语义通信桥 |
| A. 自主性 | **L5** | GoalExecutor 自主闭环执行 |
| B. 上下文感知 | L4（强） | CRAG + 23 模块本体引擎 + RunContext 三层注入 |
| C. 工具掌握 | **L4+** | 813 端点 + 32 Skill + MCP + ToolBootstrap (prompt-based) |
| D. 记忆系统 | L4（强） | 四层记忆 + 矛盾检测 + TTL + SharedKnowledgePool |
| E. 协作能力 | **L4+** | Pipeline 编队 + SubagentCoordinator + DynamicOrchestrator |
| F. 自进化 | **L5** | UCB1 搜索-评估-比较-回滚闭环 |

**六轴最低分 = C/E. L4+** → 系统整体定级为 **L4+（五轴 L4+, 两轴 L5）**。
按最低分原则，C 轴（工具）和 E 轴（协作）仍为 L4+ 而非 L5。

##### L5 全量达成路径

| 能力 | 状态 | 剩余差距 |
|:---|:--

…

_(节选；全文见权威源)_


## 4. 相关横切（对标 / 评级）

完整对标与评级目录见总白皮书 §2.5 与 [`docs/whitepaper/WHITEPAPER_SYSTEM.md`](../WHITEPAPER_SYSTEM.md)。

## 5. 验证

```bash
python3 scripts/generate_whitepaper_volumes.py --check
python3 scripts/generate_platform_whitepaper.py --check
```

*生成器：`scripts/generate_whitepaper_volumes.py` · volume=`security-governance`*
