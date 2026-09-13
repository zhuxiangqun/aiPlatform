# 企业部署选型：AI 网关两层五类 × aiPlat 落点

> **定位**：架构验收标尺，不是产品选型清单。  
> **原则**：先分层再选型；**买在错层**的代价大于买错品牌。  
> **不做**：在 core/platform 内揉成「超级网关」或自建网络层私有出口产品。

相关入口：[private-control-plane.md](private-control-plane.md)（PolicyGate/ApprovalGate）、[governance.md](governance.md)、[manuals/deployment.md](../manuals/deployment.md)（运维部署步骤）。

---

## 1. 两层分界，五类错位

| 品类 | 工作层 | 管什么 | 核心动作 |
|------|--------|--------|----------|
| 大模型网关 | 应用层·模型 API | 统一模型接入、控成本 | 路由、缓存、Token 计量 |
| MCP 网关 | 工具/连接器层 | 治理 Agent→工具 | 鉴权、凭据代理、调用审计 |
| Agent 网关 | Agent 编排层 | 治理多 Agent 协同 | 协议感知路由、身份、人在环 |
| AI 安全网关 | 应用层·内容侧 | 防泄漏、管影子 AI | Prompt 注入防护、内容级 DLP |
| 网络层私有 AI 网关 | 网络接入层 | 数据不出域、私有化 | 统一接入+脱敏出域、本地控制面 |

前四类按「做什么功能」区分；第五类按「怎么交付 / 数据主权」区分。  
它们是一条可叠加的链，**不是五选一**。

---

## 2. 选型三问（强制——进入架构验收）

任何「AI 网关 / 私有化 / 合规部署」方案立项前，必须书面回答：

| # | 问题 | 合格答案形态 | 不合格信号 |
|---|------|--------------|------------|
| 1 | **管什么对象？** | 明确落在上表某一品类（可多选，但每项独立验收） | 「全能网关」「一站式安全」无边界 |
| 2 | **哪一跳出域？** | 画出请求路径：检测点在第 N 跳；数据在检测前是否已离开企业边界 | 只谈功能清单，不画跳数 |
| 3 | **控制面归谁？** | 策略、审计、吊销、密钥轮转的权威落点（本地 / 云 SaaS / 混合） | 控制面在云上却承诺「数据主权」 |

验收写法示例（可直接贴进 ADR）：

```text
对象: LLM + MCP（应用层）；网络出口由客户防火墙/本地模型承接（本仓库不交付第五类产品）
出域跳: sys_llm_generate → InfraLLMAdapter → provider；PII 掩码在 LLM syscall 内、发送前
控制面: PolicyGate + ApprovalGate + ExecutionStore 审计；密钥经 ModelManager/CredentialPool
```

---

## 3. 三类失效模式 × aiPlat 映射（含代码证据）

### 3.1 数据先出域，再被读

**失效**：安全/脱敏部署在云上或应用远端，请求先离开企业网络才被扫。

| 项 | aiPlat 现状 | 证据 |
|----|-------------|------|
| 内容侧防护（偏弱·应用层） | `_guard_messages`：注入检测 + 发送前 PII 掩码；注入告警可拒绝 LLM 调用 | `aiPlat-core/core/harness/syscalls/llm.py`：`_guard_messages` ~L342；`pii_masked` ~L549；拒绝路径 ~L1723–1767 |
| 网络层私有出口 | **不在本仓库交付范围**（由客户侧防火墙 / 本地模型 / 第三方私有出口承接） | 设计约束：见本文 §5；勿把应用层 Gate 写成「已覆盖第五类」 |
| 判断方法 | 问：检测点落在哪一跳？数据在检测前是否已出域？ | 选型三问 #2 |

```bash
# 验证：注入/PII 守卫存在
grep -n "def _guard_messages\|pii_masked\|prompt_injection" \
  aiPlat-core/core/harness/syscalls/llm.py | head -10
```

### 3.2 凭据不收敛

**失效**：工具/模型密钥散落各 Agent、各 MCP server、各业务配置；一处泄露横向扩散，无法按主体吊销。

| 项 | aiPlat 现状 | 证据 |
|----|-------------|------|
| 模型凭据 | `ModelManager.get_credentials` → `CredentialPool`（轮询 + 429 cooldown） | `aiPlat-infra/infra/management/model/manager.py`：`get_credentials` ~L1087；`credential_pool.py`：`CredentialPool` ~L59；`next` ~L154；`mark_rate_limited` ~L174 |
| MCP 生产 stdio | prod 仅白名单：`prod_allowed` + `AIPLAT_PROD_STDIO_MCP_ALLOWLIST` + 绝对路径命令 | `aiPlat-core/core/mcp/prod_policy.py`：`prod_stdio_policy_check` ~L15–50 |
| 工具/技能权限总闸 | `PolicyGate.check_tool` / `check_skill` / `check_agent`（syscall 层唯一权限点） | `aiPlat-core/core/harness/infrastructure/gates/policy_gate.py`：`PolicyGate` ~L276；`check_tool` ~L799 |
| **缺口（诚实标注）** | MCP 工具侧「凭据代理 / 按主体一键吊销」未做成独立网关产品；依赖 env/配置纪律 + PolicyGate | 勿把 hop schema 门当成 MCP 凭据网关（见 §4） |

