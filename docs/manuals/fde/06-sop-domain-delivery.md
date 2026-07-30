# 06 — 从 0 到 1 交付一个新域 (SOP)

**定位**：FDE 标准操作手册——任何一个合格工程师按此 SOP，在 5 个工作日内完成新域端到端交付。

---

## 交付路线图

```
Day 1           Day 2           Day 3           Day 4           Day 5
① 业务认知 ──→ ② 评估域 ──→ ③ 问题重构 ──→ ④ 验证价值
                                    │
                                    ▼
                              ⑤ 快速构建 ──→ ⑥ 评测护栏
                                    │
                                    ▼
                              ⑦ 验收移交 ──→ ⑧ 运营监控
```

### 前置条件

- aiPlat 已部署（`./start.sh` 全部服务 running）
- FDE 工作台可访问（`http://localhost:5173/diagnostics`）
- 目标客户的业务专家已安排访谈时间

### 参考模板

新域交付最快捷方式是复制 `service-domain` 参考实现：

```bash
cp ~/.aiplat/ontologies/service-domain.yaml ~/.aiplat/ontologies/{新域}.yaml
cp ~/.aiplat/actions/service-domain_actions.yaml ~/.aiplat/actions/{新域}_actions.yaml
cp custom_handlers/service_handlers.py custom_handlers/{新域}_handlers.py
cp ~/.aiplat/tests/service-domain_tests.yaml ~/.aiplat/tests/{新域}_tests.yaml
```

然后按本文档 Day 1-5 步骤逐项修改为客户的业务内容。

---

## Day 1：业务认知（定义本体）

**目标**：把客户的业务世界翻译成 aiPlat 能理解的本体。

### Step 1.1：业务调研（2 小时）

和客户业务负责人访谈，回答三个问题：

| 问题 | 产出 | 示例（售后服务域） |
|:---|:---|:---|
| 有哪些对象？ | 实体列表 | 客户、工单、技师、故障类型、备件 |
| 对象之间什么关系？ | 关系列表 | 客户→提交→工单，工单→指派→技师 |
| 对象有哪些状态？ | 状态机草图 | 工单：待指派→已指派→维修中→待验收→已完成 |

**交付物**：白板照片或 Miro 图。

### Step 1.2：编写本体 YAML（3 小时）

参考 `~/.aiplat/ontologies/service-domain.yaml`，编辑新域的本体文件：

- `classes`：每个实体一个 key，含 `required_fields`、`optional_fields`、`states`
- `object_properties`：每个关系含 `name`、`from`、`to`
- `inference_rules`：定义 `exclusive_states`（互斥状态）和 `state_dependencies`（状态依赖）

### Step 1.3：加载并验证（1 小时）

```bash
# 验证语法
python3 -c "from core.harness.knowledge.ontology_loader import load_ontology_from_yaml; load_ontology_from_yaml('~/.aiplat/ontologies/{domain}.yaml')"

# 种子数据
python3 scripts/quick_seed.py --domain {domain}
```

**验证标准**：FDE 工作台 ① 业务认知 中能看到新域的名称、实体列表。

---

## Day 2：评估域（验证本体）

**目标**：用真实数据验证本体能否承载业务查询。

### Step 2.1：导入样例数据（2 小时）

准备 10-20 条真实业务数据（从客户处获取脱敏数据），以 JSON 格式存入 `~/.aiplat/seed_data/{domain}.json`，然后：

```bash
python3 scripts/quick_seed.py --domain {domain}
```

### Step 2.2：测试查询（2 小时）

在 ② 评估域 中测试 5 类典型问题：事实型、关系型、时序型、推理型、聚合型。

### Step 2.3：修正本体（2 小时）

根据查询结果迭代修正本体——补漏的属性、调整的关系、新增的状态。

**验证标准**：所有典型查询返回正确结果。

---

## Day 3：问题重构 + 快速构建

**目标**：把查询能力升级为执行能力。

### Step 3.1：定义动作（3 小时）

