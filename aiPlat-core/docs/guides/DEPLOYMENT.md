# 核心层部署指南（As-Is 对齐 + To-Be 示例）

> 说明：本文档包含 To-Be 的平台化部署示例（make/k8s/config 文件），当前仓库未必包含完整部署工件；请以代码与实际部署仓库为准。

> 继承系统级部署指南，针对核心层的特定要求

---

## 继承规范

本文档继承系统级部署指南（若存在上层仓库/平台仓库），所有系统级规范在本层必须遵守。

---

## 部署顺序

核心层部署顺序：

```
┌─────────────────┐
│ 1. 基础设施层    │  已部署：数据库、消息队列、向量存储
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 核心配置      │  Agent 配置、Skill 配置、模型配置
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 核心服务      │  CoreFacade、Agent 执行器、Skill 执行器
└─────────────────┘
```

---

## 部署命令

```bash
# To-Be 示例（需以实际部署仓库/CI 为准）
# make deploy-core ENV=dev
# kubectl apply -f k8s/core/base/
# kubectl apply -f k8s/core/overlays/prod/
```

---

## 配置管理

### Agent 配置（To-Be 示例）

```yaml
# config/core/agents.yaml
agents:
  - name: chat-assistant
    type: chat
    model: gpt-4
    skills:
      - knowledge-search
      - web-search
    memory:
      type: sliding-window
      max_tokens: 4000
```

### Skill 配置（To-Be 示例）

```yaml
# config/core/skills.yaml
skills:
  - name: knowledge-search
    type: retrieval
    knowledge_base: default
    top_k: 5
  
  - name: web-search
    type: tool
    tool_type: search
```

---

## 健康检查（To-Be 示例）

```python
@router.get("/health/ready")
async def readiness_check():
    """核心层就绪检查"""
    checks = {
        "database": await check_database(),
        "llm": await check_llm(),
        "vector": await check_vector(),
    }
    
    all_healthy = all(checks.values())
    
    if not all_healthy:
        return Response(
            content=json.dumps({"status": "not ready", "checks": checks}),
            status_code=503
        )
    
    return {"status": "ready", "checks": checks}
```

---

## 监控指标（To-Be 示例）

---

## 证据索引（Evidence Index｜抽样）

- As-Is 服务入口：`core/server.py`
- To-Be：部署工件（k8s/make/config）需由 platform/ops 仓库提供并纳入验收

```python
# 核心层特有指标
agent_executions_total = Counter(
    'agent_executions_total',
    'Agent executions',
    ['agent_type']
)

agent_execution_duration = Histogram(
    'agent_execution_duration_seconds',
    'Agent execution duration',
    ['agent_type'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120]
)

skill_executions_total = Counter(
    'skill_executions_total',
    'Skill executions',
    ['skill_name']
)
```

---

## 部署检查清单

### 部署前检查

- [ ] 基础设施层已部署
- [ ] Agent 配置完成
- [ ] Skill 配置完成
- [ ] 模型配置完成

### 部署后检查

- [ ] 所有 Pod 运行正常
- [ ] 健康检查通过
- [ ] Agent 可正常执行
- [ ] Skill 可正常调用
- [ ] 监控指标正常

---

## 相关链接

- [系统级部署指南](../../../docs/guides/DEPLOYMENT.md)
- [core层开发规范](./DEVELOPMENT.md)

---

*最后更新: 2026-04-14*
