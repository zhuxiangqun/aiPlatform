# Org L5 — 决策记录

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-DEC-2026-09` |
| 版本 | **v1.4**（D1–D5 + C + V + E + H 波 D-H1–D-H8） |
| 关联 Charter | [`ORG_L5_CHARTER.md`](./ORG_L5_CHARTER.md) · [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) · [`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md) · [`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md) · [`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md) |
| 关联 Pilot | [`ORG_L5_PILOT_SPEC.md`](./ORG_L5_PILOT_SPEC.md) |
| 关联开工 | [`ORG_L5_PHASE0_KICKOFF_CHECKLIST.md`](./ORG_L5_PHASE0_KICKOFF_CHECKLIST.md) |
| 记录日 | 2026-09-18 |
| 确认方式 | 会话书面确认（D1–D5；D6–D10；D-V1–D-V7） |
| 总状态 | ☑ P0–P4 · ☑ Phase C · ☑ K0–K5 · ☑ F2 · ☑ **V0–V5** · ☑ **E0–E2** · ☑ **H0–H5** · ☑ **S1–S4** · ☐ M4 |

---

## 0. 使用说明

1. 每问填：决议、理由、影响、Owner、Deadline、关闭标准、状态。  
2. 五问全部「已决」且 Kickoff §E 勾完 → 勾选 **P0 生效**。  
3. **P0 生效 ≠ Phase 1 已改码**；Phase 1 另见开工清单 §F。  
4. 驳回已决项时，必须新开修订版并写清影响。

---

## 0.5 假设与约束

| # | 假设 / 约束 | 若被推翻 | 状态 |
|---|-------------|----------|------|
| A1 | Phase 1–3 由 1 名主力工程师推进，不与大型无关重构并行 | 排期顺延 | ☑ 接受 |
| A2 | `abox_connector` 可扩展 fetch 而不新造 Syscall | 改成本阶梯论证 | ☑ 接受 |
| A3 | it-ops Action 种子三动作可支撑闭环故事 | 改试点域或补 Action | ☑ 接受 |
| A4 | 沙箱 stub 足以关闭 M1–M3；真系统留 W7 | M4 延后 | ☑ 接受 |
| A5 | Org 模块独立不阻塞 FDE 既有 Phase 契约 | 资源冲突时 FDE 优先写明 | ☑ 接受 |
| C1 | 禁止 harness 硬编码业务域名分叉 | 违规 PR 拒合 | ☑ 接受 |
| C2 | live 出站仅允许已登记 http_json + 双门解锁；禁任意 SQL | 守卫或配置断言 | ☑ 接受 |
| C3 | Phase C 入站仅飞书单渠；企微不做入站 | 违规 PR 拒合 | ☑ 接受 |

---

## 1. 总 Go / No-Go

| 项 | 填写 |
|----|------|
| 是否以 Charter v0.1→v1.0 为基线继续？ | ☑ **Go** |
| 条件 | 无；Phase 1 须 Kickoff §F 另宣布 |
| 已知风险接受 | 单线 L5 ≠ 全域企业大脑；话术须同步 |
| 签字（架构 / 产品） | 会话确认 / 2026-09-18 |
| 日期 | 2026-09-18 |

---

## 2. 五问决议

### D1 — 主试点域？

| 项 | 内容 |
|----|------|
| 问题 | 组织闭环第一条业务线选哪？ |
| 建议 | **it-ops**（Action 深、图说成熟、KPI 好定义） |
| **决议** | ☑ **采纳 it-ops** |
| 理由 | Action 生命周期完整；与 PPT/FDE⑦ 演示叠加成本最低 |
| 影响 | Pilot Spec 以 it-ops 为准；不设双主线 |
| Owner | 试点 Owner（工程） |
| Deadline | 2026-09-18（已决） |
| 关闭标准 | Charter §5 与 Pilot 标题域一致；无双主线 |
| 关闭日期 | 2026-09-18 |
| 状态 | ☑ **已决** · ☑ **已关闭** |

---

### D2 — 试点三 KPI？

