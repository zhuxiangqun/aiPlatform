# Pi + aiPlat 企业级混合

> 产品锁定：默认 **Pi-only**；企业级 = **Pi 壳 + aiPlat 回连**。  
> **已接线**：只读 KB + 允许列表工具代理 + **原生工具门禁桥** + **会话摘要 Memory 回写** + **审批等待桥**。  
> **分层**：Pi = 执行内核；aiPlat = 平台治理。不是两套平权产品。  
> 权威边界（上下文/压缩/学习归属）：`docs/architecture/plans/pi-thin-runtime.md` §双模式内涵 / §上下文·压缩·学习。

## 原则

1. 用户侧始终以 Pi（或薄 HTTP）为对话宿主——不要求用户默认安装全栈 aiPlat。
2. 包内能力（SOP / skills / handler）在离线/断连时仍可用；**Pi-only 默认不具备企业权限/审计/成本**，不可当无人值守生产默认。
3. 企业能力不复制进 Pi 进程，经认证 API 调用平台（PolicyGate 仍在平台/Core 侧执行一次）。
4. **能力重叠 ≠ 交付重复**：平台白皮书里的 Agent/工具/多模型不取消 Pi 交付；Pi 解决「产物怎么带走、怎么轻量跑」。
5. 对外入口：企业客户认 aiPlat（或本混合回连）；禁止叙事成「再装一套平行平台」。
6. **企业意图下原生副作用不得绕过平台门禁**：`AIPLAT_ENTERPRISE=1` 时默认拦截 bash/write/edit/powershell，迫使副作用走 `aiplat_tool_execute`。
7. **接 Pi 不为补上下文**：会话内 compaction 归 Pi；跨会话 Memory/学习归 aiPlat。混合桥只投递/等待，不搬引擎。

## 环境变量

