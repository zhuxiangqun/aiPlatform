# HYBRID_ENTERPRISE 附录：交付规格与 Citation UX 验收

> 版本：v1.0 | 日期：2026-10-14  
> 适用范围：Pi 混合回连 enterprise 出厂交付 + KB 引用强制展示  
> 主文档：[`HYBRID_ENTERPRISE.md`](./HYBRID_ENTERPRISE.md)  
> 边界权威：`docs/architecture/plans/pi-thin-runtime.md`

## 0. 定位与原则

| 项       | 说明                                                                                                                     |
| ------- | ---------------------------------------------------------------------------------------------------------------------- |
| 本文档是什么  | ① 交付产品化规格 + ② Pi KB citation UX 验收条，可直接交付开发执行                                                                          |
| 本文档不是什么 | 不是再造 RAG/Agent 内核；不在 Pi 内重实现 PolicyGate / Memory / Approval / 执行封存（`done_verify`·QR·`task_model_lock` 见主文档非目标与矩阵 §2.6）/ UI E2E 侦察-自愈闭环（见 `e2e_test` Skill） |
| 架构原则    | Pi = 执行壳；aiPlat = 治理与企业能力；只加 `aiplat_*` 桥，不搬引擎                                                                         |
| 前置状态    | hybrid live 已绿（Memory / Tools / KB / Approvals / 门禁；`AIPLAT_HYBRID_LIVE_SMOKE_OK`）                                     |
| 对齐话术    | 系列教新手「从零拼出可变现 Agent」；aiPlat 已是企业操作系统，缺的是把现有能力收成可卖的 SKU 与交付节奏。Pi 对齐「可带走成品 + 模块叠加」，用混合回连吃企业 RAG/审批/记忆，不把系列第 8–28 篇在扩展里重做 |

**借鉴原则**：抄交付节奏与产品叙事，不抄引擎实现。

---

## 1. 优先级链与依赖

```
[已完成] hybrid live ✓
    │
    ├─ ① 交付产品化（出厂去调试清单 + 客户状态页 + 使用边界一页纸）
    │      └─ 前置：交付清单归属（§2.0，已定 A+B）
    │
    ├─ ② Pi KB citation UX（引用块 + 无源降级；先 V2/V3a/V6）
    │      └─ 依赖：KB 桥已通（已满足）
    │
    ├─ ③ 成本叙事接入交付报告（cache 命中 + 模型分流；¥ 可选）
    │      └─ 依赖：semantic_cache + best_model_for_purpose（计量出口已合入）
    │
    └─ ④ 托管 SKU ↔ 值班板/入库/巡检（客户可见层）
           └─ 依赖：governance cron + daemon_jobs（已有）
```

**执行顺序**：① → ② → ③ → ④。① 与 ② 可并行（不同模块）；③④ 在 ① 交付模板定型后接入。

---

## 2. ① 交付产品化规格

### 2.0 前置依赖：交付清单归属（已决策）

| 方案                | 说明                   |  决策  |
| ----------------- | -------------------- | :--: |
| A. Builder 出厂自动生成 | 构建产物时自动附带清单骨架 + 扫描结果 | ✅ 执行 |
| B. FDE 签收勾选       | 交付时人工确认并签字           | ✅ 执行 |

**采用 A+B**：Builder/出厂生成骨架与扫描结果 → FDE（或交付负责人）勾选签字 → 纳入交付包。  
**模板库**：`docs/manuals/fde/fde-delivery-manual.md`（及同目录模板）。  
**Owner**：清单模板 = FDE 手册维护者；扫描脚本 = builder / 出厂门禁。

### 2.1 去开发化检查清单（出厂门禁）

落地：挂在 builder 出厂门禁或 FDE 交付手册，**不新建微服务**。

