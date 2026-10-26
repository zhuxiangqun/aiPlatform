# aiPlat-platform — 控制面部署说明

- **授权**：`reports/five-products/ADR09_NEXT_CONTROL_PLANE_DECISION.md`（#458）  
- **边界**：`reports/five-products/ADR09_CONTROL_PLANE_BOUNDARY.md`  
- **默认**：**共部署控制面**（本仓库挂载 apps + Identity / Policy 入口）  
- **ADR-09**：控制面已立项为单产品**正式可选**独立部署 — **非**强制把生产默认从共置改为独立  
- **不含**：compose 长驻；第二 Identity / PolicyGate；超边界 E4

## 权威真源

| 项 | 值 |
|----|-----|
| Identity / Policy 生产者 | aiPlat（ADR-02）；`require_auth` / `_resolve_identity` / PolicyGate |
| Apps 注册 | `registry/apps.yaml` |
| 权限执行 | PolicyGate 唯一执行点（禁止平行门禁） |

## 正式可选（BOUNDARY B）

```bash
# 复制示例 env（可选独立控制面进程时使用；共部署可不拷）
cp control_plane_optional.env.example .env.control-plane-optional

# 生产默认仍为共置；独立进程健康探针见 BOUNDARY C
# 回滚：停独立进程 → 切回共部署；Identity 权威不变
```
