# Ontology editor（platform apps）— 部署说明

- **授权**：`reports/five-products/ADR09_NEXT_ONTOLOGY_DECISION.md`（#453）  
- **边界**：`reports/five-products/ADR09_ONTOLOGY_BOUNDARY.md`  
- **默认**：**与控制面共部署**（本目录 API 挂在 platform 进程；DomainRouter 在 core）  
- **ADR-09**：本体已立项为单产品**正式可选**独立部署 — **非**强制把生产默认从共置改为独立  
- **不含**：compose 长驻；控制面拆；第二套域 `registry.json`

## 路由 / 配置真源

| 项 | 值 |
|----|-----|
| 注册前缀 | `/api/platform/apps/ontology-editor`（`registry/apps.yaml`） |
| HTTP | `aiPlat-platform/apps/ontology_editor/api/` |
| 配置权威 | `$AIPLAT_HOME/ontologies/{domain_id}.yaml` + `registry.json`（经 `DomainRouter`） |

## 正式可选（BOUNDARY B）

```bash
# 复制示例 env（可选独立进程时使用；共部署可不拷）
cp ontology_optional.env.example .env.ontology-optional

# 生产默认仍为控制面共置；独立进程健康探针见 BOUNDARY C
# 回滚：停独立进程 → 切回共部署；配置权威不变
```