| 项 | 内容 |
|----|------|
| 问题 | 周报固定哪三个业务后果指标？ |
| 建议 | **MTTA**、**根因标注率**、**例外占比** |
| **决议** | ☑ **采纳建议**（`mtta` / `root_cause_rate` / `exception_ratio`） |
| 理由 | 可从 ActionStore + OrgRun 出数；不抄材料 KPI |
| 影响 | weekly API schema；Value 页深链文案 |
| Owner | 试点 Owner |
| Deadline | 2026-09-18（已决） |
| 关闭标准 | Pilot Spec §6 与实现字段名一致；禁材料 KPI |
| 关闭日期 | 2026-09-18 |
| 状态 | ☑ **已决** · ☑ **已关闭** |

---

### D3 — 是否允许写非沙箱生产系统？

| 项 | 内容 |
|----|------|
| 问题 | Phase 1–3 能否 `IO_MODE=live`？ |
| 建议 | **否**；仅 sandbox/deny；live 仅 W7 书面解除 |
| **决议** | ☑ **采纳禁止**（默认 `AIPLAT_ORG_IO_MODE=sandbox`） |
| 理由 | M1–M3 用 stub 即可验收；降低合规与误写风险 |
| 影响 | connector 默认；W7 前不得合入 live 默认 |
| Owner | 工程 |
| Deadline | 2026-09-18（已决）；解除须新决议 |
| 关闭标准 | 配置默认非 live；文档写明解除条件 |
| 关闭日期 | 2026-09-18 |
| 状态 | ☑ **已决** · ☑ **已关闭**（解除=新开决策） |

---

### D4 — Org Runtime 模块挂载位置？

| 项 | 内容 |
|----|------|
| 问题 | 新 HTTP/服务放哪？ |
| 建议 | **独立 `platform/apps/org` + `core/apps/org/service`** |
| **决议** | ☑ **独立 org** |
| 理由 | 避免 FDE 控制台继续膨胀；边界清晰 |
| 影响 | `apps.yaml` 注册、前端路由、鉴权登记；Phase 1 若为薄 fetch，允许**临时**经 FDE 路由暴露但 **Core 逻辑须落在可迁路径**，Deadline= M2 前迁入 `apps/org` |
| Owner | 工程 |
| Deadline | 模块骨架：Phase 1 同期；路由收敛：不晚于 M2 |
| 关闭标准 | registry 有模块声明；FDE 契约否定清单不膨胀执行核 |
| 关闭日期 | **2026-09-18**（路由已收敛：`/org/connectors/*` 规范；FDE 路径为兼容 shim） |
| 状态 | ☑ **已决** · ☑ **已关闭** |

---

### D5 — 是否并行 data-gov 只读 fetch 薄切片？

| 项 | 内容 |
|----|------|
| 问题 | Phase 1 是否加 data-gov 只读证明通用性？ |
| 建议 | **可选**；不建第二条 OrgGoal；≤1 集成测试工作量 |
| **决议** | ☑ **做薄切片**（只读 fetch；无 OrgGoal） |
| 理由 | 低成本证明 connector 非 it-ops 特化；不抢主线 |
| 影响 | P1 人日约 +0.5–1 |
| Owner | 工程 |
| Deadline | 随 Phase 1 PR |
| 关闭标准 | 1 集成测试绿 + 文档一行诚实说明 |
| 关闭日期 | 待 Phase 1 |
| 状态 | ☑ **已决** · ☐ 执行中 |

---

## 3. P0 生效勾选

| 检查项 | 状态 |
|--------|------|
| Charter Go 已签 | ☑ 2026-09-18 |
| D1–D5 全部已决 | ☑ |
| Kickoff Checklist §E 全部勾选 | ☑ |
| **P0 生效** | ☑ **2026-09-18** · 会话确认 |

**宣布用语**：  
> Org L5 P0 于 2026-09-18 生效；Phase 1 仅沙箱 I/O；主试点 it-ops；并行 data-gov 只读 fetch 薄切片；对外话术仍为 L3 + 原型，直至 M4。

---

## 4. 每周状态（记录人更新）