| # | 检查项   | 验收条件                                                            |
| - | ----- | --------------------------------------------------------------- |
| 1 | 调试痕迹  | 产物中无面向客户的 `console.log` / 裸 `print` / `debug=True` / 临时 TODO 暴露 |
| 2 | 裸环境变量 | 无硬编码密钥、无明文 API Key、无客户包内必依赖的本机 `localhost:xxxx` 残留              |
| 3 | 假绿端点  | 无 mock/stub 伪装真实能力；接线能力有真实后端响应                                  |
| 4 | 未接线能力 | feature-flag 掩盖的未完成功能不暴露，或明确标「预览」                               |
| 5 | 标准化输出 | Agent 回复有统一结构（标题/正文/引用/异常），非裸调试 JSON                            |
| 6 | 异常兜底  | 工具失败退回包内 SOP；失败卡片 + 可重试；不向用户抛栈                                  |
| 7 | 一键启动  | 含启动说明/脚本；客户无需手搓全栈环境即可跑 Pi 包（企业回连按文档选配）                          |

执行：扫描不通过 → 阻断出厂并返回修复清单；通过 → 「出厂合格证」附交付包；FDE 签字归档。

### 2.2 标准化交付五步 → 客户可见模板

| 步骤 | 模板                                | 客户可见 |
| -- | --------------------------------- | :--: |
| 1  | 范围确认单（边界 / 含不含 / 数据范围 / 用户上限）     | ✅ 签字 |
| 2  | 部署确认单（环境 / 依赖 / 网络 / 端口域名）        | ✅ 确认 |
| 3  | 多场景测试报告（用例 / 通过率 / 已知限制）          | ✅ 验收 |
| 4  | 使用边界一页纸（能做/不能做 / FAQ TOP5 / 联系方式） | ✅ 留存 |
| 5  | 售后/托管协议（SLA / 响应 / 续费 / 升级路径）     | ✅ 签字 |

不允许跳过模板；每次交付基于模板填写。

### 2.3 运维托管三级套餐 → SKU 叙事

来源映射：系列 **第 39 篇**（运维托管）+ **第 41 篇**（交付级成品感）。  
落地：挂在 governance 值班板 + daemon，讲「月费价值」，不新建托管微服务。

| 套餐      | 定位 | 包含（客户语言）                     | 技术落点（已有）                      |
| ------- | -- | ---------------------------- | ----------------------------- |
| L1 基础巡检 | 入门 | 存活监控、告警、月度运行报告               | daemon_jobs + governance cron |
| L2 标准入库 | 主力 | L1 + 入库、检索调优、cache 命中报告、库健康分 | KB + rerank + semantic_cache  |
| L3 高级监控 | 旗舰 | L2 + 低置信监控、小版本迭代、专属值班入口      | Quality Bus + eval + 值班板      |

L2 库健康分面板（属 ④，规格见 §5）：本周入库 N / 漏召 TOP5 / 低置信 TOP5 / cache 命中率 + **建议补哪些文档**（指标→运营动作）。

---

## 3. ② Pi KB Citation UX 验收条

来源：系列第 26 篇「溯源」商用价值；实现路径：**只改 Pi 侧 KB 工具回复契约 / 渲染**，不动桥协议、不新建 RAG 管道。

### 3.0 现状 vs 缺口（防低估工时）

| 现状（已有）                                                              | 缺口（本规格新增）                                            |
| ------------------------------------------------------------------- | ---------------------------------------------------- |
| `enterprise_kb.ts` 将 `items`/`citations` 打成 `[src] snippet`（最多 5 条） | 统一「参考文献」块与固定无源开场文案                                   |
| system prompt：`do not invent citations`                             | enterprise 下强制无源前缀（V2）                               |
| —                                                                   | V3a Markdown 引用契约；V3b 富客户端展开为可选                      |
| —                                                                   | V1 句级来源、V5「未验证」：**一期 best-effort（prompt）**，非硬 NLP 门禁 |

### 3.1 溯源三段式（实现分层）

