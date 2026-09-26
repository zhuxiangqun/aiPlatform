# 操作手册：管理端创建本体 + Agent（含 FDE 工作台）

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-ONTOLOGY-AGENT-OPS-2026-09` |
| 版本 | v1.2 |
| 日期 | 2026-09-20 |
| 关联 | [`FDE_PHASE5_CUSTOMER_ONBOARDING.md`](./FDE_PHASE5_CUSTOMER_ONBOARDING.md) · [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) · [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md)（v3.7） · [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) |
| 原则 | **以管理端真实菜单/按钮为准**；FDE 不做「新建域 / 新建 Agent」 |
| 同步 | v1.2：补 it-ops 组织试点/签收准备入口交叉引用（≠ FDE 交付签收单） |

---

## 0. 与现状是否同步？（审计结论）

| 项 | 状态 | 说明 |
|----|:----:|------|
| 菜单 / 路由（业务本体 · FDE · Agent） | ✅ | `pageManifest.ts` 与 §0 表一致 |
| FDE ⑦ AcceptTab 种图/动作/表CSV/三柱 | ✅ | `FdeDashboard.tsx` 按钮与 §3.1 一致 |
| 应用库 Agent 创建 / 从模板安装 | ✅ | `/workspace/agents` · `Agents.tsx` |
| 知识工厂 confirm→提案→apply | ✅ | 业务本体 `?tab=factory` |
| 域脚手架 CLI | ✅ | `scripts/new_domain_scaffold.py` |
| **域管理「新建域」API** | ✅ 已修 | UI 曾打 `/api/core/domains`（404）；已改为 `/api/core/ontology/domains`（与 `wiki.py` 一致）。编辑器路径仍推荐：`/api/platform/apps/ontology-editor/domains` |
| FDE 工作台内嵌本手册 | ❌ | ⑦ 无链到本文；⑤ POC 页有「POC 操作手册」→ 已归档的 `docs/manuals/fde/_archive/fde-poc-playbook.md`（**不是**本文） |
| 与 PPT / PLAYBOOK 版本引用 | ✅ v1.1 | 链到 PPT v3.7、PLAYBOOK v1.3 |
| it-ops 组织试点 / 签收准备 | ✅ 交叉引用 | 入口 `/org/pilot`；权威 [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md) · [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)。**不是** FDE ⑦ 交付签收单 |

**结论**：流程口径大体已与当前实现一致；v1.0 最大漂移是「新建域」API 路径，已在代码 + 本文修正。企业交付请用**本文**，勿用 POC 归档手册。

---

## 0.1 先读：能力落在哪块屏幕

| 你要做的事 | 正确入口（侧边栏） | 路由 | FDE 工作台？ |
|------------|-------------------|------|:------------:|
| **新建域本体（说明书）** | 知识 → **业务本体** → 域管理 / 编辑器 | `/knowledge/business` | ❌ 仅链接出去 |
| **演进已有域（抽取→提案 apply）** | 业务本体 → **工厂流水线** | `/knowledge/business?tab=factory` | ① 可链到工厂 |
| **种演示图 / 点动作硬门** | AI 应用工厂 → **FDE 工作台** → ⑦ 验收 | `/diagnostics/fde` | ✅ |
| **新建应用库 Agent** | AI 应用工厂 → **Agent** | `/workspace/agents` | ❌ 仅有「创建指南」文案 |
| **it-ops 组织试点 / 签收准备**（八闸门·剧本） | 仪表盘 → **组织试点** | `/org/pilot` | ❌ ⑦ 可有 Org L5 面板，签收准备以试点页为准 |
| 引擎 Agent 启停 | 平台设置 → 引擎 Agent | `/core/agents` | ❌ 无创建按钮 |

> **勿混淆**：「FDE 交付签收」（项目 Checklist / 签收单 PDF）≠「Org M4 it-ops 签收准备」（材料齐可送审，`m4_claim_allowed` 恒 false，直至客户双签）。组织侧按 [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) §6.5 剧本操作。


**推荐新人顺序**

```text
1 业务本体：新建域 → 加类/关系 → 发布
2 （可选）注册 customer_action YAML
3 FDE ①：建客户 Profile，②：绑域
4 FDE ⑦：种图 + 点分诊等动作（验证硬门）
5 Agent 页：创建或从模板安装 Agent
```

---

## 1. 前置条件

| 项 | 说明 |
|----|------|
| 账号 | 能看到「知识」「AI 应用工厂」菜单（如 admin / developer / fde） |
| 服务 | 管理端前端 + Platform/Core API 已启动 |
| 数据目录 | `~/.aiplat`（或 `AIPLAT_HOME`）：`ontologies/`、`agents/`、`actions/` |
| 浏览器 | 建议用侧边栏进入，勿只记旧书签（`/ontology-editor` 等会重定向） |

---

## 2. 创建本体（说明书 / 域 YAML）

### 2.1 路径一：域管理「新建域」

1. 打开 **知识 → 业务本体**。  
2. 顶部 Tab 选 **域管理**（`?tab=domains`）。  
3. 点 **新建域**。  
4. 弹窗 **创建领域本体**：填写  
   - **标识**（`domain_id`，如 `acme-ops`，建议小写+连字符）  
   - **名称**、**描述**  
5. 点 **创建**。  
6. 预期：提示「创建成功！现在可以添加类和关系」；列表出现新域卡片。  
7. 在卡片上 **添加类 / 关系**；需要时用 **一键分类+构建** 等（以页面按钮为准）。  

**API（后台）**：`POST /api/core/ontology/domains`  
（UI：`OntologyManager.tsx` → `WIKI_API=/api/core/ontology`）

**落盘**：`~/.aiplat/ontologies/{domain_id}.yaml`，并热注册 `DomainRouter`。

### 2.2 路径二：本体编辑器（推荐，平台层权威 CRUD）

1. **业务本体 → 编辑器**（`?tab=editor`）。  
2. 左侧 **业务域本体** 旁点 **+**（Create domain）。  
3. 输入 `domain_id` 与显示名 → **Create**。  
4. 选中域 → **New class** 等编辑类/关系。  
5. 点 **Publish**（保存图标）写回 live YAML。  

**API**：`POST /api/platform/apps/ontology-editor/domains`，以及 classes / publish 等。  

FDE ① 页横幅也会提示：新客户建域请走 Ontology Editor / 业务本体，而不是在 FDE 里「新建本体」。

### 2.3 路径三：知识工厂演进（不新建空域）

用于**已有域**上「文档/代码→提案→改说明书」：

1. **业务本体 → 工厂流水线**（`?tab=factory`；可带 `&domain=` / `&proposal=`）。  
2. 右上角选 **当前域**（lock-service / it-ops / data-gov / …）。  
3. **① 知识抽取**：上传/粘贴 → **抽取** → 待审 **确认** / **忽略**。  
4. **①b 代码/表头建议**：选「表头/CSV」粘贴 CSV → **表头入队提案**；或「代码片段」→ 入队（禁自动 apply）。  
5. **② 跨域解析**：对候选 **关联**（按需）。  
6. **③ 本体提案**：**批准** → **应用（apply）**；页面展示**最近 apply 回执**（版本/新增类/快照路径）。  

表/CSV 入轨仍在 **FDE⑦**，勿与本页建说明书混淆。  
**勿与 FDE ⑧ Evolve（配置白名单）混淆**——那不是说明书提案。

### 2.4 路径四：CLI 脚手架（无管理端按钮）

适合批量/CI：

```bash
cd /path/to/aiPlatform
PYTHONPATH=aiPlat-core:. .venv/bin/python scripts/new_domain_scaffold.py \
  --domain-id acme-ops --name "Acme 运维" --apply
