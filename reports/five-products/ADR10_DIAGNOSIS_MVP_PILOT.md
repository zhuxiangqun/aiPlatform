# ADR-10 试点：诊断 MVP（Phase A–D）

> **批准**：A/B/C 既有决定；D `ADR10_DIAGNOSIS_MVP_PHASE_D_DECISION.md`（**仅 D1**）  
> **场景**：`fp-customer-lock-service-bundle-pi-diag-001`  
> **非目标**：D2 平台默认绑定；拆控制面/FDE/全功能中台/全拆；对外 E4

## 允许路径

| 路径 | 允许 |
|------|:----:|
| `scripts/adr10_diagnosis_mvp*` · `reports/five-products/ADR10_*` | ✅ |
| `compose.adr10-diagnosis-mvp.yml`（Phase B one-shot） | ✅ |
| Phase D D1：双 flag + `$HOME/.aiplat/adr10-diagnosis-mvp-d1` | ✅ |
| D2 平台路由默认 · 强制改控制面 · 长驻微服务 · E4 | ❌ |

## 约定

- Env：`scripts/adr10_diagnosis_mvp.env.example`  
- A–C：沙箱 `/tmp/...`；裸 `PROD_DEFAULT=1` → exit 3  
- D1：`phase_d.sh` 设 `PROD_DEFAULT=1` + `ALLOW_USER_HOME=1` + home 在 `$HOME` 下

```bash
bash scripts/adr10_diagnosis_mvp_pilot.sh
bash scripts/adr10_diagnosis_mvp_phase_c.sh
bash scripts/adr10_diagnosis_mvp_phase_d.sh
AIPLAT_DIAGNOSIS_PROD_DEFAULT=1 bash scripts/adr10_diagnosis_mvp_pilot.sh  # exit 3
```
