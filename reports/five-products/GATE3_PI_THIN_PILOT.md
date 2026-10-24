# Gate3 试点边界：Pi Thin 独立部署

> **批准**：`GATE3_DECISION.md` G3-1  
> **场景**：`fp-customer-lock-service-bundle-pi-diag-001`  
> **非目标**：拆 aiPlat 控制面 / 诊断中台 / 五产品全拆

## 1. 目标

验证 Pi Thin **执行宿主**可在与 aiPlat 控制面**进程分离**的情况下：

1. 加载已签名/已导出 Bundle；  
2. 使用**独立运行密钥/环境变量前缀**（与控制面凭据分离）；  
3. 按既有离线/拒权策略 fail-closed；  
4. 证据仍可被诊断 MVP ingest（路径可经文件/HTTP 薄接线，不新建诊断微服务）。

## 2. 允许改动的路径（冻结清单）

| 路径/产物 | 允许 |
|-----------|:----:|
| `packages/aiplat-pi-runtime/**` 启动/README/env 示例 | ✅ |
| `reports/five-products/GATE3_*` / 运维备忘 | ✅ |
| 可选：仓库根或 `packages/aiplat-pi-runtime` 下 **试点** compose/脚本（明确 `gate3-pi-thin` 名） | ✅ |
| `aiPlat-core` / `aiPlat-platform` 拆服务、搬目录 | ❌ |
| 改生产默认共部署路径为强制独立 | ❌（试点并行） |

## 3. 配置与密钥

| 项 | 约定 |
|----|------|
| 控制面 | 继续既有 `AIPLAT_*` / 平台配置 |
| Thin 试点 | 使用文档化的独立 env 文件（例：`.env.gate3-pi-thin`）；**禁止**复用生产控制面密钥文件 |
| Bundle | 仍由 aiPlat `export_pi_bundle` / 切片导出产生；试点只消费产物 |

## 4. 健康与回滚

| 项 | 做法 |
|----|------|
| 健康 | 进程存活 + 能加载 Bundle 清单；不把「无证据」报成 healthy |
| 回滚优先 | Bundle 版本回滚（落地方案 A3.5） |
| 备选 | 停试点容器/进程，切回共置 Thin |

## 5. 验收（试点 DoD）

- [x] 试点环境与控制面**不同进程**可启动 Thin — `scripts/gate3_pi_thin_pilot.sh` → `http_smoke.sh`（独立 Node 进程，默认端口 `18787`）  
- [x] 密钥/env 与控制面文件分离 — `scripts/gate3_pi_thin.env.example` → `.env.gate3-pi-thin`；脚本在 `AIPLAT_ENTERPRISE=1` 时 exit 3  
- [x] 跑通客户场景主路径技术夹具（sample-app）— 默认 `AIPLAT_APP_HOME=fixtures/sample-app`；诊断不降标（仍走既有切片证据规则）  
- [x] 回滚演练记录 — `GATE3_PI_THIN_ROLLBACK_DRILL.md`  
- [x] 无新增跨域私有 import / 无搬仓 — 仅本包脚本 + `reports/five-products/GATE3_*`  

## 6. 接线产物索引

| 产物 | 路径 |
|------|------|
| Env 示例 | `packages/aiplat-pi-runtime/scripts/gate3_pi_thin.env.example` |
| Pilot 脚本 | `packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh` |
| Compose（G3-2） | `packages/aiplat-pi-runtime/compose.gate3-pi-thin.yml`（`AIPLAT_HTTP_HOST=0.0.0.0`） |
| 回滚演练（G3-3） | `reports/five-products/GATE3_PI_THIN_ROLLBACK_DRILL.md`（Bundle 优先） |
| README | `packages/aiplat-pi-runtime/README.md` § Gate3 |

## 7. 试点发布节奏（独立于控制面）

| 项 | 约定 |
|----|------|
| Thin 试点 | 可按 Bundle 版本单独重启/换 `AIPLAT_APP_HOME`；不强制与控制面同发 |
| 控制面 | 仍走既有 aiPlat 发布；本试点不改生产默认共部署路径 |
| 节奏 owner | 运维兼任（见 ADR-08）；无独立 7×24 |

## 8. Phase B（已批 · `GATE3_PHASE_B_DECISION.md`）

| DoD | 状态 |
|-----|:----:|
| `export_pi_bundle` 产物作为 `AIPLAT_APP_HOME` | 见 `GATE3_PI_THIN_PHASE=b` |
| HTTP Thin `AIPLAT_SLICE_EVIDENCE=1` 写 JSONL（含 `scenario_id`） | `emitSliceEvidenceEvent` |
| 试点脚本断言证据落盘 | exit 4/5/6 失败 |

```bash
GATE3_PI_THIN_PHASE=b bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```

## 9. Phase C（已批 · `GATE3_PHASE_C_DECISION.md`）

| DoD | 状态 |
|-----|:----:|
| JSONL → 既有 `ingest_slice_evidence_from_jsonl` | 无新平行 ingest API |
| `build_slice_diagnosis_report` → `status=ok` | 夹具路径 |
| 独立 `AIPLAT_HOME` 沙箱 | 默认 `/tmp/aiplat-gate3-phase-c-home` |

```bash
GATE3_PI_THIN_PHASE=c bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```

## 10. Phase D（已批 · `GATE3_PHASE_D_DECISION.md`）

| DoD | 状态 |
|-----|:----:|
| 无 `evidence_report_ids` → 拒签 | exit 11 |
| 绑定 Phase C `report_id` → 通过 | exit 12 失败码 |
| 沙箱验收绑定落盘 | `$AIPLAT_HOME/five_products_slice/acceptance/` |

```bash
GATE3_PI_THIN_PHASE=d bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```

## 11. Phase E（已批 · `GATE3_PHASE_E_DECISION.md`）

| DoD | 状态 |
|-----|:----:|
| 运行时物化 lock-service Bundle（sample-app + `domain_id`/`scene_id`） | 避免深层 fixture 树 inflation |
| `GATE3_PI_THIN_PHASE=e` → export → ingest → FDE bind | 同 D 链 |

```bash
GATE3_PI_THIN_PHASE=e bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```

## 12. Phase F（已批 · `GATE3_PHASE_F_DECISION.md`）

| DoD | 状态 |
|-----|:----:|
| 无 ⑥b → HTTP 409 `preflight_gate_blocked` | exit 14 |
| 有 ⑥b、无 report → HTTP 409 slice gate | exit 15 |
| ⑥b + `report_id` → HTTP `signed_off` + 落盘 | exit 16/17 |

```bash
GATE3_PI_THIN_PHASE=f bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```

## 13. 后续 PR 约束

- 单 PR 遵守 physical merge inflation；超限则拆 PR 或短豁免并退役  
- 仅允许本包 + `reports/five-products/GATE3_*`；禁止 core/platform 拆服务  
- Phase E/F **不**授权五产品全拆 / 对外 E4；顺序第 3 仅 ADR 草案  


