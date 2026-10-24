# WP0 切片路径事实清单

> **§3.1 为目标路径；下列为 WP0 核实后的 As-Is / Known Gap / Blocker。**  
> 场景：`fp-internal-bundle-pi-diag-001`（非客户验收）· 本体：**切片未使用**  
> L1 生效：2026-10-23 · 盘点启动：同日 · 临时 R：见 `ROLES.md`  
> 证据等级：E0 文档 · E1 源码 · E2 单测/脚本 · E3 多服务集成 · E4 干净部署 · E5 生产  

**摘要**：主路径各段均有**局部**源码或烟测锚点；**贯通的端到端 E3 尚不存在**（按 §3.6.2 归 WP4，**不**列为 Blocker）。当前 **无未关闭 Blocker**。最大可控缺口是「诊断产品 MVP（Pi+aiPlat 证据关联出报告）」与「FDE 场景对象 → Bundle 发布」的产品化接线。

---

## 表 A · 能力入口

| ID | 产品步骤 | 入口（现状） | 证据 | 分类 |
|----|----------|--------------|------|------|
| A1 | FDE：建场景 + 验收标准 | `apps/fde/api/fde_acceptance.py`（checklist / signoff）；`fde_delivery_pipeline.py`；大量 FDE API | E1 | **As-Is（局部）**：验收/交付管线存在。正式 Engagement/Scenario 与本切片 SCENE 一一对应的「建场景」产品 API → 见表 B / F，**Known Gap** |
| A2 | aiPlat：发布版本化 Agent Bundle | `scripts/export_pi_bundle.py`；`builder/pi_bundle_export.py`；`agent_manager` integrity / lifecycle | E1–E2 | **As-Is（导出/完整性）**；「FDE 一键触发发布 + 权限声明审计闭环」→ **Known Gap** `KG-BUNDLE-01` |
| A3 | Pi Thin：安装并运行 | `packages/aiplat-pi-runtime/`；`live_smoke.sh`；`pi-thin-runtime.md` Phase0–2 已合并 | E2（本地烟测） | **As-Is（Thin 宿主）**；切片隔离环境签字与离线策略文件 → WP2 `pi-thin-offline.md`（Known Gap 文档，非 Blocker） |
| A4 | 诊断：Pi + aiPlat 证据 → 报告 | `core/api/routers/diagnostics.py`（平台健康）；`fde_maintenance` diagnose/heal；**无**独立「证据关联产品」MVP | E1 | **Known Gap** `KG-DIAG-01`：现有多为平台/FDE 运维诊断，≠ 切片所需 Evidence/Diagnosis 契约 |
| A5 | FDE：按标准验收 | `POST .../acceptance/signoff` + `fde_preflight_signoff_gate`（CoreFacade） | E1 | **As-Is（签字门）**；与诊断报告 ID 强制关联 → **Known Gap** `KG-FDE-ACCEPT-01` |
| A6 | 故障注入：断连/拒权/过期 | Pi enterprise/tool_gate 烟测；PolicyGate 文档与 builder 门禁 | E1–E2 局部 | **Known Gap** `KG-FAULT-01`：路径级负向套件未按 SCENE 固化 |
| A7 | 本体 | — | — | **切片未使用**（不盘「已具备」） |

---

## 表 B · 依赖边（主路径）

| 边 ID | From → To | 现状核实 | 分类 | 备注 |
|-------|-----------|----------|------|------|
| E-01 | FDE 场景 → aiPlat 发布 Bundle | 无单一「场景对象驱动 publish」生产 caller；Builder `export_pi_bundle` 与 `scripts/export_pi_bundle.py` 可导出 | **Known Gap** `KG-EDGE-01` | 拟建：场景/交付会话触发导出或登记 bundle_id；owner=架构临时 R |
| E-02 | aiPlat Bundle → Pi 安装运行 | 导出包 + `pi -e` / HTTP 烟测存在（README / live_smoke） | **As-Is** E2 | 切片须固定一份 sample/夹具 Bundle；生产默认路径禁止改 |
| E-03 | Pi 运行 → 诊断摄入证据 | Pi 侧有 `run_id` / `bundle_version` 等字段（enterprise 烟测）；诊断侧无标准摄入 API 对接本切片 | **Known Gap** `KG-EDGE-02` | 拟建：Evidence ingest（Pi 事件 + aiPlat 资产版本）→ 报告 |
| E-04 | 诊断报告 → FDE 验收 | signoff 存在；未强制绑定诊断报告引用 | **Known Gap** `KG-EDGE-03` | 拟建：Acceptance 证据链字段含 report_id / 版本 |
| E-05 | 控制面身份 → 各目标服务 | `require_auth`、`_resolve_identity`、PolicyGate（CoreFacade） | **As-Is** E1 | 双重授权禁止已锁定；切片须跑伪造身份负向（WP4） |
| E-06 | FDE → harness knowledge/ontology 直连 | 2026-10-24：platform `apps/fde` **0** 直连（走 CoreFacade）；`core/apps/fde` **仍有** knowledge/ontology_engine 直连 | **Known Gap（core 层）** / platform As-Is | 见 `MB01_E06_REVERIFY.md`；解耦须 Gate 2 + D13 |

