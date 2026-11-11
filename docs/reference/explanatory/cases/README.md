# 客户案例授权流程

> 供 **商业价值白皮书** 收集客户授权后的 ROI / TCO 材料。  
> **禁止**在未授权时把数字写入 `volumes/03-commercial-value.md` 作客户承诺。

## 授权四步

1. **客户书面授权**（可匿名对外须写明）。
2. **法务/商务确认**可公开范围与有效期。
3. 案例文件标注 `authorized: true`、授权编号、有效期。
4. 未经授权案例不得进入对外卷正文；仅允许作为 `authorized: false` + `kind: illustrative` 的内部示意（见 [`internal-illustrative-fde.md`](./internal-illustrative-fde.md)）。

## 案例模板（复制为 `YYYY-customer-slug.md`）

```markdown
---
customer: （可匿名）
industry:
engagement: PoC | Pilot | Production
authorized: false   # true 仅当客户书面授权对外
period:
---

## 业务问题
## 采用前成本/风险（可量化项）
## 采用后指标（周期、人天、事故、合规）
## 平台能力映射（链到 CAPABILITIES 行，勿抄表）
## 限制与未包含项
```

授权前本目录可仅保留本 README 与内部示意文件。