| 变量 | 含义 |
|------|------|
| `AIPLAT_PLATFORM_URL` | 平台基址。两种等价本地写法：`http://127.0.0.1:8003`（直连 platform，挂载 `/platform/*`）或 `http://127.0.0.1:8000/api`（management GW）。**禁止** `http://host:8003/api`（会拼成 `/api/platform/*` → 404）。扩展内 `normalizePlatformBaseUrl` 会纠偏 |
| `AIPLAT_PLATFORM_BASE_PATH` | 可选显式挂载前缀（如 `/api`）。URL 路径为 `/` 时写入该前缀，**跳过**端口猜纠偏。用于非 8000/8003 反代；标准本地 8003 直连请**勿**设 |
| `AIPLAT_PLATFORM_CIRCUIT` | 平台 HTTP 断路器（默认开）。设 `0`/`false` 关闭。连续失败后跳过请求，避免超时堆积 |
| `AIPLAT_PLATFORM_CIRCUIT_FAILURES` | 打开断路器的连续失败阈值（默认 3） |
| `AIPLAT_PLATFORM_CIRCUIT_COOLDOWN_MS` | 断路器冷却毫秒（默认 30000）后再试 half-open |
| `AIPLAT_KB_HEALTH_ARCHIVE_HOURS` | 平台进程周报归档间隔小时（默认 168；`0` 关闭）。写入 `AIPLAT_KB_HEALTH_REPORT_DIR` 或 `~/.aiplat/governance/reports/kb-health-YYYY-WW.md` |
| `AIPLAT_KB_HEALTH_REPORT_DIR` | 可选；KB 健康周报存档目录 |
| `AIPLAT_CORE_URL` | 可选；工具执行基址。裸 `http://host:8002` 会自动补 `/api/core`。未设时从 PLATFORM_URL 推导（`:8003`→`:8002/api/core`，`…/api`→`…/api/core`） |
| `AIPLAT_TENANT_TOKEN` / API Key | 身份注入；权限判断在平台 PolicyGate / RBAC |
| `AIPLAT_ENTERPRISE=1` | 启用回连意图；未设则严格 Pi-only。**同时默认打开原生工具门禁**（无需 URL/token） |
| `AIPLAT_KB_COLLECTION_ID` | KB 集合（默认 `default`） |
| `AIPLAT_ENTERPRISE_TOOLS` | **工具允许列表**（逗号分隔，扁平/兼容）。空且未设 L1/L2/L3 = 工具代理关闭（仅 KB） |
| `AIPLAT_ENTERPRISE_TOOLS_L1` | 可选；只读工具分级列表（如检索/列表） |
| `AIPLAT_ENTERPRISE_TOOLS_L2` | 可选；计算类工具分级列表 |
| `AIPLAT_ENTERPRISE_TOOLS_L3` | 可选；写操作/高风险工具；执行须 `AIPLAT_ENTERPRISE_APPROVAL=1` |
| `AIPLAT_ENTERPRISE_TOOL_CEILING` | 可选；会话最高工具等级 `L1`/`L2`/`L3`（默认 `L3`）。高于 ceiling 的工具不进 allowlist |
| `AIPLAT_ENTERPRISE_ALLOW_NATIVE=1` | 信任运维逃生：关闭原生门禁（bash/write 等恢复） |
| `AIPLAT_ENTERPRISE_TOOL_GATE=0` | 仅关闭原生门禁，保留 KB/工具混合 |
| `AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST` | 额外放行原生工具（可覆盖默认 block，如 `bash`） |
| `AIPLAT_ENTERPRISE_NATIVE_BLOCKLIST` | 额外拦截原生工具（如 `read`） |
| `AIPLAT_ENTERPRISE_MEMORY=1` | 启用会话摘要回写（须同时有 URL/token）；空=关闭 |
| `AIPLAT_ENTERPRISE_MEMORY_AUTO=0` | 仅关闭 `session_shutdown` 自动 flush；保留 `aiplat_memory_capture` 工具 |
| `AIPLAT_ENTERPRISE_SESSION_ID` | 可选；写入 capture 的 `session_id` |
| `AIPLAT_ENTERPRISE_APPROVAL=1` | 启用审批等待桥（须 URL/token）；空=关闭。**不**在 Pi 内 approve/reject |
| `AIPLAT_ENTERPRISE_APPROVAL_POLL_MS` | `aiplat_approval_wait` 轮询间隔（默认 2000） |
| `AIPLAT_ENTERPRISE_APPROVAL_WAIT_MS` | 等待超时（默认 120000） |
| `AIPLAT_ENTERPRISE_KB_CITATION` | KB 引用契约（V2/V3a/V6）。enterprise 下**默认开**；设 `0`/`false` 可关（回退旧版片段 dump）。见 [`HYBRID_ENTERPRISE_DELIVERY.md`](./HYBRID_ENTERPRISE_DELIVERY.md) §3 |
| `AIPLAT_ENTERPRISE_KB_CITATION_EXPAND` | V3b：`1` 时参考文献用 HTML `<details>` 可展开；默认关（V3a 纯文本头） |
| `AIPLAT_L3_DUTY_CONTACT` | L3 专属值班联系人/邮箱（未设则值班页标 unavailable，不编造） |
| `AIPLAT_L3_DUTY_CHANNEL` | 可选；值班通道（如飞书群/热线） |
| `AIPLAT_L3_DUTY_HOURS` | 可选；值守时段说明（默认话术「按托管协议 SLA」） |
| `AIPLAT_DELIVERY_COST_CNY_PER_CACHE_HIT` | 可选；成本页缓存节省估算单价（未设不展示 ¥） |

## 术语（本文档体系）