```

会写入 `~/.aiplat/ontologies/`（及可选 action/测试骨架）。**管理端无对应该按钮的调用点。**

### 2.5 注册业务动作（可选，但故障竖切需要）

动作合同不在「新建域」弹窗里一次填完，通常：

1. 准备 `customer_action` 命名空间的 Action YAML（可参考 `aiPlat-core/core/workspace_seeds/actions/`，如 `it_ops_alert_lifecycle.yaml`）。  
2. FDE 工作台使用 **注册动作**（或 `POST /api/platform/apps/fde/actions/from-yaml`）装入 ActionRegistry。  
3. 验证：AcceptTab / 动作卡片能看到分诊等按钮，且错误状态会 **blocked**。

---

## 3. FDE 工作台：客户绑定 + 真实层种图（不是建域）

路由：**AI 应用工厂 → FDE 工作台** → `/diagnostics/fde`。

| Tab | 操作员做什么 | 说明 |
|-----|--------------|------|
| ① 业务认知 | **新建** 客户 Profile | 建的是**客户**，不是本体 |
| ② 评估域 | 选择/推荐**已有**域 | 域须已在业务本体中存在 |
| ⑦ 验收移交 | 种演示图、点动作 | 见下表 |
| ⑧ 运营监控 | Evolve 批准/受控应用 | **配置** Evolve ≠ 本体提案 |

### 3.1 ⑦ 验收：种图与动作（已有域）

| 按钮（AcceptTab 一带） | 域 | 作用 |
|------------------------|-----|------|
| 创建演示告警 | it-ops | 路径 C 最小告警图 |
| 创建教学复杂拓扑 | it-ops | 路径 C 复杂教学图 |
| 导入样例告警JSON | it-ops | 路径 B JSON 入轨 |
| 导入表/CSV样例 | it-ops | 路径 B `source_type=table_map` |
| 创建治理教学图 | data-gov | 治理子集种子 |
| 创建演示工单 | lock-service | 锁服演示实体 |
| 本体三柱速览 | 指定域 | 只读 `GET …/ontology/pillars/{domain}` |
| 写入演示案例 / 加权检索 / 高分反馈 / 强制入队提案 / 回滚 | 指定域 | P0–P2 在线学习；入队后链到 **业务本体→工厂** `?tab=factory&domain=&proposal=` |
| ①b 代码/表头建议（工厂） | 指定域 | `code-suggestions` + **`schema-suggestions`**（表头→提案）；禁自动 apply；≠ Path B 写图 |

种图后：在动作卡片上执行 **分诊 / 挂疑似 / 确认根因** 等 → 走 `POST …/actions/execute` → ActionRegistry 硬门 → handler。  
Action 成功后会 **best-effort** 写回本体学习案例（`ontology_case_learning.record_case_from_action`），不改 live YAML。  
这是**正式执行通道**；「演示」仅指场景数据，不是旁路写库。

#### 3.1.1 在线学习 / 受控进化（API）

| 方法 | 路径 | 作用 |
|------|------|------|
| POST | `/api/platform/apps/fde/ontology/cases` | 写入案例（P0） |
| GET | `/api/platform/apps/fde/ontology/cases/search?domain_id=&q=` | 奖励加权检索（非 RL） |
| POST | `/api/platform/apps/fde/ontology/cases/{id}/feedback` | 人评写回；高回报可入队提案草稿 |
| POST | `/api/platform/apps/fde/ontology/cases/{id}/evolve` | 强制 enqueue 提案；**默认** `auto_apply=false`；仅当 `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY=true` 且 max_tier=edge 才可自动 apply |
| POST | `/api/platform/apps/fde/ontology/cases/{id}/rollback` | P2：回滚案例关联的已 apply 提案（恢复 apply 前快照） |
| POST | `/api/platform/apps/fde/ontology/proposals/{id}/rollback` | P2：按 proposal_id 回滚（body 需 `domain_id`） |
| GET | `/api/platform/apps/fde/ontology/cases/meta?domain_id=` | P2.5：UCB / EDGE_AUTO / case·serve·feedback 计数 |

| GET | `/api/platform/apps/fde/ontology/governance-loop` | 治理场景 8 步诚实对照（工厂/FDE⑦ 面板；禁材料 KPI） |
| GET | `/api/platform/apps/fde/ontology/governance/quality` | ⑥ 竖切：OCS + data-gov 闸2 动作 + 价值深链 |
| POST | `/api/platform/apps/fde/ontology/governance/locate` | ⑦ 竖切：GraphIndex 按业务词定位（可选 GraphRAG；非直连库） |
| POST | `/api/platform/apps/fde/ontology/governance/fetch` | Org L5 P1：实体沙箱取数（暂挂 fde；禁 live）；规范入口见 `POST …/org/connectors/fetch` |
| POST | `/api/platform/apps/fde/ontology/governance/write-preview` | Org L5 P1：写回 dry-run（默认 blocked） |

组织周闭环 / 签收准备（开跑、周报、八闸门、证据包、试算）→ 管理端 **`/org/pilot`**，手册 [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md)，签收包 [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)。本文不展开。

检索默认带 **UCB 探索项**（`AIPLAT_ONTOLOGY_CASE_UCB`，默认开）；命中案例会累加 `serve_count`（曝光）——只动排序，不是策略梯度 RL。

进化出口：默认仍是 **知识工厂** 批准 → `apply_proposal`；edge 自动 apply 必须显式开 env，且**禁止**升格 logic/core。

口令级逐步演示另见 [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md)；概念图说见 [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) 下篇 B3/B4。

### 3.2 FDE 里的「Agent 创建指南」

⑦ 中勾选 **Agent 创建指南** 只会把说明写进交付手册文案，**不会**在系统里创建 Agent。真正创建见第 4 节。

### 3.3 不要与「POC 操作手册」混淆

FDE ⑤ 一带卡片「POC 操作手册」指向**已归档** POC 注入剧本，与本文无关。企业本体 + Agent 交付以**本文**为准。

---

## 4. 创建 Agent

### 4.1 应用库 Agent（正确入口）

1. **AI 应用工厂 → Agent** → `/workspace/agents`（页标题多为「应用库 Agent」）。  
2. 点 **创建** → 填表提交。  
3. 或点 **从模板安装** → 选 seed → 安装。  

**API**：`POST /api/core/workspace/agents`；模板：`GET/POST …/workspace/agents/seeds…`  

**落盘**：`~/.aiplat/agents/` 下出现对应目录 / `AGENT.md`。

### 4.2 不要走错的地方

| 页面 | 为何不对 |
|------|----------|
| FDE 工作台 | 无创建 Agent 按钮（仅指南文案） |
| 平台设置 → 引擎 Agent | 列表/启停/执行；**页面未挂创建按钮** |
| 知识工厂 | 只管本体提案，不管 Agent |

---

## 5. 端到端验收清单

### 5.1 本体

- [ ] 业务本体 → 域管理 / 编辑器列表可见新 `domain_id`  
- [ ] `~/.aiplat/ontologies/{domain_id}.yaml` 存在且含类/关系  
- [ ] （可选）工厂提案状态为「已应用」  
- [ ] （可选）FDE ② 能选到该域；⑦ 种图或导入后实体可选  

### 5.2 动作

- [ ] ActionRegistry 能 `get` 到 `customer_action:…`  
- [ ] 合法状态执行成功；错误状态返回 blocked，图未乱改  

### 5.3 Agent

- [ ] `/workspace/agents` 列表出现新 Agent  
- [ ] `~/.aiplat/agents/` 有对应文件  
- [ ] （可选）在同页执行/启动一次  

---

## 6. 故障排查

| 现象 | 排查 |
|------|------|
| FDE 找不到「新建本体」 | 预期如此 → 去 **业务本体** |
| 新建域成功但 FDE ② 没有 | 刷新；确认 DomainRouter / 本体目录已加载；必要时重启 API |
| 域管理新建 404 | 确认前端已用 `/api/core/ontology/domains`；或改走 **编辑器** Publish 路径 |
| 种图失败 / 类未知 | 域 YAML 是否故障版词表；it-ops 种图前会对齐 `workspace_seeds/ontologies/it-ops.yaml` |
| 动作一直 blocked | 查实体 `state` 与动作 `required_state`；查 ACL 角色 Header |
| Agent 创建无入口 | 确认打开的是 **应用库 Agent** `/workspace/agents`，不是 FDE / 引擎 Agent |

---

## 7. 相关命令与文档

```bash
# 域脚手架
PYTHONPATH=aiPlat-core:. .venv/bin/python scripts/new_domain_scaffold.py \
  --domain-id <id> --name "<中文名>" --apply