```
段1 检索绑源          段2 强制引用契约           段3 输出参考文献
    │                     │                         │
    aiplat_kb_retrieve    无源固定开场；有源则         文末列表 ≤5
    结果带 source         正文只陈述有源内容            （与 slice(0,5) 对齐）
```

### 3.2 验收条件

| #   | 验收项                                        | 分期               |                  enterprise                  | Pi-only |
| --- | ------------------------------------------ | ---------------- | :------------------------------------------: | :-----: |
| V2  | 无检索结果：回复以「未在知识库中找到相关内容」开头，禁止编造             | **P0 必做**        |                      强制                      |    强制   |
| V3a | Markdown：`[来源: 文档名]` + 文末「参考文献」含 ≤200 字片段  | **P0 必做**        |                      强制                      |    可选   |
| V6  | 单次引用 ≤5；超出取 top-5 by score，可注明「共 N 条展示前 5」 | **P0 必做**        |                      强制                      |    强制   |
| V1  | 事实陈述附带来源标记（基于工具返回，非 NLP 事实句检测）             | P1 prompt/契约 ✅   |                      强制                      |    可选   |
| V5  | 无源支撑内容标「（未验证）」或避免输出                        | P1 best-effort ✅ |                     强制意图                     |   不要求   |
| V3b | 点击展开原文片段（`<details>`）                      | P2 富客户端 ✅        | 可选（`AIPLAT_ENTERPRISE_KB_CITATION_EXPAND=1`） |    可选   |

**阻断出厂（enterprise）**：V2 + V3a + V6。V1/V5/V3b 不阻断第一期。

### 3.3 回复格式规格（V3a）

```
根据知识库记录，……：
1. …… [来源: 报销管理制度.pdf]
2. …… [来源: 财务流程手册.docx]

── 参考文献 ──
① 报销管理制度.pdf — "……"（≤200 字）
② 财务流程手册.docx — "……"（≤200 字）
```

### 3.4 异常路径

| 场景            | 行为                       | 验收           |
| ------------- | ------------------------ | ------------ |
| KB 空结果        | 固定开场「未在知识库中找到相关内容」       | V2           |
| 有结果但 score 均低 | 可标注「以下信息置信度较低」，仍附来源      | V3a          |
| 桥不可达          | 退回包内 SOP；标注「知识库暂不可用」；不编造 | 既有 soft-fail |
| 来源 >5         | top-5；可注明共 N 条           | V6           |

### 3.5 配置形态（⚠️ 语义规格，非现行 YAML）

> **勿新建 `kb_citation.yaml`。** Pi 企业侧现行配置仅为 **环境变量**（见 [`HYBRID_ENTERPRISE.md`](./HYBRID_ENTERPRISE.md)）。下列表是**语义意图**，落地用 env / extension options。

Pi 企业侧现行配置为 **环境变量**（见主文档）。下列为**语义意图**，落地可用 env 或 extension options，**勿假定已存在 `kb_citation` YAML 文件**。

| 语义键                        |                     enterprise 默认                    | Pi-only 默认 | 对应验收 |
| -------------------------- | :--------------------------------------------------: | :--------: | ---- |
| `enforce_no_hallucination` |                         true                         |    true    | V2   |
| `reference_list_markdown`  |                         true                         |    false   | V3a  |
| `max_sources`              |                           5                          |      5     | V6   |
| `enforce_source_tag`       |                       true（P1）                       |    false   | V1   |
| `unverified_tag`           |                       true（P1）                       |    false   | V5   |
| `expandable_reference`     | env `AIPLAT_ENTERPRISE_KB_CITATION_EXPAND`（默认 false） |    false   | V3b  |

建议 env 命名（实现时再定，避免与主文档表冲突）：例如 `AIPLAT_ENTERPRISE_KB_CITATION=1` 打开 V2+V3a+V6。

---

## 4. ③ 成本叙事接入交付报告