| 术语 | 含义 |
|------|------|
| **混合回连** | 厂外：Pi 执行壳经认证 API 调用 aiPlat 治理能力（KB/工具/门禁/Memory/审批），不搬引擎 |
| **薄 Runtime** | 可带走的 Pi 包（extensions + export/ZIP）；断连时退回包内 SOP/skills |
| **回连能力阶梯** | 本文 §阶梯 1→5（KB→工具→门禁→Memory→审批）；产品主路径 |
| **交付优先级链** | [`HYBRID_ENTERPRISE_DELIVERY.md`](./HYBRID_ENTERPRISE_DELIVERY.md) ①②③④（出厂清单→Citation→成本→库健康）；**不是**阶梯 1–5 的别名 |
| **厂内轴（A）** | [`FACTORY_IN_EXPERIMENT.md`](./FACTORY_IN_EXPERIMENT.md) 方式四：**⓪ 合并关闭**（`blank_not_proven`）；Execute 旁路已拆；仅留离线探针 |

## 回连能力阶梯

| # | 能力 | 状态 | 合入线索 | 入口 |
|---|------|:----:|----------|------|
| 1 | 只读知识检索 | ✅ | KB 桥 + 结构化检索 [#283](https://github.com/zhuxiangqun/aiPlatform/pull/283) | `aiplat_kb_retrieve` → `POST /platform/kb/query` |
| 2 | 工具代理（允许列表） | ✅ | `enterprise_tools` 扩展 + smoke | `aiplat_tool_execute` → `POST …/tools/{name}/execute` |
| 3 | 原生工具门禁桥 | ✅ | `enterprise_tool_gate`；enterprise 默认 fail-closed | `tool_call` block + `setActiveTools`；默认禁 bash/write/edit/powershell |
| 4 | 会话摘要回写 Memory | ✅ | `enterprise_memory` → `POST /platform/memory/capture` | 工具 + `session_shutdown` 软 flush；失败不阻断 |
| 5 | 审批门 ApprovalGate | ✅ | lazy-store [#271](https://github.com/zhuxiangqun/aiPlatform/pull/271) · ISO 时间 [#272](https://github.com/zhuxiangqun/aiPlatform/pull/272) | status/pending/wait → `/platform/approvals…`；裁决在平台 UI |

交付收口（①②③④）合入线索见 DELIVERY §8（citation [#274](https://github.com/zhuxiangqun/aiPlatform/pull/274) · cost [#276](https://github.com/zhuxiangqun/aiPlatform/pull/276) · kb-health [#277](https://github.com/zhuxiangqun/aiPlatform/pull/277)+[#279](https://github.com/zhuxiangqun/aiPlatform/pull/279)+[#280](https://github.com/zhuxiangqun/aiPlatform/pull/280)）。

```bash
export AIPLAT_ENTERPRISE=1
export AIPLAT_PLATFORM_URL=http://127.0.0.1:8003      # or http://127.0.0.1:8000/api (GW)
export AIPLAT_TENANT_TOKEN=<bearer>
# KB only by default; add tools:
export AIPLAT_ENTERPRISE_TOOLS=calculator
# optional: export AIPLAT_CORE_URL=http://127.0.0.1:8002   # auto → …/api/core
# native gate is ON by default (bash/write/edit blocked). Escape:
# export AIPLAT_ENTERPRISE_ALLOW_NATIVE=1
# export AIPLAT_ENTERPRISE_NATIVE_ALLOWLIST=bash
# memory writeback (opt-in):
export AIPLAT_ENTERPRISE_MEMORY=1
# export AIPLAT_ENTERPRISE_MEMORY_AUTO=0   # keep tool, skip session_shutdown flush
# approval wait bridge (opt-in; humans approve in platform UI):
export AIPLAT_ENTERPRISE_APPROVAL=1

pi -e .
# /aiplat-status          → enterprise_hybrid / tools / tool_gate / memory / approval
# /aiplat-enterprise      → KB reconnect status
# /aiplat-kb-health       → KB health score summary (delivery panel)
# /aiplat-memory          → memory writeback status
# /aiplat-approval        → approval wait-bridge status
# tools: aiplat_kb_retrieve | aiplat_tool_execute | aiplat_memory_capture
#        | aiplat_approval_status | aiplat_approval_pending | aiplat_approval_wait
```

Offline + optional live gates:

```bash
bash packages/aiplat-pi-runtime/scripts/run_all_enterprise_smokes.sh
# or individually:
node packages/aiplat-pi-runtime/scripts/enterprise_kb_smoke.mjs
node --experimental-strip-types packages/aiplat-pi-runtime/scripts/enterprise_kb_citation_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_delivery_scan_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_kb_health_smoke.mjs
# cost / kb-health pages (offline):
#   PYTHONPATH=aiPlat-platform:aiPlat-core:. python3 scripts/render_delivery_cost_report.py --fixture --out /tmp/COST_REPORT.md
#   PYTHONPATH=aiPlat-platform:aiPlat-core:. python3 scripts/render_delivery_kb_health.py --fixture --out /tmp/KB_HEALTH.md
# live: GET /platform/delivery/cost-report|kb-health  (Bearer; ?format=markdown)
node packages/aiplat-pi-runtime/scripts/enterprise_tools_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_tool_gate_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_memory_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_approval_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_platform_url_smoke.mjs
node packages/aiplat-pi-runtime/scripts/enterprise_http_smoke.mjs
# live (probes :8003 then :8000/api; SKIP if down; set AIPLAT_HYBRID_LIVE=1 to require):
node packages/aiplat-pi-runtime/scripts/enterprise_hybrid_live_smoke.mjs
```

## 非目标

- 在 Pi 内重实现 PolicyGate / MemoryManager / SECI / ApprovalGate（桥只 **拦截/引导/等待/投递**）
- 从 Pi 代批 `approve`/`reject`（必须走平台审批 UI / 管理端）
- 无允许列表时开放任意平台工具
- 把「厚运行时私有化」写成默认交付（仅驻场例外）

## 与厂内轴（A）的关系

混合回连属于 **厂外企业交付**，优先级高于已关闭的厂内编码旁路。  
厂内方式四已 **⓪ 合并关闭**（2026-10-14）：① `blank_not_proven` → 拆除 `core_facade` Workspace Execute Pi 旁路；离线 CLI/RPC 探针归档于 [`FACTORY_IN_EXPERIMENT.md`](./FACTORY_IN_EXPERIMENT.md)。

## 交付规格附录（SKU / Citation UX / KB Health）

hybrid live 已绿之后的产品收口规格见：

- [`HYBRID_ENTERPRISE_DELIVERY.md`](./HYBRID_ENTERPRISE_DELIVERY.md) — ① 出厂交付清单与归属（A+B）② KB citation 验收（V2/V3a/V6 一期 + P1 低置信/去重/E2E）③ 成本叙事 ④ 托管 SKU；**抄交付节奏，不抄引擎**。
- [`HYBRID_ENTERPRISE_KB_HEALTH.md`](./HYBRID_ENTERPRISE_KB_HEALTH.md) — ④ 库健康分面板：`GET /platform/delivery/kb-health` + 导出 `KB_HEALTH.md` + `/aiplat-kb-health`；一期用 metrics/stats/cache；漏召/低置信 TOP best-effort（syscall_events）。

### 客户可见交付出口（平台已接线）

| SKU / 页 | API | Pi / 导出 |
|----------|-----|-----------|
| 成本页 §4 | `GET /platform/delivery/cost-report` | 导出 `COST_REPORT.md` |
| L2 库健康 | `GET /platform/delivery/kb-health`（另 `miss-top` / `low-confidence-top` / `cache-stats`） | `/aiplat-kb-health` · `KB_HEALTH.md` |
| L1 月报 | `GET /platform/delivery/monthly-ops-report` | 导出 `MONTHLY_OPS_REPORT.md` |
| L3 值班台 | `GET /platform/delivery/l3-duty-desk` | `/aiplat-duty` · `L3_DUTY_DESK.md` |

开通 L3 时至少配置 `AIPLAT_L3_DUTY_CONTACT`（及可选 `CHANNEL`/`HOURS`）；改路由后需重启 platform 进程。
