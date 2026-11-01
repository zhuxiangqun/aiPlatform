# FDE Field D2 — ops / security / compat pack

> **Status**：Field D2 工程包（本地可验）· **非** compose 长驻 · **非** PG/HA  
> 前置：Field D1 Accepted（[`ADR-FDE-FIELD-DEPLOY.md`](../../../reports/five-products/ADR-FDE-FIELD-DEPLOY.md)）

## 决策

1. Field 默认 **local-first**：`AIPLAT_ENTERPRISE=0`；客户数据默认驻留前缀。  
2. D2 在 D1 之上补齐：**upgrade / runtime rollback**、安全基线检查、N-1/驻留文档门禁。  
3. 签收仍唯一：`POST /api/platform/apps/fde/acceptance/signoff`。  
4. 禁止 Field 直导控制面内部实现作为默认路径；共置健康探针走既有 ADR-09 / CoreFacade。  
5. compose 长驻 / 独立进程拆分仍须另 ADR。

## 验证

```bash
bash packages/aiplat-fde/scripts/d2_admin_check.sh
bash packages/aiplat-fde/scripts/d2_local_closeout.sh
```

## 非目标

- 生产 authorize / `production_signed`  
- 控制面 PG/HA cutover  
- 五产品全拆 / E4  
