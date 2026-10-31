# Pi D2 — admin / security pack

> **Status**：D2 Thin admin pack（工程）· **非** D3 · **非** 强制企业回连  
> 前置：D1 Thin + ADR-08 / Gate3

## 决策

1. Edge 默认 **offline-first**：安装与 smoke 保持 `AIPLAT_ENTERPRISE=0`。  
2. 企业回连 / 审批 / KB 为 **enterprise opt-in**（见 `HYBRID_ENTERPRISE.md`），不得改 D1 默认。  
3. Chart skeleton 注解 `aiplat.enterprise_default: "0"` + `aiplat.d2_admin_pack: "true"`。  
4. 禁止 Pi 运行时直导 `aiPlat-platform` / `core.harness` 作为默认路径。  

## 验证

```bash
bash packages/aiplat-pi-runtime/scripts/d2_admin_check.sh
bash packages/aiplat-pi-runtime/scripts/d1_smoke.sh
```

## 非目标

- 多租户治理中心化  
- 替代 Ontology / Evaluation / FDE  
- 宣称 D3 生产就绪（见另批 [`ADR-PI-D3`](../../../reports/five-products/ADR-PI-D3.md)；须 `d3_production_authorized`）  
- 五产品全拆 / E4  

## 与 D3

D2 本包保持 enterprise 默认 off。D3 路径与硬门：`docs/d3/` + `d3_prep_check.sh` / `d3_authorize.sh`。
