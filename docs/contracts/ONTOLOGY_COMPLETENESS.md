# 本体完整性契约（Ontology Completeness）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-COMPLETENESS-2026-09` |
| 版本 | v1.1 |
| 状态 | 生效 |
| 关联 | [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ONTOLOGY_RUNTIME_CLOSEOUT.md`](./ONTOLOGY_RUNTIME_CLOSEOUT.md) · [`FDE_WORKBENCH_CAPABILITY_LEDGER.md`](./FDE_WORKBENCH_CAPABILITY_LEDGER.md) |
| 维护人 | Oliver Zhu |

---

## 0. 「完整企业本体」的官方定义（已确认）

**完整 = 双目标，不是跨企业统一 TBox，也不是 28 域 YAML 齐套。**

| 维度 | 含义 | 验收 |
|------|------|------|
| **A. 平台能力完整** | 任意新客户可用同一方法建成可运行业务世界（YAML + GraphIndex + Action L1 + 提案门 + 审计） | 第二客户零改 harness 接入 |
| **B. 客户纵深完整** | 至少一个客户域达到深档且覆盖核心经营闭环 | 该域 OCS ≥ 80 |

对外话术：

> 我们交付的是**可配置、可执行、可演化的企业业务世界能力**；完整性按**客户场景闭环覆盖率（OCS）**度量，不按概念图节点数度量。

**禁止**：在平台能力完整（Phase C）之前宣称「完整企业本体已建成」；禁止以「28 域都有 YAML」为完成定义。

**路线**：纵深标杆（Phase A）→ 方法产品化（Phase B）→ 第二客户复用（Phase C）→ 语义模块蓝图（Phase D）。

---

## 1. Ontology Completeness Score（OCS）

对每个 `domain_id` 计算加权分 0–100。**≥ 80** 才可称该域「纵深完整」。

| 维 | 权重 | 计分规则（实现见 `compute_domain_ocs`） |
|----|-----:|----------------------------------------|
| C1 类与属性 | 15 | 有 classes；≥50% 类声明 `required_fields` → 满分，否则按比例 |
| C2 状态机 | 20 | 有 states.enum 的类占比；有 transitions 加分 |
| C3 公理/证据 | 15 | axioms≥3 满分；1–2 按比例；compiler 可加载再加分 |
| C4 Action 硬门 | 25 | 该域 `customer_action` 数；有 `required_state`/`forbidden_states` 的占比 |
| C5 事实层 | 15 | GraphIndex 节点数>0；有边再加分 |
| C6 演化闭环 | 10 | 存在 applied 本体提案；或种子/测试证明中深档（配置覆盖） |

**试点阈值**：OCS ≥ 70 → `pilot`；≥ 80 → 可称纵深完整（ledger `production` 域级）。

平台门禁（与 OCS 正交）：

| ID | 门 | 状态 |
|----|-----|------|
| P1 | 新域 = registry + YAML + Action seed | 具备 |
| P2 | 双轨权威文档+UI | 具备 |
| P3 | confirm → 提案 | 本阶段接线 |
| P4 | 第二客户复用 | **service-domain OCS≥80（complete）** |

---

## 2. 报告与脚手架

```bash
PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py
PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py --domain lock-service
PYTHONPATH=aiPlat-core python3 scripts/new_domain_scaffold.py --domain-id my-domain --name "我的域"
```

CI：

```bash
# Ratchet — Phase A 纵深标杆（contracts-guard workflow 同步执行）
PYTHONPATH=aiPlat-core python3 scripts/report_ontology_completeness.py --domain lock-service --min-ocs 80
pytest aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_completeness_ocs.py -q
```

`lock-service` OCS 不得低于 **80**；缺 `required_state` 的新 customer_action 由测试守卫。无 `~/.aiplat` 时从 `workspace_seeds/ontologies` 回退加载。

---

## 3. 阶段出口话术

| 阶段 | 可说 | 不可说 |
|------|------|--------|
| A | 锁安安装维保业务世界已可运行（OCS≥80） | 企业本体已完整 |
| B | 具备可复制的企业本体建设方法 | 已覆盖全部行业 |
| C | 第二客户已用同一方法上线 | 全域统一语义已完成 |
| D | 语义模块正在跨场景复用 | OWL 企业本体已建成 |

---

## 4. 前端域默认值（D2）

| 页面 | 默认 `domain_id` | 说明 |
|------|------------------|------|
| KnowledgeFactory | `lock-service` | 客户纵深场景（抽取/提案/跨域） |
| BranchPanel / Ontology 分支 | `fde-delivery` | **有意**：平台交付跟踪本体，非客户业务域 |
| FdeDashboard Action YAML 示例 | `fde-delivery` | 平台动作模板示例 |

禁止把「页面默认 fde-delivery」误读为客户域未切换。

---

## 5. 变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-09-15 | 确认 A+B 定义；OCS 六维；挂 Phase A–D |
| v1.1 | 2026-09-15 | CI ratchet≥80；seed 回退；D2 前端域表；unified_customer 运行时接线 |