# 场景相关单测（可选）
.venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_it_ops_alert_lifecycle.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_executable_ontology_phase_ae.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_case_learning.py \
  -q
```

| 文档 | 用途 |
|------|------|
| [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) | 30 分钟故障/治理演示口令 |
| [`FDE_PHASE5_CUSTOMER_ONBOARDING.md`](./FDE_PHASE5_CUSTOMER_ONBOARDING.md) | 新客户接入原则 |
| [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) | 说明书/真实层/动作概念与图说（v3.7） |
| [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) | 对外口径与非目标 |
| [`ORG_L5_RUNBOOK.md`](./ORG_L5_RUNBOOK.md) | it-ops 组织现场运行（含 `/org/pilot`） |
| [`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md) | it-ops 签收准备包 / 剧本（≠ FDE 交付签收单） |

---

## 8. UI 证据索引（防文档漂移）

| 入口 | 代码锚点 |
|------|----------|
| 菜单 业务本体 / FDE / Agent | `aiPlat-management/frontend/src/pageManifest.ts` |
| 新建域（域管理） | `…/Infra/Ontology/OntologyManager.tsx`（`WIKI_API=/api/core/ontology`） |
| 编辑器 Create domain | `…/OntologyEditor/index.tsx` → `/platform/apps/ontology-editor/domains` |
| 知识工厂 | `…/KnowledgeFactory/KnowledgeFactoryPage.tsx` |
| FDE 种图/动作/三柱/案例学习 | `…/Diagnostics/FdeDashboard.tsx` AcceptTab（含 `ontology/cases*`） |
| 组织试点 / 签收准备 | `…/Knowledge/OrgPilotPage.tsx`（`/org/pilot`） |
| 应用库 Agent 创建 | `…/Workspace/Agents/Agents.tsx` |
| 后端创建域（wiki） | `aiPlat-core/core/api/routers/wiki.py` → `POST /ontology/domains` |
| 后端创建域（editor） | `aiPlat-platform/apps/ontology_editor/api/domain_crud.py` |
