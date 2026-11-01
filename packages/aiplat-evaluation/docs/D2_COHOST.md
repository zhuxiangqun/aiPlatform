# Evaluation D2 — cohost ops / security / protocol pack

> **Status**：D2 工程包（本地可验）· **D1c/cohost** · **非**进程拆分  
> 前置：D1 Thin · A3 Accepted（有条件）· `process_split_authorized=false`

## 决策

1. 交付语义仍为 **D1c**：协议/healthz 独立，进程共宿 Central。  
2. D2 在 D1 之上补齐：安全基线、协议文档门禁、本地性能基线、compat 矩阵行、upgrade/rollback。  
3. **禁止**本包授权 `process_split`；评测报告 ≠ 客户签收。  
4. 只读已发布 Artifact/Evidence；禁止直导 FDE/Ontology/harness 内部。

## 验证

```bash
bash packages/aiplat-evaluation/scripts/d2_admin_check.sh
bash packages/aiplat-evaluation/scripts/d2_local_closeout.sh
```

## 非目标

- A3 生产拆分 / authorize  
- Field/edge eval 宿主  
- 替代 FDE 验收真源  