参考 `~/.aiplat/actions/service-domain_actions.yaml`，注册 3-5 个核心动作。每个动作包含：

- `action_id`、`label`：唯一标识和显示名
- `scope`、`domain_id`、`target_class`：实体约束
- `required_state`、`forbidden_states`：状态约束
- `effect_semantics`、`compensation`：语义说明
- `handler`：`"custom_handlers.{domain}_handlers:{function}"`
- `input_schema`：JSON Schema 格式的输入参数

### Step 3.2：实现 Handler（2 小时）

```python
# custom_handlers/{domain}_handlers.py
async def my_action(entity: dict, params: dict, actor: str = "") -> dict:
    from core.harness.ontology_engine.graph_index import GraphIndex
    g = GraphIndex.load("{domain}")
    # 更新状态、写入属性、创建关系
    return {"new_state": "目标状态", ...}
```

### Step 3.3：注册并测试（1 小时）

```bash
python3 -c "
from core.harness.infrastructure.action_contract import ActionContractModel
from core.harness.ontology_engine.action_registry import get_action_registry
contracts = ActionContractModel.from_yaml_batch('~/.aiplat/actions/{domain}_actions.yaml')
get_action_registry().register_batch(contracts)
print('Actions registered')
"

curl -X POST http://localhost:8003/api/platform/apps/actions/execute \
  -d '{"action_id":"{action_id}","entity_id":"{entity_id}","params":{...}}'
```

**验证标准**：动作执行返回 `{"status":"executed"}`。

---

## Day 4：评测护栏

**目标**：建立评估体系，确保 AI 安全可靠。

### Step 4.1：定义测试集（2 小时）

编写 `~/.aiplat/tests/{domain}_tests.yaml`，覆盖正常流程、边界条件和错误场景。

### Step 4.2：RuleValidator 检查（1 小时）

确认 `inference_rules` 中的互斥状态和状态依赖正常工作：

```bash
python3 -c "
from core.harness.infrastructure.rule_validator import RuleValidator
v = RuleValidator('{domain}')
# 测试互斥状态
print(v.check_transition('test', '已完成', '待指派'))
# 测试正常允许
print(v.check_transition('test', '待指派', '已指派'))
"
```

### Step 4.3：补充规则（2 小时）

根据测试结果补充 `inference_rules`，迭代直到通过率 ≥ 95%。

---

## Day 5：验收移交 + 运营监控

**目标**：系统可上线，业务方可自主运营。

### Step 5.1：培训业务管理员（2 小时）

教会业务方三件事：
1. 怎么提新动作：写 YAML → POST `/actions/from-yaml`
2. 怎么看审计日志：⑧ 运营监控 → 筛选时间/动作/状态
3. 怎么提本体演进：① 业务认知 → 本体演进面板 → 提交提案

### Step 5.2：正式上线（2 小时）

```bash
# 备份配置
tar -czf {domain}_backup_$(date +%Y%m%d).tgz ~/.aiplat/ontologies/{domain}*.yaml ~/.aiplat/actions/{domain}*.yaml

# 运行全量验证
python3 scripts/sop_validate.py --domain {domain}
```

### Step 5.3：交付检查清单

| 检查项 | 状态 |
|:---|:---|
| 本体 YAML 存在且语法正确 | ☐ |
| ① 业务认知 显示新域 | ☐ |
| 10+ 条样例数据已导入 | ☐ |
| 3+ 个动作已注册 | ☐ |
| RuleValidator 互斥状态正常 | ☐ |
| 动作执行返回 executed | ☐ |
| 业务方完成培训 | ☐ |
| ⑧ 运营监控 有实时日志 | ☐ |

---

## 核心原则

**每一个新域的交付，都是对平台的压力测试。** 每个域的特殊性都会暴露平台的缺口，这些缺口应该被修复回平台本身，而不是让下一个域再踩一遍。FDE 工作台 ①~⑧ 不是一条单向的交付流水线，而是一个让平台持续生长的闭环。