| 指标       | 数据来源                                                                | 客户可见形式                   | 一期状态                   |
| -------- | ------------------------------------------------------------------- | ------------------------ | ---------------------- |
| API 调用总量 | billing breakdown 或 `kb/metrics.total_queries`                      | 「本月共调用 N 次」              | ✅ 有则展示                 |
| 缓存命中率    | `get_semantic_cache().stats`                                        | 「M 次命中 / 命中率 %」          | ✅ **优先**               |
| 模型分流     | 配置快照 + **LLM syscall `args.purpose`**（优先）/`model_selection_log`（回退） | 简单/复杂→模型表 + purpose/档位占比 | ✅ 无数据不编造 %；完成调用优先于选择次数 |
| 空检索/无效拦截 | `kb/metrics.empty_retrieve_count`（syscall_events 空命中）               | 「空检索拦截次数 N」+ 无答案率参考      | ✅ 已接                   |
| 月度成本 ¥   | `billing_records` 或 `AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT`        | 账单权威 ¥ 或估算 ¥             | ✅ **可选**；无价目不编造        |

**出口**：

- `GET /platform/delivery/cost-report`（`?format=markdown` 可直接拿成本页）
- `python3 scripts/render_delivery_cost_report.py --out COST_REPORT.md`（`--fixture` 离线）
- `export_pi_bundle` 写入包内 `COST_REPORT.md`

叙事：回答「一个月花多少」用这一页；优先给命中率与调用次数，避免只甩 token 术语。

---

## 5. ④ 托管 SKU 对齐（概要）

| SKU | 已有能力                          | 客户可见层                                                                               |
| --- | ----------------------------- | ----------------------------------------------------------------------------------- |
| L1  | daemon_jobs + governance cron | ✅ 月度运行报告（`MONTHLY_OPS_REPORT.md` + `GET /platform/delivery/monthly-ops-report`）     |
| L2  | KB + rerank + semantic_cache  | ✅ 库健康分面板（见下 + `KB_HEALTH.md`）                                                       |
| L3  | Quality Bus + eval + 值班板      | ✅ 专属值班台（`L3_DUTY_DESK.md` + `GET /platform/delivery/l3-duty-desk` + `/aiplat-duty`） |

### 5.1 库健康分面板（示意）

```
知识库健康分: 82/100
本周入库: 12 条
漏召 TOP5: …
低置信回答 TOP5: …
缓存命中率: 34%
建议: 补充「差旅报销标准」「年假折算规则」文档
```

末行「建议」把指标变成运营动作，服务续费与入库动作。

---

## 6. 刻意不借鉴清单

| 系列内容                       | 原因                                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------- |
| 闲鱼/成交话术/报价数字               | 销售物料，不进仓库核心                                                                                       |
| 「先选 LangChain/CrewAI」      | 与内核无关架构冲突                                                                                         |
| 在 Pi/生成物内再实现 RAG/Memory/审批 | 违反混合原则                                                                                            |
| APScheduler 级定时            | 已有 daemon_jobs + governance cron                                                                  |
| CrewAI 级多 Agent「审议」        | **层级不同**：aiPlat 在治理层（审批/门禁/Quality Bus）仲裁；CrewAI 式协作是执行层仲裁——不是同一件事的强弱版。见系列第 59 篇时勿加「审议 Agent」平行实现 |

---

## 7. 系列篇号交叉索引

| 本章节              | 系列篇号      | 借鉴方式              |
| ---------------- | --------- | ----------------- |
| §2.1 去开发化        | 29–31、43  | 出厂门禁 checklist    |
| §2.2 交付五步        | 30、32     | 客户可见模板（对齐 FDE 手册） |
| §2.3 / §5 托管 SKU | **39**、41 | 值班板 + daemon 叙事   |
| §3 Citation UX   | 26        | 零内核复制，改渲染/契约      |
| §4 成本叙事          | 31、45     | 交付报告成本页           |
| §6 不借鉴           | 8–28、59   | 明确不进核心            |

---

## 8. 开发落地检查

### 8.1 ② Citation（第一期）— 已合入

