# aiPlatform 知识库本体系统 — 接入指引

> 快速上手：从零到可用的完整工作流

---

## 场景一：知识库构建（文档入库 → 检索）

### 1.1 入库文档

```bash
# 上传 PDF 到知识库
curl -X POST http://localhost:8003/api/v1/documents/ingest \
  -H "X-Aiplat-API-Key: your_api_key" \
  -F "file=@supply_chain_report.pdf" \
  -F "collection_id=default"

# 响应
{ "job_id": "job_abc123", "doc_id": "doc_7f3a2b", "status": "processing" }
```

入库自动触发：PDF 解析 → chunk → embed → FTS5 索引 → `wiki_auto_update()` 生成 Wiki 页面。

### 1.2 统一检索

```bash
# Wiki 优先 + KB 回退，带安全过滤
curl "http://localhost:8003/api/v1/knowledge/retrieve?q=轴承库存&actor_scopes=kb:read"
```

内部流程：`Ontology Query Mapper` 改写查询 → Wiki 检索 → KB 回退 → 分数归一化 → Marking 安全过滤 → 返回。

---

## 场景二：本体管理（创建 → 验证 → 演化）

### 2.1 查看本体健康

```bash
curl "http://localhost:8003/ontology/health/score"
# { "axiom_score": 85, "violations": { "error": 0, "warning": 2 }, "total_triples": 256 }
```

### 2.2 查看知识盲区

```bash
curl "http://localhost:8003/ontology/health/triggers"
# { "triggers": [
#   { "type": "full_curation", "reason": "5 concepts lack source documents" }
# ]}
```

### 2.3 生成演化建议

```bash
# Tier 1 (规则) + Tier 2 (LLM)
curl -X POST "http://localhost:8003/ontology/suggestions/semantic" \
  -d '{"include_llm": true, "max_suggestions": 5}'
# { "suggestions": [
#   { "type": "merge_classes", "description": "合并 'Machine Learning' 和 '机器学习'", "confidence": 0.92 }
# ]}
```

### 2.4 接受演化建议

```bash
curl -X POST "http://localhost:8003/ontology/suggestions/sug_001/accept"
# → 生成代码 diff → 人工审核 → 合并
```

---

## 场景三：安全配置（Markings → 权限 → 脱敏）

### 3.1 设置 Marking（血缘传播）

```bash
# 标记 confidential 实体 — 自动沿 cites/parentOf/hasSource 传播
curl -X PUT "http://localhost:8003/ontology/markings" \
  -d '{"entity_uri": "...轴承库存", "label": "confidential", "level": 3}'
```

### 3.2 查看传播效果

```bash
curl "http://localhost:8003/ontology/markings/...轴承库存"
# { "explicit_markings": [{"label":"confidential","level":3}],
#   "effective_markings": [...],       ← 包含传播来的标记
#   "inherited_traces": [...] }        ← 溯源链
```

### 3.3 三层权限检查

```bash
# Layer1 RBAC → Layer2 Marking → Layer3 Per-object
curl "http://localhost:8003/ontology/permissions/...轴承库存"
# → deny: "Layer2-Marking: requires scope kb:read:confidential"
```

### 3.4 字段级脱敏

```bash
curl -X PUT "http://localhost:8003/ontology/field-permissions" \
  -d '{"entity_uri": "...供应商评估", "field_name": "body",
       "visibility": "scope:kb:read:internal", "redaction_strategy": "mask"}'
# body: "供应***签约"  ← 自动脱敏
```

---

## 场景四：Pipeline 执行（MRP 场景）

### 4.1 查看可用场景

```bash
curl "http://localhost:8003/ontology/scenes"
# ["supply_chain_mrp", "order_validation", "knowledge_curation", "personal_learning_coach"]
```

### 4.2 实例化场景为 Pipeline

