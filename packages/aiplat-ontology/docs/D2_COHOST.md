# Ontology D2 — cohost ops / security / protocol pack

> **Status**：D2 工程包（本地可验）· **D1c/cohost** · **非**进程拆分  
> 前置：D1 Thin · A3 Accepted（有条件）· `process_split_authorized=false`

## 决策

1. 交付语义仍为 **D1c**：契约/healthz 独立，进程共宿 Central。  
2. D2 在 D1 之上补齐：安全基线检查、API/协议文档门禁、本地性能基线、compat 矩阵行。  
3. **禁止**本包把 `process_split_authorized` 置 true；拆分须 live + checklist ✅ + authorize。  
4. 消费者只经 CoreFacade / 平台路由；禁止 platform 直导 harness 内部。

## 验证

```bash
bash packages/aiplat-ontology/scripts/d2_admin_check.sh
bash packages/aiplat-ontology/scripts/d2_local_closeout.sh
```

## 非目标

- A3 生产拆分 / authorize  
- Field/edge 本体宿主  
- 替代 FDE / Evaluation  
