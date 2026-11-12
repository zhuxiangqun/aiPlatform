---
doc_type: Report
---

# Batch 01 事实审核台账

## 范围

```text
docs/standards/       16 份  已审核 16
docs/contracts/       36 份  已审核 26，未审核 10
docs/architecture/    61 份  已审核 61（5 份符号级，其余链接/路径级）
```

## 结果

```text
standards: pass 11 / fix 5 / needs-owner 0
contracts: pass 22 / fix 1 / needs-owner 3（26/36）
architecture: pass 53 / fix 5 / needs-owner 5（61/61）
合计：pass 86 / fix 11 / needs-owner 8
```

## 已修复

| 文档 | 问题 | 修复 |
|---|---|---|
| `docs/standards/.../conformance/README.md` | 旧 approval record 文件名、旧校验命令、错误生效版本 | 改为 v4.3.1 实际文件与命令 |
| `docs/standards/规范-core-run_id-trace_id-request_id.md` | `core_facade.py:1868`、`job_scheduler.py:179` 行号漂移 | 改为 2202 / 187 |
| `docs/standards/规范-platform-鉴权与身份透传.md` | builder 签名验证行号 508–532 过期 | 改为 944–968 |
| `docs/standards/规范-功能开关与配置.md` | workspace_skills_meta 路径错误、两个默认值描述错误 | 改为 core 路径 + 默认 true 例外 |
| `docs/standards/规范-独立多租户.md` | 租户表迁移写成“待迁移”；MemoryEntry 字段描述错误 | 改为已迁移 + Manager 注入 metadata |
| `docs/contracts/FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md` | accept_order 别名仍写成 canonical + alias | 改为 canonical only / alias removed |

## architecture 已修复

| 文档 | 问题 | 修复 |
|---|---|---|
| `docs/architecture/overview.md` | `loop.py` 不存在；`evolution_engine.py` 路径错；Agent/Skill 数量陈旧；多个行号错位 | 改为 package 路径、10 类 Agent、58 Engine skills；行号改为文件级入口 |
| `docs/architecture/boundary-standard.md` | `database_port.py` 不存在；document 模块状态写成“需新建”；kb_provider 写成 Any；`docs/index.md` 不存在 | 改为 bridge 现状、模块已存在、Protocol 已接入、`docs/README.md` |
| `docs/architecture/capability-profile.md` | 三个函数实际在 `pipeline_stage.py`；多个 file:line 错位 | 改为 `pipeline_stage.py:283/310/390` 等实际位置 |
| `docs/architecture/slo.md` | 声称 SLI 由 Prometheus 测量，但 4 个指标名不存在 | 改为“计划指标，未实现” |
| `docs/architecture/plans/observability-eval-repair-architecture.md` | 三个证据锚点过期/不存在 | 改为 `base.py:443`、`eval_runner.py:498`、auto-runtime 实际记录位置 |

## needs-owner（8）

```text
docs/contracts/ORG_M4_SIGNOFF_PACK.md
docs/contracts/ORG_L5_LIVE_UNLOCK.md
docs/contracts/FDE_PHASE0_KICKOFF_CHECKLIST.md
docs/architecture/eu-ai-act-compliance.md
docs/architecture/comparison.md
docs/architecture/plans/ai-platform-five-products-review-talking-points.md
docs/architecture/plans/ai-platform-five-products-review-deck-outline.md
docs/architecture/plans/ai-platform-five-products-decision-brief.md
```

原因：客户签收、签名、EU 法规、第三方产品能力、商业叙事，仓库无法独立验证。

## 未审核（contracts，10 份；architecture 已全部机械审核）

```text
FDE_DECISION_RECORD.md
FDE_GUARD_REGISTRY_LANDING.md
FDE_WORKBENCH_CONTRACT.md
FDE_WORKBENCH_CAPABILITY_LEDGER.md
FDE_USAGE_SIGNAL_MINIMAL_SET.md
FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md
FDE_ONTOLOGY_AGENT_OPS_MANUAL.md
ORG_L5_DECISION_RECORD.md
ORG_L5_PILOT_SPEC.md
ORG_CHANNEL_INTERFACE_CHARTER.md
```

## 验证

```text
docs links：0
doc_type：全部有效
v4.3.1 examples：22/22
v4.3.1 semantic：30/30
```