实现：`extensions/enterprise_kb_citation.ts` + `enterprise_kb.ts`；冒烟 `enterprise_kb_citation_smoke.mjs`。

- [x] 空结果 → 固定 V2 开场文案（工具返回层，不依赖模型自觉）
- [x] 有结果 → V3a Markdown 参考文献块，片段 ≤200 字，条数 ≤5（V6）
- [x] system prompt 与桥失败路径禁止编造 citation（失败文案含「知识库暂不可用」）
- [x] `enterprise_kb_citation_smoke`；`enterprise_kb_smoke` / hybrid live 仍应绿
- [x] 不引入新的平台 RAG 管道或 Pi 内 Memory/Approval 实现

**P1 增强已合入**：

- [x] **A. 低置信标注**（§3.4）：score 全部 < `LOW_CONFIDENCE_THRESHOLD`(0.5) 时插入 ⚠️ 警告；仅当 score 非零时触发（避免无 score 数据时误报）；system prompt 增加置信度传递指令
- [x] **B. 来源去重**：`dedupeBySource()` 按 source 名去重，保留最高 score 片段；避免同一文档占多个参考文献槽位
- [x] **C. 端到端合规验证**：`enterprise_hybrid_live_smoke.mjs` step 3b 用 `spawnSync --experimental-strip-types` 将 live KB 响应喂入 citation formatter，验证 ref block / source tag / empty prefix；soft-skip 若 strip-types 不可用
- [x] 冒烟扩展：dedup 测试（同 doc_id 不同 snippet）、低置信测试（全低/全高/无 score/混合）、E2E soft-skip

**P2 V3b 已合入**：

- [x] `AIPLAT_ENTERPRISE_KB_CITATION_EXPAND=1` → 参考文献包在 HTML `<details><summary>…点击展开</summary>…</details>`（默认仍 V3a 纯文本头）

### 8.2 ① 出厂清单挂接（A+B）— 已合入

- [x] `scripts/scan_pi_bundle_delivery.py`（密钥/debug/假绿等规则）
- [x] `export_pi_bundle.py` 导出时写入 `DELIVERY_CHECKLIST.md` + `delivery_scan.json` + `USAGE_BOUNDARY.md`
- [x] 导出包必含 `enterprise_kb_citation.ts`（修复 KB import 断裂）
- [x] 导出包版本戳：`BUNDLE_VERSION` + `aiplat-export.json.build`（`bundle_version` / `git_sha` / `build_time`；可用 `AIPLAT_PI_BUNDLE_VERSION` 覆盖）
- [x] FDE 手册 §8 签收表（`docs/manuals/fde/fde-delivery-manual.md`）
- [x] `enterprise_delivery_scan_smoke.mjs`；默认导出**不**因 warning/error 阻断（CI 可用 `--strict`）

### 8.3 ③ 成本页计量出口 — 已合入

- [x] `aiPlat-platform/delivery/cost_report.py`（cache / KB / billing / 分流策略）
- [x] `GET /platform/delivery/cost-report`（json + markdown）
- [x] `scripts/render_delivery_cost_report.py`；导出写入 `COST_REPORT.md`
- [x] 无 `AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT` 时不编造 ¥ 节省
- [x] `aiPlat-platform/tests/test_delivery_cost_report.py` + delivery scan smoke 校验 COST_REPORT.md
- [x] 模型分流流量占比：`model_selection_log.json` → purpose/档位 %（选择次数；无日志不编造）
- [x] LLM 完成调用级 purpose：`sys_llm_generate(purpose=…)` 写入 syscall `args.purpose`；成本页优先聚合完成调用，回退选择日志
- [x] 高流量调用点透传 purpose：ReAct `inference` / pipeline stage LLM / skills base / autoreview / extractor / materials_chat / loop facade
- [x] `peek_routing_purpose` ContextVar：同任务 `best_model_for_purpose` 后未显式传 purpose 的 `sys_llm_generate` 可自动带上
- [x] 长尾 purpose：`_SOURCE_TO_PURPOSE` + workspace_agents / fde_ask / prompt_app / kb_planner / tool_bootstrap / moa / memory / query_rewriter / hyde
- [x] purpose 占比冒烟：`scripts/smoke_delivery_purpose_share.py`（离线 seed → `usage_share_source=llm_syscall`）；delivery scan 校验 COST_REPORT「流量占比」
- [x] purpose→model 表：`best_model_for_purpose` 失败时回填 `model_selection_log` 最近选用（不编造模型名）