| 周次 | 进度 | 阻塞 | 下次动作 |
|------|------|------|----------|
| 2026-09-18 | P0–P4 完成；http_json 出站门禁已接线（默认关） | 无客户真线 | M4 仅在客户沙箱真线+人工签收后宣称 |
| 2026-09-18 | **Phase C C0**：渠道/Interface Charter 落盘；D6=飞书 | C1 未开工 | 宣布 C1 后方可改 Interface 执行码 |
| 2026-09-18 | **Phase C5 签收包就绪**：`c5_pack_ready`；`m4_claim_allowed=false` | 客户未签字 | 等客户真线 + 双签，不自动称 L5 |
| 2026-09-18 | **C1.5 落地**：Interface YAML 权威；`live` 只读兼容 | 无客户真线 | 不自动称 L5 |
| 2026-09-18 | **K0 契约**：事实清单见 K 波 Charter §3；K1 未开工 | 活 YAML 旁路仍在 | 另宣布才可改 K1 |
| 2026-09-18 | **K1 落地**：确认 → 信号；活 YAML 不变 | F2 旁路仍在；K2 未开 | 另宣布才可改仲裁写边 |
| 2026-09-18 | **K2 落地**：仲裁单闸门；HTTP 不再直接写边 | F2 旁路仍在 | 另宣布才可开 K3 |
| 2026-09-18 | **K3 落地**：OrgRun 挂 reasoning_paths / skip | 无 | 另宣布才可开 K4 |
| 2026-09-18 | **K4 落地**：OrgRun/工具连续失败 → 案例 overlay | 无 | 另宣布才可开 K5 |
| 2026-09-18 | **K5 落地**：重复失败 → edge 提案；不自动 apply | F2 旁路仍在 | 不称出错已变规则 |
| 2026-09-18 | **F2 门禁**：直写活 YAML 拒绝；令牌仅 apply/rollback | 不称 M4 | 客户真线另跟踪 |
| 2026-09-19 | **V0 契约**：trace 闭集、批准≠apply、回滚边界、自动 apply 启动断言写入 Charter。执行码未改 | V1 未开工 | 断言先于回放；不称 L5 |
| 2026-09-19 | **V1-pre + V1**：开关打开则拒绝开跑与 K5；`GET …/org/traces/{id}` 只读五步 | V2 未开工 | 不称 L5；批准仍未走 PolicyGate |
| 2026-09-19 | **V2**：控制台开跑一次岗位判决；侧边栏 `/org/pilot`；渠道方向来自状态接口 | V3 未开工 | 不称 L5；飞书入站不重复判决 |
| 2026-09-19 | **V3**：价值看板分平台指标与客户签收。`GET …/org/signoff` 只读，无签收按钮 | V4 未开工 | `m4_claim_allowed` 仍 false |
| 2026-09-19 | **V4**：提案批准只经 PolicyGate。身份来自 `X-AIPLAT-ROLE`。批准不写活 YAML | V5 未开工 | 不说出错已变成规则 |
| 2026-09-19 | **V5**：回滚边界写入 `GET …/org/rollback/scope` 与试点页。不回滚草稿和边 | 无 | 不称 L5 |
| 2026-09-19 | **E0 契约**：仲裁边回滚只覆盖带 `edge_before` 的 merge 单。无快照的旧边不撤。执行码未改 | E1 未开工 | 不称 M4/L5 |
| 2026-09-19 | **E1**：`apply_ticket` 写边前保存 `edge_before`。读图失败不调用 `resolve`。无撤回接口 | E2 未开工 | 旧边仍不能撤 |
| 2026-09-19 | **E2**：带快照的 merge 边可两侧撤回。空身份拒绝。不写活 YAML | 无 | 不称 M4/L5 |
| 2026-09-19 | **H0 契约**：提效不放权。快照脱敏+分页；证据包≠签字；价值无基线不编数。H4/H5 默认不做。执行码未改 | H1 未开工 | 不称 M4/L5 |
| 2026-09-19 | **H1**：待批 inbox + 快照只读；按角色脱敏；批准不走新写路径 | H2 未开工 | 不称 M4 |
| 2026-09-19 | **H2**：签收证据包只读导出；封面不是签字；trace≤5；billing=null | H3 未开工 | 不称 M4 |
| 2026-09-19 | **H3**：价值翻译；租户基线隔离；无基线不显示节省人时 | H4 未开工 | 不称 M4；H4/H5 默认不做 |
| 2026-09-19 | **H4**：沙箱队列自动通过；只改队列；YAML 哈希不变；日通过率熔断；规则默认关 | H5 默认不做 | 不称出错已变成规则 |
| 2026-09-19 | **S 波**：H4 可扫队列；价值基线可写；领域模板可装；签收进度可填；`m4_claim_allowed` 仍 false | 客户真线 | 不称 M4/L5 |
| 2026-09-19 | **沙箱演练**：多角色交接只记日志；一次干跑；不翻 `allow_fleet`；不写活本体 | 舰队仍默认拒绝 | 不称多 Agent 已产品化 |
| 2026-09-19 | **JSON diff**：人批 apply 另写浅层 before/after。回滚仍用 YAML 快照。旧边无快照仍不能撤 | 不是全量事件日志 | 不称一键撤回任意变更 |
| 2026-09-19 | **案例降权**：注入时跳过反复失败且低收益的案例。不删除，不改系统提示词前缀 | 不是全量上下文淘汰 | 不称已归档 |
| 2026-09-19 | **事件预演**：白名单事件只干跑并记待批。不进 live，不推渠道，不开第二入站 | 飞书确认门仍在 | 不称主动伙伴 |
| 2026-09-19 | **联合健康度**：只读能解释/缺口/覆盖率。无案例不报覆盖率。不写活本体 | 不是签收 | 不称 L5 |
| 2026-09-19 | **缺口草稿**：schema_gap 进既有 K5 提案账本。不调用 apply | 人批仍在 | 不称已写活本体 |
| 2026-09-20 | **缺口 Diff 预览**：先投影变更并展示 Diff；确认后才进提案。不写活本体 | 人批仍在 | 不称一键修活 |
| 2026-09-20 | **H1 提案 Diff**：待批快照附带路径级 Diff；非审批角色只见路径。不批准、不写活 | 批准仍走原路由 | 不称已 apply |
| 2026-09-20 | **案例冷库**：低收益案例移出在线注入，冷库存档只供审计。不删除，不改 TBox | 降权仍在 | 不称已清洗记忆 |
| 2026-09-20 | **沙箱/live 通过率对照**：只读；live 拒绝记审计；无 live 尝试不报 live 率。不是灰度影子放行 | H4 live 仍拒 | 不称可切 live |
| 2026-09-20 | **签收准备度**：六闸门只读汇总 + 签收包验收标准/基线引导。材料齐 ≠ 已签收 | 双签仍人工 | `m4_claim` 仍 false |
| 2026-09-20 | **A8 回滚演练可记**：`rollback_drill_done` 进进度与准备度；按钮不 pause Goal / 不改 IO | 现场仍须真做演练 | 不打开 m4 |
| 2026-09-20 | **准备度清单可导出**：`GET …/signoff/prep?format=markdown`；封面不是签字 | 送审材料 | `m4_claim` 仍 false |
| 2026-09-20 | **基线试算**：`GET …/value/roi-preview`；`simulation=true`；不落盘；不是客户基线 | 写入仍须 PUT | 不打开 m4 |
| 2026-09-20 | **准备度对齐 A1–A8**：增 `kpis_visible` / `inbox_readable`；八闸门 | 现场仍须填齐 | `m4_claim` 仍 false |
| 2026-09-20 | **签收剧本 + 闸门卡片**：prep 含 how_to/owner/ui_anchor 与 6 步 playbook；试点页可跳转 | 双签仍人工 | 不打开 m4 |
| 2026-09-20 | **RUNBOOK v1.2**：日常操作指向 `/org/pilot` 剧本；§6 补值班/回滚演练进度字段 | 手册对齐代码 | 不打开 m4 |
| 2026-09-20 | **FDE 操作手册 v1.2**：入口表交叉引用组织试点/签收包；区分 FDE 交付签收 vs Org M4 | 防找错屏 | 不打开 m4 |
| 2026-09-20 | **用户操作手册对齐现状**：`knowledge-system` 附录 C v1.3；`management` / L1 UI 手册修正业务本体与组织试点入口 | 防旧路由误导 | 不打开 m4 |
| 2026-09-20 | **FDE 交付手册路径纠偏**：`02/03/01` + 签收单模板区分项目签收 vs Org 准备；本体入口改 `/knowledge/business` | 操作可照做 | 不打开 m4 |
| 2026-09-20 | **手册第二轮**：`06` SOP / `03` API 表 / `getting-started` / `management` Studio 收敛到现状入口 | 可照做 | 不打开 m4 |
| 2026-09-19 | **上下文命中率**：已注入且有反馈 / 已注入。无注入不报率。不改提示词 | 不是动作调用计数 | 不称已淘汰上下文 |

