# EU AI Act 合规自评（初稿）

> **PolicyGate 实现参考**：[private-control-plane.md](./private-control-plane.md)

> 框架三 macro.2 合规伦理 2.5→3.0 baseline。本文件证明 aiPlat 具备基本的 AI 合规意识与内建护栏——**非正式合规审计**，而是工程能力清单。

last_synced: 2026-07-07
status: draft
owner: compliance/security

---

## 1. EU AI Act 四等风险评估（自评）

| 风险等级 | 触发条件 | aiPlat 状态 | 证据 |
|------|:--|:--:|------|
| **不可接受** | 社会评分/实时生物特征 | ✅ N/A | 不涉及 |
| **高风险** | 关键基础设施 / 教育 / 雇佣 | ⚠️ 不适用当前 SaaS 形态 | — |
| **有限风险** | Chat/Agent transparency | ✅ 已覆盖 | 系统 prompt 透明度 + audit log |
| **极小风险** | 通用 AI 系统 | ✅ aiPlat 定位在此 | 内建护栏 + 可追溯性 |

## 2. 内建护栏清单

| 要求 | 实现 | 文件/行号 |
|------|------|------|
| **透明性** | 系统 prompt 未隐藏（多 Agent 模式下 agent 知道自己角色）；audit log 可追溯 | `syscalls/llm.py` → trace_id + span_id |
| **可追溯** | SHA-256 审计链 + 决策溯源(`reason`字段)；每次 `sys_llm_generate` 携带 span | `syscalls/llm.py`；`CLAUDE.md §5.20` |
| **禁止注入** | 用户输入必须经过 injection detection（6 正则 + 特殊 token 过滤） | `syscalls/llm.py:_guard_messages()` |
| **PII 脱敏** | 双引擎（Presidio + 内置正则）自动掩码 | `syscalls/llm.py` → `PIIDetector.mask()` |
| **风险监控** | 安全/危机检测：每轮输出自动扫描 crisis signals + sentiment | `security/crisis_detector.py` + `emotion_tracker.py` |
| **可申诉** | 政策门(PolicyGate) allowlist → DENY 可被 admin override | `gates/policy_gate.py:147-166` |
| **人工兜底** | HITL（人机交互）暂停→人工审批→恢复；恢复后从 checkpoint 继续 | `pipeline_engine.py` → HITL + `CLAUDE.md §5.16` |
| **模型治理** | 黑名单/白名单 + 模型准入+退役 | infra `ModelManager` |
| **密钥安全** | AES-256-GCM at rest + 日志脱敏（`secret[:4]+'***'`） | `SecretsManager`；`CLAUDE.md §5.67` |

## 3. 差距

| 领域 | 状态 | 说明 |
|------|------|------|
| EU AI Act 正式合规计划 | ❌ | 无外部 legal/audit 评估 |
| 算法备案（中国） | ❌ | 无 |
| 高风险系统文档（如用于关键基础设施） | N/A | 当前不适用 |
| 偏差检测 (fairness) | ❌ | 无 SHAP/LIME 集成 |
| ISO 42001 认证 | ❌ | 未认证，但架构对其有对齐设计 |

## 4. 基线评级

**aiPlat 具备有限风险级别的内建护栏，可自评为 3.0 基线（最低 EU AI Act 准备就绪）。** 达到 4.0+ 需要外部合规审计。
