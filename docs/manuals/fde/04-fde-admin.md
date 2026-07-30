# FDE 管理与扩展

> ← [文档导航](README.md)

> **目标角色**：需要扩展 FDE 系统的管理员 / 高级工程师  
> **前置**：熟悉 [02 - 交付操作手册](./02-fde-delivery.md)

---

## 一、创建新 Agent

FDE 团队可以通过 AI 辅助快速创建交付专用的 Agent。

### 1.1 快速创建

1. 进入管理端 → **打开 /core/agents（Agent 管理页面）** → 点击 **[+ 新建 Agent]**
2. 填写基本信息：
   - Agent ID（如 `custom_poc_agent`）
   - 显示名称
   - 描述
3. 点击 **AI 智能填充** → 系统自动生成完整的 `AGENT.md`：
   - 角色描述和 SOP
   - 推荐绑定的 Skill 和 Tool
   - pipeline 配置（field、写入键、读取上游键）
4. 审查生成的 `AGENT.md`，调整 frontmatter 字段
5. 绑定所需的 Skill 和 Tool
6. 切换状态为 `ready`

### 1.2 AGENT.md 关键字段

```yaml
---
id: custom_poc_agent
display_name: 定制 POC Agent
description: 为特定行业客户生成 POC 方案
model: qwen2.5-coder:7b
temperature: 0.3
status: ready
skills: [poc_data_inject, customer_profile_creator]
tools: [knowledge_retrieve, file_write]
pipeline_config:
  output_artifact: pocProfile
  depends_on: [domain]
---
```

### 1.3 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| Agent 状态为 `draft` | 未手动切换 | AGENT.md → 改 `status: ready` |
| Agent 不显示在列表中 | SKILL.md 未注册 | 检查 `~/.aiplat/skills/` 下的 SKILL.md |
| 执行时报 "Model not found" | model 字段值在 ModelManager 中不存在 | 检查 `aiPlat-infra/config/infra/llm_profile.yaml` |
| bound skills 不生效 | SKILL.md frontmatter 语法错误 | 检查 YAML 格式（缩进用 2 空格） |

---

## 二、创建 Workflow

FDE 支持的 Workflow 仅需 4 种节点，用于编排 Agent 的自动流转。

### 2.1 快速创建

1. 管理端 → **打开 /core/workflows（Workflow 管理页面）** → 点击 **[+ 新建]**
2. 输入 Workflow 名称和描述
3. 添加节点（4 种类型）：
   - **start** — 工作流入口，输入 JSON payload
   - **agent** — 调用指定 Agent
   - **condition** — 条件分支（按 field 值路由）
   - **end** — 终止点
4. 连线：从 start → agent → condition → … → end
5. 点击 **[测试运行]**
6. 提交审批

### 2.2 节点示例

```yaml
nodes:
  - id: start
    type: start
  - id: ba
    type: agent
    agent_id: fde_business_analyst
  - id: check
    type: condition
    field: diagnosis.status
    branches:
      ready: sa
      retry: ba
  - id: sa
    type: agent
    agent_id: fde_solution_architect
  - id: end
    type: end
```

### 2.3 审批流程

| 步骤 | 谁做 | 多久 |
|------|------|:---:|
| FDE 创建 Workflow | FDE | 1 天 |
| 提交审批 | FDE → 管理员 | — |
| 审批 | 管理员 | 1 天 |
| 发布 | 管理员 | — |

---

## 三、CLI 命令速查

> 以下所有命令均基于实际可用的 HTTP API 端点。API base 默认为 `http://localhost:8003/api/platform`。

### 3.1 种子数据

```bash
# 种子数据注入请通过 FDE 工作台操作：
# 进入 ④ POC Tab → 加载行业模板 → 快速数据注入
# 或通过 API 注入演示数据
curl -X POST "http://localhost:8003/api/platform/apps/fde/poc/inject" \
  -H "Content-Type: application/json" \
  -d '{"profile": "poc-general", "namespace": "demo"}'
```

### 3.2 反馈查询