---

## 表 C · 数据 owner

| 数据 | 权威（目标） | 现状 owner 线索 | 切片结论 |
|------|--------------|-----------------|----------|
| 租户/策略/Agent 资产 | aiPlat | platform auth + agent_manager | 沿用 aiPlat；临时 R=架构 |
| Runtime 实例/执行状态 | Pi | aiplat-pi-runtime 本地/导出元数据 | 沿用 Pi |
| 项目/需求/验收证据 | FDE | FDE API + acceptance | 沿用 FDE；与诊断报告引用待接线 |
| 诊断报告/证据索引 | 诊断产品 | **分散**（diagnostics 路由 / FDE maintenance） | **Known Gap**：权威库未产品化 |
| Ontology | 本体 | 多处 | **本切片未使用** |

缓存：未在本轮逐库审计；WP0 续作：凡跨产品缓存标版本/新鲜度字段有无（DoD）。

---

## 表 D · 身份与副作用

| 点 | 位置 | 校验 | 副作用风险 | 分类 |
|----|------|------|------------|------|
| FDE API | `apps/fde/api/router.py` Depends(`require_auth`) | HTTP 身份注入 | 中（交付/heal） | As-Is E1；heal 等不进首切片默认工具集 |
| PolicyGate | CoreFacade / builder promotion | 工具副作用门禁 | 高若绕过 | As-Is 设计；切片禁止旁路 |
| Pi tool gate | `enterprise_tool_gate` 等 | 客户端/扩展门 | 不能替代服务端 | As-Is 局部；验收 F2 约束 |
| Bundle permission_claims | export / agent integrity | 声明 ≠ 授权 | 中 | As-Is 字段线索；契约 WP2 |

**安全未知？** 否——授权方式可知（aiPlat/PolicyGate）；首切片工具集保持低风险。→ **非 Blocker**。

---

## 表 E · 关闭实验

| 项 | 状态 | 规则 |
|----|------|------|
| 厂内 Pi 编码旁路 | 文档称合并关闭 / closed | D10：进主路径须独立 RFC + E4；本切片 **不启用** |
| Enterprise 厚能力烟测 | 存在多脚本 | 本切片默认 **Thin**；Enterprise 仅作对照，不进 SCENE 必经 |

---

## 表 F · 差距分级与 Known Gap 字段（§3.6.3）

### F.1 Blocker

| ID | 描述 | 状态 |
|----|------|------|
| — | （无）安全/权威/授权未知或不可控；隔离暂定「能」 | **无未关闭 Blocker** |

### F.2 Known Gap（可随 Gate 1 带入 WP3–WP4）

| gap_id | 描述 | 拟建面 | owner | 依赖 | 测试点 | 回滚 | 安全副作用 |
|--------|------|--------|-------|------|--------|------|------------|
| KG-EDGE-01 | FDE 场景→Bundle 发布无产品化 caller | 交付会话/场景登记 `bundle_id` + 调用现有 export，或薄 API | 架构临时 R | A1/A2 | 夹具场景导出成功；坏包拒绝 | 停用新 API，回退手工 export | 否（预签：安全 reviewer 在 Gate1） |
| KG-BUNDLE-01 | 发布含权限声明与审计的闭环未按契约固化 | Bundle 契约最小字段 + 审计事件 | aiPlat 临时 R | export_pi_bundle / agent_manager | permission_claims 不能单独授权 | 回退仅完整性哈希导出 | 触及授权声明 → Gate1 安全预签 |
| KG-DIAG-01 | 诊断 MVP：Pi+aiPlat 证据→可追溯报告 | Evidence/Diagnosis 最小 API 或适配器 | 诊断临时 R | E-03 | 缺证据→unknown/stale；版本可关联 | 关闭适配器，不写 healthy | 否 |
| KG-EDGE-02 | Pi 证据未标准摄入诊断 | ingest 契约 + Pi 侧发射 | 诊断+Pi 临时 R | KG-DIAG-01 | run_id/bundle_version 入报告 | 停 ingest | 否 |
| KG-EDGE-03 / KG-FDE-ACCEPT-01 | 验收未强制绑定诊断报告 | Acceptance 证据链字段 | FDE 临时 R | KG-DIAG-01 | 无 report 不可签「通过」 | 字段可选开关关闭 | 否 |
| KG-FAULT-01 | 路径级断连/拒权/过期套件 | WP3 测试计划 + WP4 执行 | 测试/验收 owner | 启用集契约 | ≥3 负向 | N/A | 否 |
| KG-OFFLINE-DOC | `pi-thin-offline.md` 未按 D6b 切片签字 | WP2 产出文件 | Pi 临时 R | Pi Thin As-Is | 评审签字 | N/A | 否 |

