# Plan: aiPlat × Pi 薄 Runtime（1C + 2C）

> Living 摘要 · 2026-10-12 · 包：`packages/aiplat-pi-runtime/`  
> **状态**：Phase 0–2 + 工厂/FE/ZIP **已合并 main**（PR [#251](https://github.com/zhuxiangqun/aiPlatform/pull/251)）  
> **Live 门**：✅ `bash packages/aiplat-pi-runtime/scripts/live_smoke.sh`（Ollama `ollama/qwen2.5:3b` — CLI print + SOP + `/aiplat-status` + HTTP `createAgentSession`）

## 战略：两条轴，勿合成一条

Pi 是极简 Agent Harness（非治理平台）。与 aiPlat 的关系拆成**两条产品轴**，禁止写成「一个 Pi 集成路径解决所有问题」。

| 轴 | 定位 | 状态 | 解决什么 | 不解决什么 |
|----|------|------|----------|------------|
| **（B）厂外** | 用户侧薄交付宿主：导出包 → `pi -e` / 薄 HTTP | **既定主路径**（已落地） | 不装全栈也能跑快照（SOP + skills + handler） | 平台级厚度（Memory / SECI / PolicyGate / 知识 syscall） |
| **（A）厂内** | 可选编码执行核：CLI/RPC 包在 PolicyGate 外 | **⓪ 合并关闭**（2026-10-14 `blank_not_proven`）：Workspace Execute Pi 旁路已拆；离线 CLI/探针归档；CAPABILITIES **不**标「厂内已接线」 | （历史宣称）编码闭环副作用 | 替代编排治理；默认换掉 ReActLoop |

### 分层，而非两套平行产品（2026-10-13 锁定）

> **能力重叠 ≠ 交付重复。** aiPlat 白皮书里已有 Agent 循环、工具、多模型——那是**平台能力清单**。  
> Pi 默认交付解决的是另一件事：**工厂产出物如何在用户侧轻量跑起来**（不装 core/platform/infra 全栈）。

| 说法 | 是否采纳 |
|------|:--------:|
| 执行面（Pi）与治理面（aiPlat）**分层** | ✅ |
| 用户对外装「两个平权平台」、两套权限/审计 | ❌ |
| 企业场景入口仍是 aiPlat（或 Pi 壳回连 aiPlat）；Pi 对用户透明为「更轻的跑法」 | ✅ |
| 用 Pi 替代 aiPlat 编排/门禁/多租户 | ❌ |

```text
aiPlat（控制面 / 工厂 / 治理）
    │ 导出快照（AGENT.md / skills / handler）
    ▼
Pi（执行面 / 厂外薄宿主）── 默认 Pi-only 可闭环
    │ 可选 AIPLAT_ENTERPRISE=1
    └── 回连 aiPlat API（KB / 工具 / 原生门禁 / Memory / 审批等待；PolicyGate 留在服务端）
```

**产品决策（已锁定 · 2026-10-12；措辞澄清 · 2026-10-13）**

> **默认：只靠 Pi 就能跑产出物。**  
> **企业级：Pi + aiPlat（混合）——Pi 仍是用户侧宿主，厚能力经 aiPlat 托管 API / 门禁回连。**  
> **不以「用户侧单独部署厚 aiPlat 运行时」为默认交付形态。**  
> **不以「Pi 与 aiPlat 两套平行产品」对外叙事。**

| 模式 | 用户侧 | 能力 | 状态 |
|------|--------|------|------|
| **Pi-only** | 导出包 + `pi` / 薄 HTTP + 自备模型 | SOP + skills + handler（确定性桥） | **默认交付 · 已落地** |
| **Pi + aiPlat** | 同上 Pi 壳 + `AIPLAT_ENTERPRISE=1` 回连 | + 只读 KB + 允许列表工具代理 + **原生工具门禁** + **Memory capture** + **审批等待**（`AIPLAT_ENTERPRISE_APPROVAL=1` → status/pending/wait；裁决在平台 UI） | **混合阶梯 1–5 · 已接线** |
| ~~厚运行时~~ | 用户侧直接跑裁剪 aiPlat | 接近平台 Agent | **非默认**；仅特殊驻场/私有化例外 |

**Pi-only 必须能完成的闭环（验收）**

- 加载导出包（manifest / AGENT.md / skills）
- 对话 + SOP 注入
- `/skill-*` 与 `handler.py` 确定性执行
- 自备 LLM（Ollama / 云厂商均可）
- **不依赖** 8002/8003 进程

**Pi + aiPlat 才提供的企业能力（混合回连，不搬进 Pi 进程）**

- PolicyGate / RBAC / 审批
- Memory / SECI / 经验回写
- 平台知识检索（`sys_kb_retrieve` 等）
- 运行时审计 / 可观测回写
- 租户配额与成本治理

混合形态示意（KB + 工具 + 原生门禁 + Memory + 审批等待已落地）：

```text
用户 ──► Pi（对话壳 + 本地 skills/handler）
              │
              ├── 本地可完成 → 不回连（默认 Pi-only）
              └── AIPLAT_ENTERPRISE=1
                    ├── enterprise_tool_gate：block bash/write/edit（默认）
                    ├── POST /platform/kb/query          （只读 KB）
                    ├── AIPLAT_ENTERPRISE_TOOLS=… → POST …/tools/{name}/execute
                    ├── AIPLAT_ENTERPRISE_MEMORY=1 → POST /platform/memory/capture
                    └── AIPLAT_ENTERPRISE_APPROVAL=1 → GET /platform/approvals…
                          （wait/status only；approve/reject 在平台 UI）
```

接线入口：`enterprise_kb.ts` / `enterprise_tools.ts` / `enterprise_tool_gate.ts` / `enterprise_memory.ts` / `enterprise_approval.ts`（由 `aiplat-app.ts` 条件注册）。详见 `packages/aiplat-pi-runtime/docs/HYBRID_ENTERPRISE.md`。

### 双模式内涵（精确化 · 2026-10-13）

> **合理方向 = 控制面 / 执行面分层**，不是「两套平权平台」。企业级 ≠ 单一功能，而是可观测、可治理、可审计的平台工程；Pi 不承担该体系。

| 模式 | 内涵 | 能力边界 | 不安全假设 |
|------|------|----------|------------|
| **模式一 · 仅 Pi** | 独立、可自托管的极简 Agent Harness | `read`/`write`/`edit`/`bash`、会话内循环、多模型抽象；适合个人 / 小团队 / 快速验证 | **无**内置权限、队列、成本、审计 → **禁止**默认无人值守生产 |
| **模式二 · Pi + aiPlat** | Pi = 执行内核；aiPlat = 平台层包裹 | 权限 / 策略 / 审计 / 成本 / 生命周期 / 多租户在 **aiPlat**；副作用经回连或外层 PolicyGate | 禁止叙事成「再装一套平行平台」；禁止把 Memory/SECI/ApprovalGate 搬进 Pi 进程 |

**厂内集成形态（轴 A，与厂外交付正交；已 ⓪ 合并关闭）**：

| 形态 | 原理 | 现状 |
|------|------|------|
| RPC 子进程 | aiPlat 启 Pi 为外部进程，JSONL 通信 | 离线 CLI / `pi_rpc_client` **归档**（不经 Workspace Execute） |
| SDK 嵌入 | 同进程调 Pi API | **非默认**（强 Node 绑定） |
| 可选执行后端 | 曾拟 `AIPLAT_PI_CODING_EXECUTOR` 旁路 | **已拆除**；flag 无生产效果 |

接 Pi **不是为了补上下文**：aiPlat 已有 Memory / CRAG / ContextBus。厂内换心须单独 RFC；当前主路径已是 `coding_closed_loop` + sandbox + `sys_file_*`。

### 上下文 · 压缩 · 学习（作用域 × 治理）

划分标准：**会话内 vs 跨会话**；**是否要权限 / 审计 / 共享 / 持久化 / 回滚**。

| 能力 | 归属 | 说明 |
|------|------|------|
| 会话内窗口管理 / 自动·手动 compaction / 分支摘要 / `transformContext` | **Pi 原生** | 执行自保：不爆窗口；≠ 平台知识沉淀 |
| 项目上下文（AGENTS.md/CLAUDE.md）/ system prompt 组装 | **Pi 原生** | 仓库指令进会话；与 aiPlat ContextBus 来源不同 |
| 上下文选择（Memory / RAG / CRAG / Team Brain） | **aiPlat** | 租户边界 + 策略 |
| 上下文注入包 | **aiPlat 构建，Pi 消费** | 平台决定「给什么」，Pi 决定「怎么进循环」 |
| 跨会话压缩 / 蒸馏 / 持久记忆 | **aiPlat** | 混合桥只投递 `memory/capture`，不搬 MemoryManager |
| 提示 / 知识 / 技能 / 策略层学习 | **aiPlat** | 需持久化、治理、验证、版本与回滚 |
| 会话内即时适应（重试 / ReAct 自纠） | **Pi** | 单次任务内；跨会话学习仍归平台 |
| Pi 扩展生态（magic-context / continual-harness 等） | **可选参考，非默认交付** | 若引入跨会话记忆，治理仍须回 aiPlat；禁止双头管理 |

> **一句话**：会话内上下文与压缩 → Pi；跨会话记忆与学习 → aiPlat；Pi 扩展可补执行侧能力，但共享边界与审计不得旁路平台。

**厂内处置** — 详见 `packages/aiplat-pi-runtime/docs/FACTORY_IN_EXPERIMENT.md`（⓪ 合并关闭）

1. 巩固 Pi-only 交付 + **Pi + aiPlat 混合回连**（企业 DELIVERY SKU）——主产品轴
2. ~~方式四 Workspace Execute Pi 旁路~~ → **已拆除**（`blank_not_proven`）
3. 方式一/二/三：**不实现**，除非 RFC 重做 ① 空白验证 + 真实 caller
4. 离线 `coding_exec` / RPC 探针仅归档复现，**不得**标 CAPABILITIES「厂内已接线」

## 结论（Phase 0）

| 假设 | 文档结论 | 离线检查 | 在线 LLM 冒烟 |
|------|----------|:--------:|:-------------:|
| 包内 `skills/` 自动发现 | **成立**（Pi Skills / Packages 文档） | 结构 ✅ | ✅ live_smoke |
| `before_agent_start` 注入 systemPrompt | **成立**（可返回 `systemPrompt` / `forceSystemPrompt`） | 代码含事件 ✅ | ✅ SOP marker |
| `registerCommand` / `registerTool` | **成立** | 代码含 API ✅ | ✅ `/aiplat-status` |
| `registerSkill` API | **不存在** → **方案 A**（导出复制 skills/） | N/A | N/A |

Skills 策略锁定 **方案 A**：`scripts/export_pi_bundle.py` 把工厂 skills 复制进导出包；扩展只注册斜杠命令与 SOP 注入。

## 职责（厂外薄 Runtime）

| | aiPlat | Pi Runtime（厂外） |
|--|--------|-------------------|
| 工厂 / 合规 / 工作区编辑 | 是 | 否 |
| 用户侧对话执行（薄快照） | 可全栈 | **已交付路径** |
| PolicyGate / Memory / SECI / 审批裁决 | 是 | **不搬**（混合只回连 / 等待） |
| 会话内 compaction / 窗口管理 | 非职责（不侵入循环） | **Pi 原生** |
| 跨会话记忆 / 蒸馏 / 自学治理 | **平台层** | 可选 capture 投递；扩展生态非默认 |
| 扩展 `aiplat-app` | — | 胶水：SOP、斜杠、handler、企业桥；**非** Agent 大脑搬家 |

## 路径

1. `packages/aiplat-pi-runtime` — Pi Package（扩展 + fixture skills）
2. `scripts/export_pi_bundle.py` — 从 `~/.aiplat/apps/{id}/current` 导出
3. Phase 1b handler 协议：JSON stdin/stdout（见 `fixtures/handler_echo.py`）
4. Phase 2：薄 HTTP — `packages/aiplat-pi-runtime/bin/aiplat-http.mjs`
   - `GET /health` · `POST /v1/chat` · `POST /v1/skills/:name`
   - 有 `handler.py` 时走确定性桥（硬失败）；否则注入 SKILL.md 再对话
   - stub：`AIPLAT_HTTP_STUB=1`；真 Agent：`AIPLAT_PI_MODEL=provider/id` + `createAgentSession`
5. 工厂一键导出：`builder/pi_bundle_export.py`；`deploy-to-app` 响应 `pi_bundle`；`POST …/export-pi-bundle`；`GET …/export-pi-bundle.zip`；管理端「导出 / 下载 ZIP」

## 命令

```bash
python3 packages/aiplat-pi-runtime/scripts/phase0_offline_check.py
bash packages/aiplat-pi-runtime/scripts/http_smoke.sh
# Full live gate (Ollama default; needs :11434 + model pulled)
AIPLAT_PI_MODEL=ollama/qwen2.5:3b bash packages/aiplat-pi-runtime/scripts/live_smoke.sh

python3 scripts/export_pi_bundle.py \
  --app-home packages/aiplat-pi-runtime/fixtures/sample-app \
  --out dist/aiplat-app-sample
AIPLAT_APP_HOME=$PWD/dist/aiplat-app-sample \
  pi -e dist/aiplat-app-sample --model ollama/qwen2.5:3b
# /aiplat-status  /skill-greet  /skill-demo_skill  /aiplat-sop-check

# Real HTTP Agent (Ollama / OpenAI-compatible)
# AIPLAT_PI_MODEL=ollama/qwen2.5:3b AIPLAT_APP_HOME=dist/aiplat-app-sample \
#   node packages/aiplat-pi-runtime/bin/aiplat-http.mjs
# Cloud: set AIPLAT_PI_BASE_URL + AIPLAT_PI_API_KEY, or pi /login + provider/id
```

## handler 协议

```json
{"skill":"demo_skill","params":{}}
→ stdout {"ok":true,"result":{...}} exit 0
```

`fixtures/handler_runner.py <handler.py>` 包装现有 `async def execute(params)`。