```bash
# 查看所有反馈历史
curl "http://localhost:8003/api/platform/apps/fde/feedback/history"

# 按客户过滤诊断会话
curl "http://localhost:8003/api/platform/apps/fde/sessions?company=客户名"

# 查看某次诊断的详细时间线（含反馈记录）
curl "http://localhost:8003/api/platform/apps/fde/sessions/session_xxx/timeline"
```

### 3.3 Agent 日志分析

```bash
# Agent 执行日志请在 FDE 工作台 → ⑧ 运营监控 Tab 的诊断面板中查看
# 系统级告警可通过以下 API 获取
curl "http://localhost:8003/api/platform/apps/fde/alerts?min_severity=warning"
```

### 3.4 部署打包

```bash
# 标准打包（online/hybrid）
curl -X POST "http://localhost:8003/api/platform/apps/fde/package" \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "客户名"}'

# airgap 打包（含模型文件）
curl -X POST "http://localhost:8003/api/platform/apps/fde/package" \
  -H "Content-Type: application/json" \
  -d '{"customer_name": "客户名", "deployment_mode": "airgap"}'
```

### 3.5 离线部署

```bash
# 在客户环境执行安装
tar -xzf deploy-客户名.tar.gz
bash install.sh
```

### 3.6 系统状态

```bash
# 查看系统整体健康（含自演进组件状态）
curl "http://localhost:8003/api/platform/apps/fde/health"

# 手动触发全系统自检
curl -X POST "http://localhost:8002/api/core/system/self-check"

# 查看知识图谱统计
curl "http://localhost:8002/api/core/knowledge-graph/stats"
```

---

## 四、API 端点快速参考

### FDE Platform API (`/api/platform/apps/fde/`)

| 端点 | 方法 | 功能 |
|------|:--:|------|
| `/fde/dashboard` | GET | 运营仪表板 |
| `/fde/sessions` | GET | 诊断会话列表（支持 `?company=X` 按客户过滤） |
| `/fde/validate` | GET | 8 项 E2E 测试 |
| `/fde/health` | GET | 6 维健康检查 |
| `/fde/trends` | GET | 趋势分析 |
| `/fde/search` | GET | 全文搜索 |
| `/fde/ask` | POST | 诊断追问 |
| `/fde/overview` | GET | 系统自描述 |

### System API (`/api/core/system/`)

| 端点 | 方法 | 功能 |
|------|:--:|------|
| `/system/diagnose` | GET | 主动诊断 |
| `/system/heal` | POST | 自动修复 |
| `/system/evolve` | GET | 演化循环 |
| `/system/self-check` | POST | 全周期自检 |

### 快速验证脚本

```bash
#!/bin/bash
# 一键检查所有 FDE 相关服务
for ep in \
  /api/platform/apps/fde/health \
  /api/platform/apps/fde/sessions \
  /api/platform/apps/fde/dashboard \
; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:8002$ep")
  echo "$ep: $code"
done

---

## 十、本体引擎集成

### 10.1 域成熟度监控

- 成熟度评分由 `domain_maturity.py` 自动计算（6 维：实体/Wiki/技能/通过率/密度/评测）
- 查看路径：本体编辑器 → Scenarios tab → 域对比表
- API: `GET /api/platform/apps/ontology-editor/scenarios/compare`

### 10.2 场景优先级排序

- `scenario_selector` 基于 5 条件 + 4 象限自动推荐域构建顺序
- 查看路径：本体编辑器 → Scenarios tab → 推荐列表
- API: `GET /api/platform/apps/ontology-editor/scenarios/recommend`

### 10.3 评分引擎告警

- `scoring_engine` 基于累加加权规则自动产生风险/机会告警
- 查看路径：本体编辑器 → Monitor tab → SLA Violations + Scoring Alerts
- API: `GET /api/platform/apps/ontology-editor/scoring-models/{name}/alerts`

### 10.4 推理路径编排

- `ontology_agent` 通过 `sys_ontology_reason` 执行 5 步推理流水线
- 集成在 FDE field_assessment 和 domain_assessor 中
- 输出包含 reasoning_trace 可审计推理链
```
