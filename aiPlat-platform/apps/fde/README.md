# FDE（platform apps）— 部署说明

- **授权**：`docs/decisions/products/five-products/ADR09_NEXT_FDE_DECISION.md`（#448）  
- **边界**：`docs/decisions/products/five-products/ADR09_FDE_BOUNDARY.md`  
- **默认**：**与控制面共部署**（本目录 API 挂在 platform 进程）  
- **ADR-09**：FDE 已立项为单产品**正式可选**独立部署 — **非**强制把生产默认从共置改为独立  
- **不含**：强制生产默认长驻；本体 / 控制面拆；第二套 `acceptance/signoff`；E4  
- **可选长驻（F11 Accepted）**：`packages/aiplat-fde/compose.fde-long-running.yml`

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
# 起薄 health → curl → 立刻停；不暴露第二套 signoff
# 同时校验 /healthz（V2 D1：status/product_id）
bash scripts/adr09_fde_optional_phase_health.sh
```

## 可选 compose 长驻（BOUNDARY D / F11）

```bash
# 正式可选；≠ 强制生产默认；签收仍在控制面
cd packages/aiplat-fde
docker compose -f compose.fde-long-running.yml up -d
curl -fsS http://127.0.0.1:18766/health
docker compose -f compose.fde-long-running.yml down -v

# 烟测（必 down -v）
bash scripts/adr09_compose_fde_long_running_smoke.sh
```

授权：`docs/decisions/products/five-products/ADR-FDE-COMPOSE-LONG-RUNNING.md`。  
≠ Field 卷/DB 包（`ADR-DRAFT-fde-field-compose` 仍 Draft）。

## V2 现场范围 / A1 契约

- 现场范围：`docs/products/five-products/modules/fde/FIELD_SCOPE.md`
- 契约：`docs/products/five-products/modules/fde/contracts/`（`validate_sample.py`）
- Field D1 ADR（**未 Accepted**）：`docs/decisions/products/five-products/ADR-DRAFT-fde-field-deploy.md`

业务手册（现场交付 SOP）见仓库 `docs/manuals/fde/`，与本部署说明分工不同。
