# 首切片设计（WP3）· 可执行规格

> `scene_id` = `fp-internal-bundle-pi-diag-001`  
> Gate 1：有条件通过（修订版）· 验收真源：落地方案 **§3.4**（不降标）  
> 原则：**正确 / 合理 / 合规 / 可落地** — 复用现有能力，但必须形成可重复证据链，禁止「能跑就行」的旁路。

---

## 1. 目标路径（逐步 · 责任产品 · 证据文件名）

| 步 | 动作 | 责任产品 | 运行时产物（约定文件名） |
|----|------|----------|-------------------------|
| S1 | 建内部场景 + 验收标准（夹具） | FDE | `ACCEPTANCE_CRITERIA.md` |
| S2 | 导出/登记版本化 Bundle（thin） | aiPlat | `bundle/aiplat-export.json` + integrity |
| S3 | 隔离环境安装并运行 Pi Thin | Pi | `RUNLOG/pi-run.jsonl`（含 run_id） |
| S4 | 摄入 Pi + aiPlat 证据 → 诊断报告 | 诊断 | `DIAGNOSIS_REPORT.md` + `report_id` |
| S5 | FDE 验收（必须引用 report_id） | FDE | `ACCEPTANCE.md` |
| S6 | 故障注入 ≥3 | 测试 | `FAILURE_INJECTION.md` |
| S7 | 版本集合与缺口 | 全员 | `VERSIONS.md` · `GAPS.md` |

本体：不执行。生产默认路径：不修改。

---

## 2. 环境与夹具（硬指定）

| 项 | 指定值 |
|----|--------|
| 隔离 | 本机/专用沙箱；禁止写生产租户默认配置 |
| App 夹具 | `packages/aiplat-pi-runtime/fixtures/sample-app` |
| 导出 | `python3 scripts/export_pi_bundle.py --app-home <夹具> --out <slice>/bundle --runtime-mode thin` |
| 离线策略 | `reports/five-products/contracts/pi-thin-offline.md`（执行必须遵守） |
| 身份 | aiPlat `require_auth` / `_resolve_identity`；副作用经 PolicyGate；Pi 客户端 gate **不得**单独放行 |
| 回滚 | **优先**换回上一 `bundle_id`/导出目录；备选 Runtime 版本回退；目标 ≤30 分钟可演练 |

---

## 3. Known Gap → 实现规格（关闭标准）

### 3.1 KG-EDGE-01 + KG-BUNDLE-01（FDE→发布 / Bundle 契约）

**合理做法**：不新建发布栈；在平台侧增加**薄编排**，内部只调用现有 `export_pi_bundle` / `builder.pi_bundle_export`。

| 项 | 规格 |
|----|------|
| 建议位置 | `aiPlat-platform/apps/fde/api/` 新路由文件 **或** 现有 delivery 路由增端点；业务逻辑在 `aiPlat-core/core/apps/fde/service/`（无 HTTP）；对外经已有 FDE router + `require_auth` |
| 接口形状（最小） | `POST /api/platform/apps/fde/slice/bundle/export`（最终路径以 router 挂载为准，须登记 CAPABILITIES）Body: `{ "scenario_id", "app_home", "runtime_mode":"thin" }` → `{ "ok", "bundle_id", "out_dir", "integrity", "export_meta" }` |
| 合规 | 禁止 FDE service 直 import harness 内部做「假发布」；导出失败不得返回伪装成功；`permission_claims` 写入 meta 但 **文档+测试** 声明其不能授权 |
| 测试 | 夹具导出 200；篡改/缺 manifest → 非 ok；单测或脚本进 `FAILURE_INJECTION` / pytest |
| 回滚 | Feature 开关或路由不挂载；手工 CLI export 仍可用 |
| 关闭标准 | 从 scenario_id 可追溯到 bundle_id + integrity 文件落在证据包 |

### 3.2 KG-DIAG-01 + KG-EDGE-02（诊断 MVP + Pi 摄入）

**合理做法**：最小 Evidence API（ingest + get report），**不是**新诊断产品中台；可放 `aiPlat-platform` 诊断/FDE 旁路路由 + `core/apps` 无 HTTP 服务；状态机含 `ok|unknown|stale|fail`。

| 项 | 规格 |
|----|------|
| 写入 | `POST .../slice/evidence/ingest` Body: Pi 侧 `run_id, bundle_version, events[]` + 可选 aiPlat `asset_versions` |
| 生成报告 | `POST .../slice/evidence/report` → `report_id` + 正文（缺任一侧证据 → 强制 `unknown`/`stale`，**禁止**默认 healthy） |
| Pi 侧 | 运行后写出 `RUNLOG/pi-run.jsonl`（至少 run_id、bundle_version、timestamp）；首切片可用**受控脚本**从 Pi 输出采集后调 ingest（须在 DESIGN/RUNLOG 标明采集器版本）；后续再嵌扩展，但验收不得依赖「人工口头描述」 |
| 合规 | 报告权威属诊断；FDE 只引用；断连 aiPlat 查版本时记 stale |
| 测试 | 缺 Pi 事件 → 非 ok；缺 bundle 版本 → stale/unknown；齐备 → ok 且版本可关联 |
| 回滚 | 关闭路由；不影响平台既有 `diagnostics.py` 健康检查 |
| 关闭标准 | `DIAGNOSIS_REPORT.md` 含 report_id 与证据引用表 |

