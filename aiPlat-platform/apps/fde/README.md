# FDE（platform apps）— 部署说明

- **授权**：`reports/five-products/ADR09_NEXT_FDE_DECISION.md`（#448）  
- **边界**：`reports/five-products/ADR09_FDE_BOUNDARY.md`  
- **默认**：**与控制面共部署**（本目录 API 挂在 platform 进程）  
- **ADR-09**：FDE 已立项为单产品**正式可选**独立部署 — **非**强制把生产默认从共置改为独立  
- **不含**：compose 长驻；本体 / 控制面拆；第二套 `acceptance/signoff`

## 路由真源

| 项 | 值 |
|----|-----|
| 注册前缀 | `/api/platform/apps/fde`（`registry/apps.yaml`） |
| HTTP | `aiPlat-platform/apps/fde/api/` |
| 签收唯一入口 | `POST …/fde/acceptance/signoff` |

## 正式可选（BOUNDARY B）

```bash
# 复制示例 env（可选独立进程时使用；共部署可不拷）
cp fde_optional.env.example .env.fde-optional

# 生产默认仍为控制面共置挂载本模块
# 回滚：停独立进程 → 切回共部署；签收入口不变
```

## One-shot health（BOUNDARY C）

```bash
# 起薄 health → curl → 立刻停；非 compose 长驻；不暴露第二套 signoff
bash scripts/adr09_fde_optional_phase_health.sh
```

业务手册（现场交付 SOP）见仓库 `docs/manuals/fde/`，与本部署说明分工不同。