### F.3 Pi Thin vs Enterprise（摘录）

| | Thin（本切片） | Enterprise |
|--|----------------|------------|
| 现状 | 包与 live_smoke 存在 | 多 hybrid/enterprise 烟测 |
| 切片 | **采用** | 不作为必经；验证子集若改选须书面 |
| 离线 | 签名 Bundle 落盘后执行可断连；草案见 `contracts/pi-thin-offline.md` | 回连 aiPlat 厚能力 |

### F.4 诊断现状 vs MVP

| MVP 要求 | 现状 | 差距 |
|----------|------|------|
| 接 Pi 证据 | 部分 run_id 等 | 无标准诊断摄入 |
| 接 aiPlat 资产/bundle 版本 | agent/export 有版本线索 | 未关联进诊断报告产品 |
| unknown/stale | 平台诊断有 health 语义 | 未作为切片验收硬规则接线 |
| 本体/FDE adapter | 存在 FDE 向 ontology 直连等 | **后置**（本切片不启用） |

---

## 隔离环境（§2.3-4 核实）

| 项 | 结论 |
|----|------|
| L1 启动时 | 暂定「能」 |
| WP0 核实 | **维持「能」**：`phase0_offline_check` PASS；sample-app **export PASS**（2026-10-23）；夹具路径固定，**不**改生产默认路径 |
| 若后续失败 | 改判「不能」→ 只出缺口，挡 Gate 1 |

---

## 表 G · 主路径缓存 / DB 直连抽查（非全仓）

| 抽查 | 结果 | 对切片 |
|------|------|--------|
| `apps/fde` / `core/apps/fde` 主路径 API 层裸 `sqlite3.connect` | 平台 FDE API **未命中**；`k_wave_signal` 有 aiosqlite（本体/信号侧，**非**本切片必经） | 不登记为 As-Is 集成边；后置 |
| FDE→platform storage 跨层 import | 抽查未命中典型跨层 storage | 无新增 Blocker |
| 跨产品「共享 DB 当契约」 | 本轮主路径未见以共享 DB 作为 Bundle↔Pi↔诊断契约 | 保持禁止；发现则升 Blocker/Known Gap |

缓存版本/新鲜度：诊断 MVP（KG-DIAG）设计时强制 `freshness` 字段（见 enablement-matrix）。

---

## 表 H · As-Is 边可跑验证命令（E2 锚点）

| 边/能力 | 命令 | 2026-10-23 结果 |
|---------|------|-----------------|
| Pi Thin 结构/离线门 | `python3 packages/aiplat-pi-runtime/scripts/phase0_offline_check.py` | **PASS** |
| Bundle 导出（夹具） | `python3 scripts/export_pi_bundle.py --app-home packages/aiplat-pi-runtime/fixtures/sample-app --out /tmp/aiplat-fp-wp0-sample --runtime-mode thin` | **PASS**（含 `aiplat-export.json`） |
| Pi 实机对话烟测 | `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh` | 未本轮跑（依赖本机 pi/模型）；**不**阻塞 WP0；Gate1 前建议跑 |
| FDE 验收门源码 | `rg -n 'acceptance/signoff|fde_preflight_signoff_gate' aiPlat-platform/apps/fde/api/fde_acceptance.py` | 入口存在（E1；集成 E3 归 WP4） |
| 身份/Policy | `rg -n 'require_auth|PolicyGate|_resolve_identity' aiPlat-platform --glob '*.py' \| head` | 入口存在（E1） |

---

## WP0 DoD 进度

- [x] 摘要首句：目标路径 vs As-Is/Known Gap/Blocker  
- [x] 主路径边已分类；Known Gap 含最低字段；Blocker 单列（空）  
- [x] 未因整路径无 E3 阻塞 Gate 1  
- [x] 无跨库直写登记为 As-Is  
- [x] 数据 owner 表；缓存抽查见表面 G  
- [x] Pi Thin vs Enterprise；离线草案已起  
- [x] 诊断 vs MVP 差距表  
- [x] 临时 R 署名（ROLES）  
- [x] As-Is 带证据；E2 命令见表 H  
- [x] 时间盒内未虚构完备性  

**WP0 状态**：**可关闭初稿**（续跑 live_smoke 为加分，非关盒硬条件）。并行 WP1/WP2 草案已起。

**明确不做**：因「整路径无 E3」阻塞 Gate 1；不把 Known Gap 改写成 As-Is。