### 8.4 ④ 库健康分面板 — 本迭代


- [x] `delivery/kb_health.py`（score 公式 + metrics/stats/cache + 建议）
- [x] `GET /platform/delivery/kb-health`；导出 `KB_HEALTH.md`；`/aiplat-kb-health`
- [x] 漏召/低置信 TOP best-effort（syscall_events）；无数据不阻断
- [x] 零流量 → `insufficient_data` / 「数据不足」（不编造 60 分）
- [x] `kb/query_telemetry.py`：`POST /platform/kb/query`（及 collections/query）写 `knowledge_retrieve`/`platform_kb_retrieve`
- [x] 规格与检查表：[`HYBRID_ENTERPRISE_KB_HEALTH.md`](./HYBRID_ENTERPRISE_KB_HEALTH.md)
- [x] **结构化检索接线**：`kb/platform_query.py` 默认本地 FTS/LIKE（`AIPLAT_KB_QUERY_CRAG=1` 才走 `query_elements`）；不再走 prompt `knowledge_query`；响应含 `kb.items`/`citations`，Pi citation UX 与遥测可吃到真实命中

**已补（v2 加固）**：平台 HTTP 断路器 + `AIPLAT_PLATFORM_BASE_PATH`（`extensions/enterprise_http.ts`，各桥 `platformFetch`；导出必含）。

**已补（独立 TOP）**：`GET /platform/kb/miss-top` + `GET /platform/kb/low-confidence-top`（`delivery/kb_health.kb_miss_top` / `kb_low_confidence_top`）。

**已补（周报 + cache-stats）**：`kb_health_archive`（默认每 168h 写 `~/.aiplat/governance/reports/kb-health-YYYY-WW.md`）+ `GET /platform/kb/cache-stats`。

**已补（空拦截 + V1/V5）**：成本页 `empty_retrieve_count`；citation 工具返回层 + system prompt 明确 V1/V5。

**已补（工具分级）**：`AIPLAT_ENTERPRISE_TOOLS_L1|L2|L3` + `TOOL_CEILING`；L3 须审批桥；扁平 `ENTERPRISE_TOOLS` 仍兼容。

**已补（V3b）**：`AIPLAT_ENTERPRISE_KB_CITATION_EXPAND=1` → `<details>` 可展开参考文献。

**已补（文档对齐）**：`HYBRID_ENTERPRISE_KB_HEALTH.md` §0/§1.2/§3.2/§5 与代码一致——`miss-top` / `low-confidence-top` / `cache-stats` 标为 ✅ 已合入（不再写「需补 endpoint」）。

**已补（L1 月度运行报告）**：`delivery/monthly_ops_report.py` + `GET /platform/delivery/monthly-ops-report`；导出 `MONTHLY_OPS_REPORT.md`（daemon 存活 + 成本 + KB 健康合成；无数据不编造）。

**已补（L3 专属值班台）**：`delivery/l3_duty_desk.py` + `GET /platform/delivery/l3-duty-desk` + `/aiplat-duty` + 导出 `L3_DUTY_DESK.md`（`AIPLAT_L3_DUTY_CONTACT/CHANNEL/HOURS`；无配置不编造联系人）。

**下一刀（可选）**：hybrid ①–④ 客户可见层（含 L1/L2/L3）已齐；按客户开通 L3 时配置值班 env 并保持 platform 加载当前代码。