逾期两周未更新 → 标记「停滞」。

---

## 5. Phase C 决策（D6–D10）· 2026-09-18

关联：[`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md)

### D6 — 首个入站渠道

| 字段 | 内容 |
|------|------|
| 问题 | C2 首渠选飞书还是企微？ |
| **决议** | ☑ **飞书**（入站 ID=`lark`，出站 ID=`feishu`）；**单开**；企微本期不做入站 |
| 理由 | 本机双边 Webhook env 均 unset；代码侧 `AIPLAT_FDE_NOTIFY_CHANNELS` 默认以 feishu 为首；`LarkAdapter` 入站字段更完整；Gateway 示例用 feishu |
| 影响 | Org Ingress 必须维护 `lark↔feishu` 别名；C2 联调只接飞书 |
| Owner | Org 试点 Owner |
| Deadline | C2 开工前 |
| 关闭标准 | Charter §5 已写；CAPABILITIES/Runbook 同步渠道 ID |
| 状态 | ☑ 已决 2026-09-18 |

### D7 — Interface 权威存放

| 字段 | 内容 |
|------|------|
| 问题 | InterfaceSpec 放哪？ |
| **决议** | ☑ C1 曾以 `connector.live` 为单源；**C1.5 已落地（2026-09-18）**：`AIPLAT_HOME/interfaces/{id}.yaml` 覆盖种子 YAML；无 YAML 时 `live` 只读兼容；禁双写 |
| 理由 | 已有 live 块与 `org_live_adapter`；避免双源 |
| 状态 | ☑ 已决 |

### D8 — 用量账本

| 字段 | 内容 |
|------|------|
| 问题 | 本期是否做 W11？ |
| **决议** | ☑ **做薄**（异步记账、不计费）；**不阻塞** C2 / OrgRun |
| 状态 | ☑ 已决 |

### D9 — 第二业务系统

| 字段 | 内容 |
|------|------|
| 问题 | 是否并行 CRM/财务等？ |
| **决议** | ☑ **否**；守 D1 it-ops 单线 |
| 状态 | ☑ 已决 |

### D10 — 独立 Charter

| 字段 | 内容 |
|------|------|
| 问题 | Phase C 是否独立契约文件？ |
| **决议** | ☑ **是** → [`ORG_CHANNEL_INTERFACE_CHARTER.md`](./ORG_CHANNEL_INTERFACE_CHARTER.md) |
| 状态 | ☑ 已决 · C0 已生效 |

**Phase C C0 宣布用语**：  
> Org Phase C C0 于 2026-09-18 生效；首渠飞书（lark/feishu）；Interface 先 connector.live 单源；用量账本做薄不阻塞入站；第二业务系统不做；M4 客户线独立跟踪；对外仍为 L3 + 单线组织闭环（沙箱），直至 M4 签收。

**C1 开工**：☑ 2026-09-18 已宣布并落地。  
**C2 开工**：☑ 2026-09-18 已落地。  
**C3 开工**：☑ 2026-09-18 已落地。  
**C5 签收包（2026-09-18）**：[`ORG_M4_SIGNOFF_PACK.md`](./ORG_M4_SIGNOFF_PACK.md)。`c5_pack_ready` ≠ M4。`m4_claim_allowed` 恒 false。

---

## 6. K 波决策（D-K1–D-K5）· 2026-09-18

关联：[`ORG_K_WAVE_CHARTER.md`](./ORG_K_WAVE_CHARTER.md)。与 Phase C 分开，不替代 M4。

| ID | 决议 | 状态 |
|----|------|------|
| D-K1 | 试点只 it-ops | ☑ |
| D-K2 | 抽取确认、仲裁批准、提案批准分开记 actor；不新建角色名 | ☑ |
| D-K3 | 窗口 ≥3 次，或 2 次且 reward 低于现有门槛；去重、合并、过期 | ☑ |
| D-K4 | 不生成 Skill 文件；只允许 `skill_candidate=true` | ☑ |
| D-K5 | 精确键也只出建议合并单 | ☑ |

**K0 宣布**：☑ 2026-09-18。随后 F2：直写活 YAML 在令牌外拒绝。  
**F2 门禁**：☑ **2026-09-18**。`save_domain_yaml` / wiki `_write_domain_yaml` / `import_ontology` 无 `allow_live_yaml_write` 即拒绝。令牌仅 apply/rollback。  
**K1 开工 / 落地**：☑ **2026-09-18**。确认只发信号，不写活 YAML / 跨域边。  
**K2 开工 / 落地**：☑ **2026-09-18**。仲裁单 → decide → apply 才写边。  
**K3 开工 / 落地**：☑ **2026-09-18**。OrgRun `reasoning` 证据；不执行。  
**K4 开工 / 落地**：☑ **2026-09-18**。案例 overlay；无 Skill 文件。  
**K5 开工 / 落地**：☑ **2026-09-18**。重复失败只提案；`auto_apply=false`。

---

## 7. V 波决策（D-V1–D-V7）· 2026-09-19

关联：[`ORG_V_WAVE_CHARTER.md`](./ORG_V_WAVE_CHARTER.md)。验收波。不替代 M4，不重做 K 波与 Phase C。

| ID | 决议 | 状态 |
|----|------|------|
| D-V1 | 只做 V0–V5。客户真线签收不在本波。`c5_pack_ready` ≠ 已签收。程序不得把 `m4_claim_allowed` 设为 true | ☑ |
| D-V2 | `trace_origin` 闭集与继承规则以 V Charter §3 为准。直接跑不得回填抽取单。回放只精确匹配，缺步不补假记录 | ☑ **2026-09-19** 只读回放已落地 |
| D-V3 | `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY` 本波不删。组织任务与 K5 启动时必须断言为 false，否则 `edge_auto_apply_forbidden` 并拒绝。断言先于 V1 回放合并 | ☑ **2026-09-19** 断言已落地，先于回放 |
| D-V4 | 试点入口只能调用已有开跑路由。该路由先做一次 `authorize_console_run`。飞书入站不重复调用。渠道方向从 `ingress_status` 读 | ☑ **2026-09-19** |
| D-V5 | 提案批准改为 PolicyGate 一次。body 里的 `approver_role` 不再当作授权。批准后活 YAML 哈希不变，写入仍只走 `apply_proposal` | ☑ **2026-09-19** |
| D-V6 | 不扩大回滚。可回滚与不可回滚两列必须出现在 API 与面板。边的回滚另立项 | ☑ **2026-09-19** 边界已明示。另立项为 E 波，E0 只写契约 |
| D-V7 | 不新建角色名。五组菜单不删 | ☑ |

**V0–V5**：☑ **2026-09-19** 收口。回放只读，开跑先过岗位，批准只经 PolicyGate，回滚边界已写明。不是 M4，也不是 L5。

---

## 8. E 波决策（D-E1–D-E6）· 2026-09-19

关联：[`ORG_EDGE_ROLLBACK_CHARTER.md`](./ORG_EDGE_ROLLBACK_CHARTER.md)。不替代 M4，不扩大 YAML 回滚。

| ID | 决议 | 状态 |
|----|------|------|
| D-E1 | 只撤回 `apply_ticket` 在 `decision=merge` 时写下的 `_cross_domain`。`add` 和其他决定不写边，也不撤 | ☑ E0 |
| D-E2 | 写入前必须把两侧旧值存进该单的 `edge_before`。没有这份快照的旧边拒绝，原因 `edge_before_missing`。不回填历史 | ☑ **2026-09-19** 快照与拒绝均已落地 |
| D-E3 | 两侧一起恢复。当前标记已不是这张单的对端则 `edge_superseded`，不顺着链条撤 | ☑ **2026-09-19** |
| D-E4 | 不调用 `rollback_proposal`，不写活 YAML。范围接口的两列在 E2 落地前不改口 | ☑ **2026-09-19** 两列已改口；活 YAML 未写 |
| D-E5 | 新撤回路由只认 `X-AIPLAT-ROLE`，空身份拒绝，不新建角色。本波不改旧 apply 路由的 body 身份 | ☑ **2026-09-19** |
| D-E6 | 撤回后同一张单不得再次 apply。重新对齐另开一张单 | ☑ **2026-09-19** |

**E0 宣布**：☑ **2026-09-19**。  
**E1**：☑ **2026-09-19**。写入前快照已落地。  
**E2**：☑ **2026-09-19**。带快照的 merge 边可撤回。不是 M4。

---

## 9. H 波决策（D-H1–D-H8）· 2026-09-19

关联：[`ORG_H_WAVE_CHARTER.md`](./ORG_H_WAVE_CHARTER.md)。提效不放权。不替代 M4。

| ID | 决议 | 状态 |
|----|------|------|
| D-H1 | 必做 H0–H3；H4、H5 可另宣布 | ☑ **H4、H5 已宣布并落地** |
| D-H2 | 快照与证据包只读。禁止为补全跑 LLM。缺信息写「该信息未发生」。批准写路径不新增第二套 | ☑ **2026-09-19** inbox/snapshot 已落地 |
| D-H3 | 快照必须分页；允许秒级延迟；按角色字段脱敏。内部审批 ≠ 全量明文 | ☑ **2026-09-19** |
| D-H4 | 证据包封面声明不是签字。客户可见过滤。代表性 trace ≤ 5。预留 `sandbox_mode`，本波不附模拟联调 | ☑ **2026-09-19** evidence-pack 已落地 |
| D-H5 | 价值翻译可配置基线；按 `tenant_id` 隔离；必带 `baseline_source`；`missing` 时不显示节省人时 | ☑ **2026-09-19** value/translation 已落地 |
| D-H6 | H4 若做：只改队列状态；永不自动 `apply_proposal`/`resolve`；单日自动通过率 >20% 熔断；auto-audit 仅治理角色 | ☑ **2026-09-19** 无规则文件时沙箱开；live 拒 |
| D-H7 | H5 若做：只到草稿包 + 人批上架；打包格式另设计，不在本波预挖 | ☑ **2026-09-19** JSON 草稿；人批后 register；不写 SKILL.md |
| D-H8 | Mock 沙箱工具包、全量 Event Sourcing、接口限流实现不进本波。限流意图可记在 H Charter §7 | ☑ |

**H0 宣布**：☑ **2026-09-19**。  
**H1**：☑ **2026-09-19**。inbox + 快照只读。  
**H2**：☑ **2026-09-19**。证据包只读导出；不是签字。  
**H3**：☑ **2026-09-19**。价值翻译；无基线不编节省人时。  
**H4**：☑ **2026-09-19**。无规则文件时沙箱开关打开；live 拒绝。不写活本体。  
**H5**：☑ **2026-09-19**。草稿包；人批后才登记市场。不自动上架。不是 M4。

---

## 10. S 波决策（D-S1–D-S4）· 2026-09-19

关联：[`ORG_S_WAVE_CHARTER.md`](./ORG_S_WAVE_CHARTER.md)。补齐吞吐/基线/模板/签收准备。不替代 M4。

| ID | 决议 | 状态 |
|----|------|------|
| D-S1 | H4 须可从试点页扫描；seed `approval_rules.yaml`；live 永不扫 | ☑ |
| D-S2 | 租户可写价值基线；无基线仍不编人时；跨租户禁止 | ☑ |
| D-S3 | 领域模板安装经 CoreFacade；动作脚手架只写 `org/action_drafts`，不进 `actions/`；禁 harness 硬编码新域名 | ☑ |
| D-S4 | 值班/双签可持久化并进证据包；`m4_claim_allowed` 恒 false | ☑ |

**S0 宣布**：☑ **2026-09-19**。  
**S1–S4**：☑ **2026-09-19** 落地。不是 M4。
