# 切片场景（D13 客户路径 · 2026-10-24 升格）

> **场景类型**：**客户可追溯路径**（江苏锁安 / `lock-service`）  
> **D13**：见 [`D13_CUSTOMER_ENDORSEMENT.md`](./D13_CUSTOMER_ENDORSEMENT.md)（§6.0.1 六字段齐全）。  
> **路径方案**：A（本体非必经）— 见落地方案 §3.1  
> **历史**：原内部场景 `fp-internal-bundle-pi-diag-001`（非客户验收）保留为对照，见 §7。

---

## 1. 场景标识

| 字段 | 内容 |
|------|------|
| `scene_id` | `fp-customer-lock-service-bundle-pi-diag-001` |
| 名称 | 江苏锁安：版本化 Bundle → Pi Thin 运行 → 诊断关联 → FDE 验收 |
| 客户场景 | **是**（客户组织：江苏锁安；域：`lock-service`） |
| 承诺等级 | 路径目标 **E3**；默认 **非对外 E4 宣传** |

---

## 2. 输入

1. 江苏锁安 / `lock-service` 域相关 Engagement（业务叙述）；技术验证可用夹具数据。  
2. 一份待发布的 **低风险** Agent Bundle 候选（工具以只读/无高风险副作用为默认）。  
3. 一个 **隔离** Pi Thin 目标环境（本地或专用沙箱；Gate3 试点可独立进程/密钥）。  
4. 预定义：成功输出契约、失败条件、回滚指向（**Bundle 版本优先**，Runtime 备选）。  
5. 夹具锚点（技术）：`packages/aiplat-pi-runtime/fixtures/sample-app`（见 `DECISIONS_AND_AUTHORIZATIONS.md` A3.4）— 夹具 ≠ 否定客户场景归属。  
6. 域锚点：`lock-service`（禁止在 harness 硬编码业务分叉；经 DomainRouter / 配置发现）。

---

## 3. 预期输出（目标路径 · 非断言现状已通）

```text
FDE：建场景 + 验收标准（江苏锁安 / lock-service）
  → aiPlat：发布版本化 Agent Bundle（权限声明 + 审计）
  → Pi Thin：隔离环境安装并运行（Gate3 试点可独立部署）
  → 诊断：接入 Pi + aiPlat 证据，报告可追溯（含 unknown/stale）
  → FDE：接受 / 拒绝或开整改
  → 至少 1 次：断连 / 拒权 / 过期 → 不得伪报成功
```

本体步骤：**本场景默认不启用**（盘点维度标「切片未使用」）。

---

## 4. 失败条件（业务可判定）

| ID | 失败条件 |
|----|----------|
| F1 | 无法从 FDE 需求追溯到 Bundle 版本 → Pi 实例 → 诊断报告 |
| F2 | 无授权调用未被目标服务拒绝，或仅靠 Pi 客户端 gate「通过」 |
| F3 | 缺证据仍报 healthy/成功 |
| F4 | 控制面/证据断连时高风险副作用未 fail-closed（首切片应无高风险工具） |
| F5 | 无法按预定回滚 Bundle 或 Runtime |

---

## 5. 验收人

与 [ROLES.md](./ROLES.md) / [L1_AUTHORIZATION.md](./L1_AUTHORIZATION.md) 业务验收人一致（可与业务 owner 兼任）。

---

## 6. 隔离环境

| 项 | 结论 |
|----|------|
| 可行性 | 本地或隔离沙箱可建；Gate3 Pi Thin 试点见 `GATE3_PI_THIN_PILOT.md` |
| 生产默认路径 | **禁止**在验证中擅自修改，除非 Gate3 试点清单明示 |

---

## 7. 变更与历史对照

| 日期 | 变更 |
|------|------|
| 2026-10-23 | 初版内部场景 `fp-internal-bundle-pi-diag-001`（非客户验收） |
| 2026-10-24 | **D13 升格**：替换为 `fp-customer-lock-service-bundle-pi-diag-001`；背书见 `D13_CUSTOMER_ENDORSEMENT.md` |

旧内部 id 仅作回归对照与历史证据目录名兼容；**新验收与 Gate3 试点以本文件客户场景为准**。
