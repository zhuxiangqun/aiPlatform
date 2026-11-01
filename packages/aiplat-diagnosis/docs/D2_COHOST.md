# Diagnosis D2 — cohost ops / security / protocol pack

> **Status**：D2 工程包（本地可验）· **D1c/cohost** · **非**进程拆分  
> 前置：D1 Thin · C1+C2 PASS · `process_split_authorized=false`

## 决策

1. 交付语义仍为 **D1c**：协议/healthz 独立，进程共宿 Central。  
2. D2 在 D1 之上补齐：安全基线、契约文档门禁、本地性能基线、upgrade/rollback。  
3. **禁止**本包授权 `process_split`；诊断报告 ≠ 自动修复 / accuracy 认证。  
4. 只读 Evidence；禁止 `remediate` / `auto_execute=true`。

## 验证

```bash
bash packages/aiplat-diagnosis/scripts/d2_admin_check.sh
bash packages/aiplat-diagnosis/scripts/d2_local_closeout.sh
```

## 非目标

- A3 生产拆分 / authorize  
- staging / production_signed  
- EVAL G2b / accuracy_claim  