### 3.3 KG-EDGE-03 / KG-FDE-ACCEPT-01（验收绑报告）

| 项 | 规格 |
|----|------|
| 改动点 | `fde_acceptance.py` 的 signoff：**当**请求带切片标志或 `evidence_report_ids` 策略开启时，缺少有效 `report_id` → **拒绝**「通过」 |
| 合规 | 走现有 `fde_preflight_signoff_gate`；新增校验与之串联，不绕过安全预检 |
| 测试 | 无 report 签通过 → 失败；有 report_id → 可签（仍受预检约束） |
| 回滚 | 配置项 `AIPLAT_FDE_REQUIRE_DIAG_REPORT_FOR_SLICE=0` 仅用于紧急回滚，默认切片开启 |
| 关闭标准 | `ACCEPTANCE.md` 记录 decision + report_ids + signer |

### 3.4 KG-FAULT-01（路径级负向 · 属 WP4 执行，WP3 定用例）

必须执行并记入 `FAILURE_INJECTION.md`（≥3，建议 4）：

1. 伪造/空身份调用导出或验收 → 拒绝  
2. 坏 Bundle（改 integrity）→ 安装/导出校验失败  
3. 诊断缺证据 → 报告 unknown/stale，不得成功  
4. 离线超 TTL 或调用 denied_ops（按 `pi-thin-offline.md`）→ 停止/拒绝  

### 3.5 KG-OFFLINE-DOC

`pi-thin-offline.md` 已草案；WP3 结束前架构×业务在该文件「切片确认」栏签字；WP4 执行按其字段。

---

## 4. 序列（集成）

```text
操作者/FDE
  → (auth) POST slice/bundle/export (夹具)
  → 证据包写入 bundle/*
Pi
  → 安装导出目录；执行低风险闭环；写 RUNLOG
采集器（版本记入 VERSIONS）
  → POST slice/evidence/ingest
  → POST slice/evidence/report → report_id
FDE
  → POST acceptance/signoff { evidence_report_ids:[report_id], ... }
故障注入脚本
  → 四条负向；结果写入 FAILURE_INJECTION.md
```

---

## 5. WP4 日程（按落地方案，可压缩但不可删项）

| 日 | 内容 | 退出条件 |
|----|------|----------|
| D1 | 隔离环境；导出 smoke | export ok + VERSIONS 起稿 |
| D2 | FDE 标准夹具 | ACCEPTANCE_CRITERIA.md |
| D3 | （跳过本体） | — |
| D4 | 发布/导出 API 或等价编排 + 审计字段 | bundle_id 可追溯 |
| D5–D6 | Pi 主路径 + RUNLOG | run_id 存在 |
| D7 | 诊断报告 | report_id + 非伪健康 |
| D8 | FDE 验收 | ACCEPTANCE 通过或归因 |
| D9 | 故障注入 | ≥3 条记录 |
| D10 | 归档；GAPS | §3.4 勾选完成 |

---

## 6. §3.4 验收映射（WP4 DoD · 不降标）

| §3.4 条 | 本切片验证方式 |
|---------|----------------|
| 1 追溯链 | scenario → bundle_id → Pi run_id → report_id 在证据包可指认 |
| 2 Pi 输出契约 | 与 ACCEPTANCE_CRITERIA 对照 |
| 3 诊断可回溯 / 禁伪健康 | DIAGNOSIS_REPORT + 负向#3 |
| 4 FDE 书面接受/拒绝 | ACCEPTANCE.md |
| 5–6 服务端鉴权 | 负向#1；PolicyGate/require_auth |
| 7 失联 fail-closed | 负向#4；无高风险工具 |
| 8 无密钥明文 | RUNLOG 脱敏检查 |
| 9–11 可重复/版本/归因 | 同夹具重跑；VERSIONS；GAPS |

对外承诺：默认 **不做** → 不强制 E4；路径 **必须 E3**（本证据包即 E3 载体）。

---

## 7. 目录（证据包）

```text
reports/five-products/slice-fp-internal-bundle-pi-diag-001/
  DESIGN.md                 ← 本文件（WP3）
  VERSIONS.md
  RUNLOG/
  bundle/
  DIAGNOSIS_REPORT.md
  ACCEPTANCE_CRITERIA.md
  ACCEPTANCE.md
  FAILURE_INJECTION.md
  GAPS.md
```

---

## 8. WP3 DoD

- [ ] 上文每步有责任产品与证据文件名  
- [ ] 故障注入用例 ≥3（已列 4）  
- [ ] 回滚步骤可执行（Bundle 目录切换演练说明写入本节 §2）  
- [ ] 全部 KG 有实现规格与关闭标准  
- [x] 架构临时 R 确认本 DESIGN 作为编码依据（与修订版 Gate 1 同日生效）  

**WP3 规格生效。** 下一步按 §3 实现代码与测试，再按 §5–6 跑 WP4 并归档证据包；不得以「先简单跑通」绕过 §3.4 / 负向用例 / 服务端鉴权。
