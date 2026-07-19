> ⚠️ **已归档** — 本文档为历史版本，API 引用可能已过期。最新文档请参见 [FDE 交付手册](../fde-delivery-manual.md)。

# FDE 命令行参考（v2.4）

> **受众**：FDE、平台运维、开发人员  
> **用途**：操作手册中标注 💻 的终端操作，均在此处详细说明  
> **前置**：core 服务运行中（`curl http://localhost:8000/api/core/health` 确认）

---

## 1. 种子数据注入

### 1.1 生成种子数据

```bash
# 生成单个域的种子数据 JSON
python3 scripts/seed_wiki.py --domain supply-chain

# 一次生成所有有模板的域（supply-chain / procurement-mvo / ship-design）
python3 scripts/seed_wiki.py --all
```

生成的文件在 `~/.aiplat/seed_data/{domain_id}.json`。
没有模板的域需要手动创建种子 JSON（结构见 §1.4）。

### 1.2 注入到引擎

```bash
# 确认服务在运行
curl http://localhost:8000/api/core/health | python3 -m json.tool

# 注入单个域
python3 scripts/ingest_seed.py --domain supply-chain

# 一次注入所有
python3 scripts/ingest_seed.py --all

# 指定自定义 URL
python3 scripts/ingest_seed.py --domain supply-chain --base-url http://192.168.1.100:8000
```

### 1.3 验证注入结果

```bash
# 检查实体和关系数量
curl http://localhost:8000/api/core/ontology/engine/graph-stats/supply-chain | python3 -m json.tool

# 期望输出示例：
# {"domain_id": "supply-chain", "entity_count": 42, "relation_count": 38, "wiki_pages": 15}

# 测试检索可用性
curl -X POST http://localhost:8000/api/core/wiki/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "有哪些供应商","collection_id":"supply-chain","top_k": 5}'
```

### 1.4 手动创建种子 JSON（无模板时）

```json
{
  "domain_id": "my-domain",
  "entities": [
    {
      "class": "MyEntity",
      "name": "示例实体",
      "description": "这是一个示例",
      "properties": {}
    }
  ],
  "relations": []
}
```

通过 API 直接注入：

```bash
curl -X POST http://localhost:8000/api/core/ontology/engine/ingest-seed \
  -H "Content-Type: application/json" \
  -d @~/.aiplat/seed_data/my-domain.json
```

---

## 2. 域诊断与查询

### 2.1 查看域成熟度

```bash
curl http://localhost:8000/api/core/diagnostics/capability-boundary?domain=supply-chain | python3 -m json.tool
```

### 2.2 Golden Query 评测

```bash
curl -X POST http://localhost:8000/api/core/wiki/golden-queries/run \
  -H "Content-Type: application/json" \
  -d '{"domain":"supply-chain"}'
```

### 2.3 反馈历史查询

```bash
# 按客户和步骤筛选
curl "http://localhost:8000/api/core/fde/feedback/history?customer=江苏锁安&step=customers" | python3 -m json.tool

# 最近 50 条
curl "http://localhost:8000/api/core/fde/feedback/history?limit=50" | python3 -m json.tool
```

---

## 3. Agent 与 Workflow 运维

### 3.1 确认 Agent 已注册

```bash
grep "fde_business_analyst\|fde_solution_architect\|fde_delivery_engineer\|fde_delivery_manager" ~/.aiplat/logs/core.log
```

期望：每个 Agent 至少有 1 行命中。WARNING 级别表示已加载但部分配置不完整。

### 3.2 确认 Skill 已注册

```bash
ls aiPlat-core/core/engine/skills/customer_profile_creator/SKILL.md \
   aiPlat-core/core/engine/skills/domain_assessor/SKILL.md \
   aiPlat-core/core/engine/skills/package_builder/SKILL.md \
   aiPlat-core/core/engine/skills/acceptance_checker/SKILL.md
```

### 3.3 架构守卫

```bash
bash scripts/architecture_guard.sh
```

---

## 4. 打包部署

```bash
# 通过 API 触发后台打包
curl -X POST http://localhost:8000/api/core/fde/package
# 返回 {"task_id": "pkg-xxxxxxxx", "status": "running"}

# 轮询任务状态
curl http://localhost:8000/api/core/fde/package/pkg-xxxxxxxx

# 下载部署包
curl -O http://localhost:8000/api/core/fde/package/pkg-xxxxxxxx/download
```

---

## 5. 创建新域

### 5.1 域本体 YAML 模板

```yaml
name: "域名称"
namespace: "http://aiplat.local/ontology/domain-id/"
version: "1.0.0"
description: "域描述"

classes:
  EntityName:
    label: 实体中文名
    required_fields: [name, description]
    optional_fields: [category, tags]
    categories: [domain-id]
```

保存到 `~/.aiplat/ontologies/{domain_id}.yaml`。

### 5.2 注册域

编辑 `~/.aiplat/ontologies/registry.json` 的 `domains` 对象：

```json
"domain-id": {
  "name": "域名称",
  "description": "域描述",
  "ontology_file": "domain-id.yaml",
  "collection_id": "domain-id",
  "namespace": "http://aiplat.local/ontology/domain-id/",
  "min_wiki_score": 0.3,
  "expand_subclasses": false,
  "system_prompt_id": "domain-prompt-domain-id",
  "min_cross_results": 3
}
```

或通过 API 热加载：

```bash
curl -X POST http://localhost:8000/api/core/ontology/domains \
  -H "Content-Type: application/json" \
  -d '{"id":"domain-id","name":"域名称","namespace":"http://aiplat.local/ontology/domain-id/","ontology_file":"domain-id.yaml"}'
```

---

> **最后更新**：2026-07-15 (v2.4)  
> **维护者**：aiPlat 平台团队