```bash
curl -X POST "http://localhost:8003/ontology/scenes/supply_chain_mrp/instantiate" \
  -d '{"gross_demand": 800, "on_hand_inventory": 200, "safety_stock": 50}'
# → PipelineConfig: 2 algorithm nodes + 1 LLM judgment node
```

### 4.3 执行确定性算法节点

```python
# algorithm_node.py 内置算法
execute_algorithm("mrp_net_demand", {"gross_demand": 800, "on_hand_inventory": 200, "safety_stock": 50})
# → { net_requirement: 650, needs_planned_order: true, execution_time_ms: 0.0 }
```

### 4.4 验证输出

```bash
# 预期结果校验 + 回放一致性
curl "http://localhost:8003/ontology/verify" ...
# { verified: true, checks_passed: 3/3, replay_consistent: true }
```

---

## 场景五：AI 学习教练

### 5.1 创建学习画像

```bash
curl -X POST "http://localhost:8003/learning/profile" \
  -d '{"learner_id": "zhangsan", "target_role": "ai_literate",
       "current_level": "beginner", "weekly_hours": 3,
       "goals": "半年内成为 AI 通识人才"}'
```

### 5.2 查看学习路径

```bash
curl "http://localhost:8003/learning/paths"
# ai_literate (5章, 4.8h) | ai_decision_maker (6章, 6.2h) | ai_engineer (8章, 10.5h)
```

### 5.3 开始学习

```bash
curl -X POST "http://localhost:8003/learning/start" \
  -d '{"learner_id": "zhangsan", "path_id": "ai_literate"}'
# → 返回第1章内容 + 章节骨架 + 习题列表
```

### 5.4 提交作业

```bash
curl -X POST "http://localhost:8003/learning/chapter/lit_intro/complete" \
  -d '{"learner_id": "zhangsan", "answers": [1, "大语言模型是生成内容的AI..."]}'
# → { average_score: 85, results: [{score:100,passed:true}, {score:70,passed:true}] }
```

### 5.5 查看进度

```bash
curl "http://localhost:8003/learning/progress/zhangsan"
# { progress: "1/5", completion_pct: 20, radar: [...], mastery_average: 85 }
```

### 5.6 向教练提问

```bash
curl -X POST "http://localhost:8003/learning/ask" \
  -d '{"learner_id": "zhangsan", "question": "什么是 Chain-of-Thought？"}'
# → 教练结合学习进度给出定制回答
```

---

## 场景六：外部集成

### 6.1 Obsidian 可视化

```bash
# 直接打开知识库目录
open ~/.aiplat/wiki/collections/default
# Obsidian → Open folder as vault → 选择上述路径
# 44 个 .md 文件自动生成双向链接图谱
```

### 6.2 注册写回目标

```bash
curl -X POST "http://localhost:8003/ontology/writebacks" \
  -d '{"target_type": "rest_webhook",
       "target_endpoint": "https://crm.internal/api/ai-sync",
       "trigger_actions": ["create", "update"]}'
```

### 6.3 知识增长指标

```bash
curl "http://localhost:8003/ontology/growth-stats?days=30"
# { deltas: { pages: +15, cross_links: +34 }, metrics: { pages_per_day: 0.5 } }
```

---

## 环境变量参考

| 变量 | 默认值 | 说明 |
|------|------|------|
| `AIPLAT_HOME` | `~/.aiplat` | 数据根目录 |
| `AIPLAT_WIKI_BOOST` | `1.1` | Wiki 检索提权系数 |
| `AIPLAT_WIKI_SCHEMA_MODE` | `warning` | Schema 校验模式 (warning/error/off) |
| `AIPLAT_GIT_ENABLED` | `false` | Pipeline 阶段自动 git commit |
| `AIPLAT_ENABLE_REPLAY` | `false` | LLM 阶段启用回放快照 |
| `AIPLAT_EMBED_BACKEND` | `hash` | 嵌入后端 (hash/transform/api) |