```bash
# 验证：凭据池 + MCP prod 策略
grep -n "class CredentialPool\|def next\|mark_rate_limited" \
  aiPlat-infra/infra/management/model/credential_pool.py
grep -n "AIPLAT_PROD_STDIO_MCP_ALLOWLIST\|prod_stdio_policy_check" \
  aiPlat-core/core/mcp/prod_policy.py
```

### 3.3 控制面在云上，审计无法自证

**失效**：策略与审计权威在厂商云；出事时无法用本方可验证日志自证。

| 项 | aiPlat 现状 | 证据 |
|----|-------------|------|
| 策略权威 | PolicyGate + ApprovalGate（本地进程内 / 部署方基础设施） | `policy_gate.py`；`approval_gate.py`：`ApprovalGate` ~L154；入口见 [private-control-plane.md](private-control-plane.md) |
| 运行审计 | ExecutionStore / audit 链路（部署方存储） | `core/harness/observability/audit.py`（见 private-control-plane 表） |
| Agent 协同控制 | 工厂默认 `mode: single`；`spawn_policy` + `skill_hop_gate` + `promotion_gate`；消息总线**非**协同主路径 | `spawn_policy.py`；`aiPlat-platform/builder/skill_hop_gate.py`；契约条款见 `system-architecture-contract.md` §5 #31 |
| **缺口** | 若客户把 LLM provider 与全部审计日志都放在不可控第三方，本平台无法单独「自证」——控制面归属仍是部署拓扑问题（三问 #3） | — |

```bash
# 验证：控制面组件可定位
ls aiPlat-core/core/harness/infrastructure/gates/policy_gate.py \
   aiPlat-core/core/harness/infrastructure/gates/approval_gate.py
grep -n "allow_dynamic_spawn\|should_skip_dynamic_spawn" \
  aiPlat-core/core/harness/coordination/spawn_policy.py | head -5
```

---

## 4. 易混映射（禁止写进对外材料）

| ❌ 误写 | ✅ 正确边界 |
|--------|-------------|
| W4 `skill_hop_gate` = MCP 网关 | hop 管的是**工厂 Skill 入参契约**（`execute_skill` ↔ `input_schema`）；MCP 网关管的是 Agent→外部工具的聚合/凭据/审计 |
| `generated_conformance` = AI 安全网关 | conformance = **生成物形态**契约（部署前）；安全网关 = 内容侧注入/DLP/影子 AI |
| PolicyGate = 网络层私有出口 | PolicyGate = syscall **权限**总闸；不出域是网络/拓扑问题 |
| `agent_messages` = Agent 协同主路径 | 身份/通知层；协同主路径 = Pipeline + handoff + schema 门 + HITL |

---

## 5. aiPlat 品类成熟度（对照表）

| 品类 | 成熟度 | 主路径 | 明确不做 |
|------|:------:|--------|----------|
| 1 LLM 网关 | **强** | `ModelManager` → `InfraLLMAdapter` → `sys_llm_generate`；成本/配额/限流 | 不按 provider 在 core 分文件适配器 |
| 2 MCP 网关 | **中强** | `MCPRuntime` + `prod_policy` + `PolicyGate` + Trace | 不把 hop 门写成 MCP 网关 |
| 3 Agent 网关 | **强（契约化）** | Pipeline / spawn_policy / hop / promotion / HITL | 不默认自由多 Agent / 消息总线冒充协同 |
| 4 AI 安全网关 | **偏弱·部分** | `_guard_messages` + PII；非完整影子 AI / 内容级 DLP 产品 | 不把 conformance 写成已覆盖 |
| 5 网络层私有出口 | **不适用（本仓库）** | 客户防火墙 / 本地模型 / 第三方 PAG | **禁止**在 core 建网络出口产品 |

---

## 6. 与应用工厂的关系

工厂「跑通」晋升（N≥20、`failed_stage`、conformance/real_tests 物理证据、PolicyGate）回答的是：**生成物是否可晋升**，不是「企业网络是否出域」。

部署验收应同时满足：

1. 工厂晋升门禁（见 `system-architecture-contract.md` §5 #31）  
2. 本文选型三问书面答案  
3. 三类失效模式无「买在错层」残留

---

## 7. 变更纪律

- 新增「网关」能力族时：更新本文成熟度表 + `AIPLAT_CAPABILITIES.md`（含生成物适用性）。  
- 禁止用文档把第五类写成「已实现」。  
- 事实性声明必须可 `grep` 复核（本文 §3 表内路径/行号）。
