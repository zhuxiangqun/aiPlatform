# FDE 工作台演进 — 决策记录

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-DEC-2026-09` |
| 版本 | **v1**（六问已决 · Phase 0 生效） |
| 关联方案 | [`fde-workbench-evolution-plan.md`](../architecture/plans/fde-workbench-evolution-plan.md) §9 |
| 关联契约 | [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) · [`FDE_GUARD_REGISTRY_LANDING.md`](./FDE_GUARD_REGISTRY_LANDING.md) · [`audit_schema.v1.yaml`](../../aiPlat-core/core/harness/schemas/audit_schema.v1.yaml) · [`domain_literals_scan.md`](./domain_literals_scan.md) · [`action_branch_scan.md`](./action_branch_scan.md) |
| 会议 / 评审日 | 2026-09-14 |
| 记录人 | Oliver Zhu |
| 参与人 | Oliver Zhu（书面采纳建议答案开工） |
| 总状态 | ☑ **六问已决** · ☑ **Phase 0 生效** |

---

## 0. 使用说明

1. 每个决策点填：**决议**、**理由**、**影响评估**、**Owner**、**Deadline**、**后续动作**、**关闭标准**、**状态**。  
2. 六问全部为「已决」且配套文档确认后，方可勾选 **Phase 0 生效**。  
3. **本文件是评审产物**；Phase 0 生效后按 [`FDE_PHASE0_KICKOFF_CHECKLIST.md`](./FDE_PHASE0_KICKOFF_CHECKLIST.md) 推进实施。  
4. 驳回建议答案时，必须写清对验收 / 风险的影响（尤其 D4、D6）。  
5. 「已决」与「已执行 / 已关闭」是两个维度，见 §4.5 / §6。  
6. **§5** 由记录人在六问已决时一次性填完；**§6** 由记录人每周更新，逾期两周未更新则标记为「停滞」。  
7. 开工勾选见开工清单。

---

## 0.5 假设与约束

| # | 假设 / 约束 | 若被推翻的影响 | 验证方式 | 状态 |
|---|-------------|----------------|----------|------|
| A1 | Phase 0–2 由 1–2 名工程师投入，不并行其他大项目 | 排期顺延；D4 资源重估 | 评审确认 | ☑ 接受 |
| A2 | `AsyncActionRegistry.register` 可加前置钩子，不需重构接口 | Landing §3 改设计 | Landing 已盘点 | ☑ 接受 |
| A3 | `action_audit` 可增量加列（NULL）或 JSON 嵌入 | Phase 1 迁移方案改 | Landing §4 | ☑ 接受 |
| A4 | lock-service 种子可脚本生成，200 工单无需人工录入 | D4 降 20 或延后 | Phase 2 开工前验证 | ☑ 接受（**已验证** `scripts/seed_lock_service_orders.py` + bench 200） |
| A5 | `run_security_review_dry` 已存在且可经 CoreFacade 调用 | Phase 4A 先补 Facade | 代码已确认 | ☑ 接受 |
| A6 | Pipeline HITL / failure_strategy 已可用 | Phase 1 HITL 硬验收失败 | Phase 1 开工前冒烟 | ☑ 接受（待冒烟） |
| A7 | `pending_approvals` 可承载 Action 级审批 | 需新建审批存储 | Landing §1 | ☑ 接受 |
| A8 | DomainRouter 已存在且可作为唯一域解析入口 | Phase 0 需先补 Router | Landing §2 | ☑ 接受 |

**约束：** C1–C4 维持。Phase 0 生效后 C4 解除，改按开工清单推进。

---

## 1. 总 Go / No-Go

| 项 | 填写 |
|----|------|
| 是否以方案 v1.1+ 为基线继续？ | ☑ **Go** |
| 有条件时的条件 | 无 |
| 方案修订要求（若有） | 无；以 v1.1++ 文档地图为准 |
| 已知风险接受 | D4 坚持硬门 200；若 A4 被推翻再按决策记录重开 D4。action_branch 硬违规≈0，Phase 2 无分支清理前置。 |
| 签字（架构） | Oliver Zhu / 2026-09-14 |
| 签字（产品 / FDE 负责人） | Oliver Zhu / 2026-09-14 |

---

## 2. 六问决议

### D1 — FDEBuilderOrchestrator：接线 vs 删除？

| 项 | 内容 |
|----|------|
| 问题 | 零 caller 的 Orchestrator 是接线工厂，还是删除/归档？ |
| 方案建议 | **删除或归档**；交付一律工厂 Pipeline |
| **决议** | ☑ **采纳建议（归档/删除）** |
| 理由 | 零 caller 假能力；交付核唯一为工厂 Pipeline |
| 影响评估 | Phase 0：归档路径 + CAPABILITIES 标注/移除 + Tab 入口清理 |
| Owner | Oliver Zhu |
| Deadline | 2026-09-14（评审周结束 / 与 Phase 0 并行） |
| 后续动作 | 定位 `FDEBuilderOrchestrator` → 归档或删除 → 更新 CAPABILITIES → 清理 UI 引用 |
| 关闭标准 | 无生产 caller；CAPABILITIES 已更新；无 UI 假入口 |
| 关闭日期 | **2026-09-14**（Phase 0 归档完成） |
| 状态 | ☑ **已决** · ☑ **已执行** · ☑ **已关闭** |

---

### D2 — `fde-delivery` 是否允许唯一平台跟踪域常量？

| 项 | 内容 |
|----|------|
| 问题 | harness 是否允许 `PLATFORM_TRACKING_DOMAIN = "fde-delivery"`？ |
| 方案建议 | **允许**该常量；**禁止**行为分叉 |
| **决议** | ☑ **采纳建议（允许常量，禁止行为分叉）** |
| 理由 | 与守卫 `allow_if: in_constant_assignment` 一致；跟踪元域需要稳定标识 |
| 影响评估 | 保留 allow_if；扫描关闭项区分常量 vs 行为分叉 |
| Owner | Oliver Zhu |
| Deadline | 2026-09-14 |
| **升 error 触发条件与 Owner** | 行为分叉清零 + domain 扫描关闭项完成；Owner=**Oliver Zhu**；最迟 **Phase 5 开工前** → **已达成** |
| 后续动作 | 确认/落点 `PLATFORM_TRACKING_DOMAIN`；对齐守卫与扫描分类 |
| 关闭标准 | 常量已落点；行为分叉类命中=0 或已计划清零 |
| 关闭日期 | **2026-09-14** |
| 状态 | ☑ **已决** · ☑ **已执行**（`fde_domain_literals=error`，AST=0） · ☑ **已关闭** |

---

### D3 — `accept_order` 命名空间迁移时机

| 项 | 内容 |
|----|------|
| 问题 | 立即改 id 前缀，还是双 id 过渡？ |
| 方案建议 | Phase 2：**新 id + 旧别名**；Phase 3 废弃别名 |
| **决议** | ☑ **采纳建议** |
| 理由 | 降低存量调用同步成本；与 action_branch≈0 一致，主风险在别名而非 if 清理 |
| 影响评估 | Phase 2 维护别名表；Phase 3 废弃公告 |
| Owner | Oliver Zhu |
| Deadline | Phase 2 开工前（目标 **2026-10-15**） |
| 后续动作 | 设计别名表；兼容调用清单；Phase 3 废弃计划 |
| 关闭标准 | 别名表合入；Phase 3 废弃公告已发 |
| 关闭日期 | _Phase 3 后填_ |
| 状态 | ☑ **已决** · ☑ **已执行**（`ActionContractModel.aliases` + `resolve_action_id`） · ☐ 已关闭 |

---

### D4 — Phase 2 压测规模：200 vs 20

| 项 | 内容 |
|----|------|
| 问题 | 200 工单是否作为硬门？ |
| 方案建议 | **默认 200** |
| **决议** | ☑ **硬门 200** |
| 量化标准 | 失败率 0；审计 200 条完整率 100%；全链路 P95 &lt; 500ms；查询 P95 &lt; 100ms |
| **P95 测量口径** | 从 `AsyncActionRegistry.execute` 入口到 `insert_audit` 返回；不含人工审批；环境优先 **CI / 本地可复现脚本**，预发可选 |
| 若降级，关闭空心风险计划日 | N/A（不降级） |
| 补偿措施（若降级） | N/A |
| 理由 | 防 Ontology 空心；action_branch≈0 不阻塞压测 |
| 影响评估 | 需种子脚本（A4）；D3 迁移为前置 |
| Owner | Oliver Zhu |
| Deadline | Phase 2 开工前（目标 **2026-10-15**） |
| 后续动作 | 种子脚本；压测脚本与环境 |
| 关闭标准 | 四项量化达标 |
| 关闭日期 | **2026-09-14** |
| 状态 | ☑ **已决** · ☑ **已执行** · ☑ **已关闭**（bench：fail=0 audits=200 exec_p95≈32ms query_p95≈0.4ms complete=100%） |

---

### D5 — Phase 4A 入口与 Phase C 默认

| 项 | 内容 |
|----|------|
| 问题 | 上线前检查放哪一 Tab？是否默认开 Phase C？ |
| 方案建议 | 独立入口；默认 Phase B；Phase C 显式开关 |
| **决议** | ☑ **采纳建议** · ☑ **Phase 4 已重开并执行** |
| 理由 | 不阻塞 Phase 0–3；4A 接口已存在可后期接线 |
| 影响评估 | Phase 4 立项时补 UI 与生命周期小注 |
| **延期责任人** | **Oliver Zhu**（已重开） |
| Owner | Oliver Zhu |
| Deadline | Phase 4 立项时 |
| 后续动作 | ~~立项时~~ **已完成**：独立「⑥b 上线前检查」；默认 B；C 开关；Evidence 存 `~/.aiplat/fde_security_preflight/`（摘要指针；Phase C 产物仍落 cache/tmp） |
| 关闭标准 | 入口上线且默认 B；C 开关验证 |
| 关闭日期 | **2026-09-14** |
| 状态 | ☑ **已决** · ☑ **已执行** · ☑ **已关闭** |

---

### D6 — 人审通过率是否可作为个人考核唯一指标？

| 项 | 内容 |
|----|------|
| 问题 | 是否书面禁止「通过率」作为个人考核唯一 KPI？ |
| 方案建议 | **禁止作为唯一 KPI**；拒绝率 + 回滚率 + 存活时间 |
| **决议** | ☑ **采纳建议（书面禁止唯一 KPI）** |
| 理由 | 防橡皮图章；与方案 Phase 4 反向指标一致 |
| 影响评估 | 写入 FDE 运营手册 KPI 节；仪表盘展示组合指标 |
| Owner | Oliver Zhu |
| Deadline | 2026-09-14 |
| 后续动作 | EvolutionTab 声明组合指标；手册 KPI 节可继续补全文 |
| 关闭标准 | 手册 KPI 节已更新且仪表盘指标清单已发布（可延至 Phase 4） |
| 关闭日期 | **2026-09-14**（工作台声明已落地；手册全文可后续补） |
| 状态 | ☑ **已决** · ☑ **已执行（工作台）** · ☐ 手册全文关闭 |

---

## 2.5 跨决策依赖

| 决策 | 依赖 | 说明 | 本轮检查 |
|------|------|------|----------|
| D3 | D2 | D2 非严格模式 → 别名可用字面量过渡 | ☑ 无冲突 |
| D4 | D3 | 压测前置命名空间迁移 | ☑ D3 已决采纳 |
| D4 | A4 | 种子脚本 | ☑ A4 接受，Phase 2 验证 |
| D5 | A5 | dry-run 已存在 | ☑ |
| 其余 | — | — | ☑ 无冲突 |

---

## 3. 配套文档确认 — **六件套**

| 文档 | 确认 | 签字 / 日期 |
|------|------|-------------|
| 方案 v1.1+ / v1.1++ | ☑ 已评 | Oliver Zhu / 2026-09-14 |
| `FDE_WORKBENCH_CONTRACT.md` | ☑ 已评 | Oliver Zhu / 2026-09-14 |
| `audit_schema.v1.yaml` | ☑ 已评（语义冻结） | Oliver Zhu / 2026-09-14 |
| `FDE_GUARD_REGISTRY_LANDING.md` v1.1 | ☑ 已评 · ☑ §1 盘点无异议 | Oliver Zhu / 2026-09-14 |
| `domain_literals_scan.md` | ☑ 已确认分布与分类框架 | Oliver Zhu / 2026-09-14 |
| `action_branch_scan.md` | ☑ 已产出 · ☑ 分类（硬违规≈0） | Oliver Zhu / 2026-09-14 |
| 本决策记录 | ☑ 六问已决（D5 延期） | Oliver Zhu / 2026-09-14 |

---

## 4. Phase 0 生效门禁

- [x] §0.5 假设与约束已确认  
- [x] §1 总 Go  
- [x] D1–D4、D6 已决；D5 延期且已指定延期责任人  
- [x] §2.5 无冲突  
- [x] §3 六件套已确认  
- [x] Phase 0 最小项清单已单列  
- [x] 生效后按开工清单推进（不再冻结改码）  

**Phase 0 生效：** ☑ **是**（生效日 **2026-09-14**，宣布人 **Oliver Zhu**）

### Phase 0 最小项清单

| # | 项 | 回滚 | Owner |
|---|-----|------|-------|
| 1 | API 前缀统一 `/api/platform/apps/fde` | 恢复兼容路由标注 | Oliver Zhu |
| 2 | Tab⑤ 诚实文案 | 文案回退 | Oliver Zhu |
| 3 | Orchestrator 按 D1 归档/删除 | 恢复归档或断开 | Oliver Zhu |
| 4 | dashboard stub 真数据或隐藏 | 恢复隐藏 | Oliver Zhu |
| 5 | 契约/扫描/本记录入库引用 | 文档回退版本号 | Oliver Zhu |

---

## 4.5 生效后评审

| 时点 | 评审内容 | 负责人 | 产出 |
|------|----------|--------|------|
| Phase 1 结束 | D1/D2 后续；A2/A6/A7 | Oliver Zhu | 阶段记录 |
| Phase 2 开工前 | D3 别名；D4 环境；A4 | Oliver Zhu | D3/D4 更新 |
| Phase 2 结束 | D4 压测；风险 #3 | Oliver Zhu | 压测报告 |
| Phase 3 结束 | D3 别名废弃；生成物规范 | Oliver Zhu | 废弃公告 |
| Phase 4 立项时 | **D5 重开**；A5；4A 生命周期小注 | Oliver Zhu（延期责任人） | D5 + 4A 小注 |
| Phase 5 开工前 | D2 升 error；domain_literals 清零 | Oliver Zhu | 升级公告 |

**触发方式：** 负责人主动发起；逾期 3 天未发起由记录人升级至 §1 签字人。

---

## 5. 决议一览

| ID | 一句话决议 | Owner | Deadline | 影响阶段 | 状态 |
|----|------------|-------|----------|----------|------|
| D1 | 归档/删除 Orchestrator，交付走工厂 | Oliver Zhu | 2026-09-14 | Phase 0 | ☑ 已决 |
| D2 | 允许 PLATFORM_TRACKING_DOMAIN；禁行为分叉 | Oliver Zhu | 2026-09-14 | Phase 0/5 | ☑ 已决 |
| D3 | Phase 2 新 id+别名；Phase 3 废弃 | Oliver Zhu | 2026-10-15 | Phase 2/3 | ☑ 已决 |
| D4 | 硬门 200；P95=execute→insert_audit | Oliver Zhu | 2026-10-15 | Phase 2 | ☑ 已决 |
| D5 | 采纳建议；延期至 Phase 4 立项 | Oliver Zhu | Phase 4 立项 | Phase 4 | ☑ 已决(延期) |
| D6 | 禁止通过率作唯一 KPI | Oliver Zhu | 2026-09-14 | 持续 | ☑ 已决 |

---

## 6. 决议执行追踪

| ID | 关闭标准 | 当前进度 | 阻塞项 | 最近更新 |
|----|----------|----------|--------|----------|
| D1 | 无 caller；CAPABILITIES 更新 | **已关闭**（归档 `_archive/builder.py`） | — | 2026-09-14 |
| D2 | 常量落点；行为分叉清零计划 | **已关闭**（error + AST=0）；见 `domain_literals_scan.md` v1.1 | — | 2026-09-14 |
| D3 | 别名表 + Phase 3 废弃 | **已执行**：canonical + `accept_order` alias；Phase 3 再废弃 | Phase 3 废弃公告 | 2026-09-14 |
| D4 | 四项量化达标 | **已关闭**（`bench_accept_order_p95.py --count 200` PASS） | — | 2026-09-14 |
| D5 | 入口+默认 B | **已关闭**：⑥b PreflightTab；默认 B；C 开关 | — | 2026-09-14 |
| D6 | 手册 KPI 节 | **工作台已声明**禁止唯一通过率 KPI；手册全文可选补 | 手册全文 | 2026-09-14 |

---

## 7. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0–v0.3 | 2026-09-14 | 模板迭代 |
| **v1** | **2026-09-14** | 全部采纳建议答案；Owner=Oliver Zhu；Phase 0 生效宣布 |
| v1.1 | 2026-09-14 | D3 已执行；D4/A4 关闭（200 压测 PASS） |
| v1.2 | 2026-09-14 | D5 关闭；D6 工作台声明；Phase 4 4A/4B |
| v1.3 | 2026-09-14 | D2 升 error 关闭；Phase 5 客户接入清单 |
