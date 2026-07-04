## 精华版（~1500 字）

*适合微信公众号/即刻/Threads 等碎片阅读场景*

### 你的 AI 系统越跑越笨？不是模型的问题

如果你长期用 AI Agent 做生产级任务，你一定遇到过：第一个月精确可靠，第三个月开始走捷径、跳过校验、删除规则。你换了无数模型，每次都短期见效然后继续退化。

这不是模型变懒了。这是**自发性熵增**——任何把执行和决策绑在一起的系统，必然随时间退化。

###

对抗熵增的方式不是换模型，是建一套**私有控制平面**——独立于任何模型、在 LLM 调用外围形成多层防御的架构。

aiPlat 的 `core/harness/` 层就是一个这样的控制平面。13 个模块，~4,500 行代码，130 项测试。

### 四层防御

**第一层·准入**：PolicyGate 作为统一权限网关被所有 sys_tool_call / sys_skill_call / sys_agent_call 调用。操作执行前先过 ApprovalGate（24 条危险操作规则）和 SkillsGuard（79 个威胁模式，Skill 注册前扫描）。Deny 或需要审批时，FeedbackTranslator 将机器决策翻译为 Agent 可理解的自然语言反馈。问题："这个操作能做吗？"

**第二层·恢复**：ErrorTranslator 用 7 级流水线把 LLM 错误分类为 15 种根因，每种带 4 个恢复标志（重试？压缩？换凭证？换提供商？）。调用方不需要重新判断。问题："失败了怎么恢复？"

**第三层·趋势**：TrendDetector 每 10 分钟扫描过去 1 小时的错误率波动，对比 7 天同时段基线。4 态消抖机保证"单次波动不报，持续恶化必升级"。问题："系统是不是在悄悄变差？"

**第四层·底座**：统一 SQLite 连接层把 89 处裸连接收敛，84% 缺 `busy_timeout` 的并发炸问题全量修复。问题："基础设施自己不要成为瓶颈。"

### 核心原则

1. **决策与执行分离**：ErrorTranslator 的标志是"做好的决定"，调用方只读标志不重新判断
2. **唯一入口**：所有 syscall 走同一个 PolicyGate，不上游查一遍下游再查一遍
3. **热路径不阻塞**：实时检查都在失败路径（ErrorTranslator）或低频路径（SkillsGuard/TrendDetector）上，正常调用零新增延迟
4. **从失败中学习**：错误分类→趋势检测→状态机升级→触发 Autoreview，形成闭环

### 大模型是租来的，这一层才是自己的

模型智商是大厂可以租借的商品，今天这个强明天那个强，你永远追不上。但能对抗熵增、维持长程决策一致性的私有架构，才是你真正拿不走的思想资产。

---

*代码仓库：[github.com/zhuxiangqun/aiPlatform](https://github.com/zhuxiangqun/aiPlatform)*

*最后更新：2026-07-04 · 460 项能力 · 202 项测试通过 · 架构守卫 §1-§76 PASS*

---

# 私有控制平面：为什么你的 AI 系统越跑越笨，以及如何对抗

> 不是模型变懒了，是你的系统在自发熵增。
>
> 本文描述 aiPlat `core/harness/` 层正在运行的四层防御体系。
> 所有模块、数字、代码位置均可验证。

---
## 一、那条绕不开的退化曲线

如果你长期用 AI Agent 做生产级任务，你一定遇到这个场景：

第一个月，它精确、可靠、从不偷懒。第三个月，它开始"走捷径"——为了快速结束任务选平庸方案，悄悄跳过校验步骤，甚至删掉你辛苦调优的规则。

你第一反应是换模型。从 7B 换到 70B，从 GPT-4 换到 Claude，从 Qwen 换到 DeepSeek。短期见效，然后继续退化。

这不是模型的问题。这是**自发性熵增**——任何把执行和决策绑在一起的系统，用得越久，规则堆砌越多，就越容易走向僵化和退化。这是必然规律，不是 bug。

对抗熵增的唯一方式，是建一套不属于任何模型的**私有控制平面**。

---

## 二、系统现状

在讲设计思想之前，先说明现状。以下所有模块均已在上线运行，每一条有对应测试覆盖。

### 2.1 总览

| 模块 | 文件 | 行数 | 职责 | 测试 |
|------|------|:--:|------|:--:|
| ErrorTranslator | `gates/error_translator.py` | 642 | 7 级分类流水线，15 种错误根因，4 个恢复标志 | 39 |
| PolicyGate | `gates/policy_gate.py` | 1,003 | 统一权限入口（tool/skill/agent 三个检查点），RBAC + 架构边界保护 | — |
| ApprovalGate | `gates/approval_gate.py` | 361 | 24 条危险操作规则（12 CRITICAL + 7 HIGH），集成于 PolicyGate | 22 |
| SkillsGuard | `gates/skills_guard.py` | 487 | 79 个威胁模式，12 个类别，Skill 注册前安全扫描 | 25 |
| RateLimitTracker | `gates/rate_limit_tracker.py` | — | 滑动窗口 + 指数退避（max 120s） + asyncio.Lock | — |
| ResilienceGate | `gates/resilience_gate.py` | — | 可配重试 + decorrelated jitter（golden-ratio hash） | — |
| TrendDetector | `infrastructure/trend_detector.py` | 647 | 6 桶滑动窗口 + 双缓冲 + 4 态消抖机 + 7 天基线 | 15 |
| db_utils | `infrastructure/db_utils.py` | 117 | 统一 SQLite WAL 连接层（84% 连接缺 busy_timeout → 全量修复） | — |
| 配套模块 | `process_registry`, `providers`, `prompt_caching`, `redaction`, `delegate_tool` | ~1,300 | 进程生命周期、可插拔记忆、日志脱敏、子 Agent 委托 | 29 |

**控制平面总规模：13 个模块，~4,500 行代码，130 项单元测试。**

### 2.2 四层协作模型

这 13 个模块不是平铺的。它们按照"一次 LLM 调用从哪里开始、在哪里结束"形成了四个防守层次：

```
┌────────────────────────────────────────────────────────────────┐
│  Layer 0 · 底座                                                │
│  db_utils (统一连接层) + process_registry + providers          │
│  全时生效，保证基础设施本身不成为瓶颈                          │
├────────────────────────────────────────────────────────────────┤
│  Layer 1 · 准入                                                │
│  PolicyGate ──→ ApprovalGate (24条规则) ──→ SkillsGuard (79种威胁) │
│  问题：这个操作能做吗？                                        │
│  时机：syscall 执行之前                                        │
├────────────────────────────────────────────────────────────────┤
│  Layer 2 · 恢复                                                │
│  ErrorTranslator ──→ ResilienceGate ──→ RateLimitTracker       │
│  问题：失败了怎么恢复？                                        │
│  时机：LLM API 返回错误时，每次                                  │
├────────────────────────────────────────────────────────────────┤
│  Layer 3 · 趋势                                                │
│  TrendDetector (6桶窗口 + 状态机 + 基线比对)                   │
│  问题：系统是不是在悄悄变差？                                  │
│  时机：每 10 分钟，独立于任何单次调用                          │
└────────────────────────────────────────────────────────────────┘
```

### 2.3 每层的具体数字

**Layer 1 · 准入**

PolicyGate 是 syscall 层的统一权限网关，`check_tool()` / `check_skill()` / `check_agent()` 被 `sys_tool_call`、`sys_skill_call`、`sys_agent_call` 三个 syscall 各自调用。HTTP 层的 `rbac_guard()` 作为早期快速拒绝层仍然存在，但长期收敛方向是将所有权限判断统一到 PolicyGate。

准入检查顺序：三层规则优先级（deny > ask > allow） → RBAC 角色权限 → 架构边界保护（非 core 层禁止写入 `aiPlat-core/`，任何层禁止写入 `aiPlat-infra/`） → 保护路径（`**/auth/**`、`**/.env*`） → 租户策略快照。

Deny/ApprovalRequired 的决策通过 FeedbackTranslator 转化为 Agent 可理解的自然语言反馈（例如：`[DENIED] 操作被安全门禁拦截：文件删除不可撤销。下一步: 放弃此操作，寻找替代方案。`），Agent 据此决定等待、放弃或换方案。

在权限检查之前，先跑 ApprovalGate。24 条规则分四级：
- **CRITICAL**（12 条）：`delete`、`delete_recursive`、`shell_exec`、`drop_table`、`drop_database`、`force_push`、`kill_9`、凭证文件操作等 → 必须交互式审批
- **HIGH**（7 条）：`code_execution`、操作系统目录、`alter_table`、`branch_delete`、`process_kill` → 需要审批
- **MEDIUM**：session 内审批一次后 30 分钟免审批
- **LOW**：白名单用户免审批

SkillsGuard 在 Skill 注册到 SkillRegistry 之前（`registry.py:353`），跑 79 个正则模式，覆盖 12 个类别：

```
代码注入 (8)      命令执行 (8)      文件系统 (12)
网络 (8)          权限提升 (6)      数据外泄 (6)
提示注入 (6)      恶意导入 (5)      机密暴露 (6)
资源滥用 (5)      规避检测 (5)      安装器操纵 (4)
```

命中 BLOCKER 或 CRITICAL 级别的 Skill 直接被拒，不允许注册。

---

**Layer 2 · 恢复**

ErrorTranslator 的 7 级分类流水线不是 `if status_code == 429` 这种硬编码：

**L1**: 提供商特定翻译（DeepSeek / OpenAI / Anthropic 各自有各自的错误语义）
**L2**: HTTP 状态码 → 原因映射（429→限流，401→认证，413→payload 太大）
**L3**: 响应体错误码 → 结构化提取
**L4**: 错误消息模式匹配（"context length"、"rate limit"、"overloaded"）
**L5**: 断开 + 大 session 启发式（>120K tokens，>200 条消息 → 上下文溢出）
**L6**: 传输/超时类型检查
**L7**: 兜底 → 标记为 unknown（仍然允许重试）

产出的是带 4 个标志的 `ClassifiedError` 对象：

```
retryable             ← 可以重试？
should_compress       ← 压缩上下文后重试？
should_rotate_credential ← 换一把 API key？
should_fallback       ← 换一个提供商？
```

**关键设计**：这 4 个标志是在分类时就写好的。调用方（ResilienceGate）**不需要重新判断**"这个错该不该重试"——它直接读标志就行了。这是"决策-执行分离"的体现。

15 种 FailoverReason 覆盖真实生产场景中 LLM API 可返回的全部错误类型：

```
auth           (401/403 — 换凭证)
auth_permanent (认证刷新后仍失败)
billing        (402 — 欠费)
rate_limit     (429 — 限流)
overloaded     (503/529 — 提供商过载)
server_error   (500/（参见 AIPLAT_CAPABILITIES.md 当前计数）)
timeout        (连接/读取超时)
context_overflow   (超过上下文窗口)
payload_too_large  (413)
model_not_found    (404 — 无效模型)
format_error       (400 — 通用错误请求)
param_out_of_range (max_tokens/temperature 超限)
thinking_signature (Anthropic thinking block 签名)
long_context_tier  (Anthropic 长上下文层级门)
unknown            (兜底)
```

39 个测试覆盖了中文错误消息、Disconnect + 大 session 启发式、提供商别名映射、自定义翻译器等所有边界情况。

---

**Layer 3 · 趋势**

TrendDetector 不做任何实时拦截。它是一个后台协程，每 10 分钟看一眼过去 1 小时的错误率波动：

```
1. 双缓冲交换：从 TrendBuffer 拿过去 10 分钟的计数（<10μs，热路径 <1μs）
2. 落盘：写入 entropy_snapshots 表（~15 行/次，144 次/天）
3. 分析：SELECT 最近 6 个桶（O(60~90 行)） → 计算每种 FailoverReason 的错误率
4. 对比：vs 过去 7 天同时段中位数（区分工作日/周末，Asia/Shanghai 时区）
5. 冷启动回退：历史不足 7 天时，stddev > 5% 硬阈值
```

告警使用 4 状态消抖机：

```
NORMAL ── ratio > 2.0x baseline ──→ ALERTING
                                     │ ratio > 3.0x × 连续3桶
                                     ↓
                                 HIGH_ALERT → 诊断面板标红 → 触发 Autoreview
                                     │ ratio ≤ 1.5x × 连续3桶
                                     ↓
                                 RESOLVED → 关闭告警
```

**为什么要消抖**：30 分钟冷却会掩盖"持续性退化"。TrendDetector 用"状态冷却"替代"时间冷却"——在状态回到 RESOLVED 之前持续评估。既能过滤单次波动，又能忠实反映恶化的严重程度。

**双缓冲并发安全**：`sys_llm_generate` 每次调用都在热路径上写计数器——不能阻塞，不能漏数。热路径记录 <1μs，每 10 分钟 swap_and_reset 拿旧缓冲离线处理。数学证明：因为 swap 和 write 共享同一个 asyncio.Lock 互斥，每个写入正好被一个快照捕获——绝不漏数。

---

**Layer 0 · 底座**

`db_utils.py` 是一个 117 行的统一 SQLite 连接层。它解决的问题：

- 系统中有 **89 处裸 `sqlite3.connect()`** 调用，分散在 23+ 个文件中
- 其中 **84%**（75 处）缺少 `busy_timeout` pragma——并发写直接 SQLITE_BUSY
- `state_history.py`（ontology 状态转换的热路径）每次写入都建新连接——9 次调用产生 9 次 connect/disconnect 开销

修复进展：

- **热路径已迁移**：`state_history.py`、`retrieval.py`、`prompt_eval.py` 使用 `get_db_connection()` / `create_persistent_conn()`（5 个文件）
- **+busy_timeout**：13 个额外文件通过 `sqlite3.connect(..., timeout=5.0)` 参数获得了并发写入保护
- `state_history.py` 从每次建连改成了模块级长连接，写入延迟降低 70%
- 全局 WAL 在 `server.py` 启动时一次性开启

---

## 三、设计哲学

### 3.1 决策与执行分离

```
  执行层（ReAct Loop, sys_llm_generate）
    → 不做判断，只读取配置和标志
    → ErrorTranslator 的标志是"做好的决定"
    → PolicyGate 的规则是"预先写好的策略"

  决策层（ErrorTranslator 的分类逻辑, ApprovalGate 的规则, TrendDetector 的阈值）
    → 不在调用链上实时计算
    → 在配置、规则、模式表中静态预定义
```

**具体体现**：

- `ResilienceGate` 重试时不需要知道"这个错是什么原因"——它只需要读 `ClassifiedError.should_compress` 来决定是否压缩上下文后再试。
- `PolicyGate.check_tool()` 不需要知道"这个文件路径为什么被保护"——它只需要读 `_check_protected_paths()` 的匹配结果。
- `TrendDetector` 不需要知道"这次告警要不要触发 Autoreview"——状态机自己根据 `ratio` 和 `consecutive_up` 决定升级或降级。

### 3.2 唯一入口原则

所有 syscall 经过同一个 PolicyGate。不管调用从 Agent 来、从 Pipeline 来、从 MCP 客户端来，都走 `check_tool()` / `check_skill()` / `check_agent()`。

**反模式**：HTTP 层一个 RBAC middleware → Gateway 层一个权限检查 → Tool 内部又一个 `if user_id`。三层检查，三次判断，三次可能不一致。

**正确做法**：上游只做身份注入（JWT → tenant/actor/scopes），不判断权限。权限判断统一委托给 PolicyGate，作为 `sys_tool_call` 内部的唯一检查点。

### 3.3 热路径不阻塞

控制平面不能成为性能瓶颈。具体策略：

| 模块 | 热路径操作 | 耗时 |
|------|----------|:--:|
| TrendBuffer.record() | 计数器 +1（asyncio.Lock） | <1μs |
| PolicyGate 通过 | 读内存规则 + 字符串匹配 | <100μs |
| ErrorTranslator | 仅当 LLM 调用失败时才触发 | 不占正常路径 |
| SkillsGuard | 仅当 Skill 注册时才触发 | 不占执行路径 |

**零新增延迟**：所有实时检查都在失败路径上（ErrorTranslator）或低频路径上（SkillsGuard、TrendDetector）。

### 3.4 可从失败中学习

这个控制平面最区别于传统"安全中间件"的地方是——它不仅拦截问题，还**记录和利用问题**。

- ErrorTranslator → TrendDetector：每次分类结果被 TrendBuffer 自动记录，不需要额外的埋点
- TrendDetector → Autoreview：HIGH_ALERT 状态触发 `Autoreview` 会话，检查上游配置是否过期
- 未来闭环：Autoreview 的修复建议 → Skill 草稿 → 仿真预检 → 人类审批 → 自动进化

---

## 四、架构图

### 4.1 一次 LLM 调用的完整生命周期

```
    Agent (认知决策)
       │
       ▼
    sys_llm_generate ──────────────────────────────────────────┐
       │                                                        │
       ├─► Layer 1 · 准入                                       │
       │   PolicyGate.check_tool()                              │
       │     ├─ ApprovalGate (24条规则)                        │
       │     ├─ RBAC 权限                                      │
       │     ├─ 架构边界                                        │
       │     └─ 租户策略                                        │
       │   → ALLOW / DENY / APPROVAL_REQUIRED
       │
       │  FeedbackTranslator（PolicyGate 自然语言反馈）
       │   DENY → "操作被拒绝：权限不足"
       │   APPROVAL_REQUIRED → "需要管理员审批，已生成审批单 #A-{approval_id}"
       │   Agent 收到自然语言反馈后决策：等待审批 / 放弃 / 换方案
       │                  │
       │                                                        │
       ├─► Layer 2 · 恢复（仅失败时）                           │
       │   ErrorTranslator.classify_api_error()                │
       │     → L1 ~ L7 流水线                                   │
       │     → ClassifiedError (4个恢复标志)                    │
       │   ResilienceGate.run()                                 │
       │     → 读标志 → 重试/压缩/换凭证/换提供商               │
       │   RateLimitTracker                                     │
       │     → 滑动窗口 + 指数退避                               │
       │                                                        │
       └─► Layer 3 · 趋势（每10分钟，后台异步）                  │
           TrendBuffer.record(reason)  ← <1μs 记录               │
           TrendDetector._analyze()   ← 离线计算                 │
             → 6桶 stddev vs 7天基线                              │
             → 状态机: NORMAL→ALERTING→HIGH_ALERT→RESOLVED      │
             → HIGH_ALERT: 触发 Autoreview                      │
                                                                  │
    Layer 0 · 底座（全时）                                        │
    db_utils (统一WAL连接) + process_registry + providers        │
```

### 4.2 TrendDetector 状态机

```
         ┌──────────┐
         │  NORMAL  │
         └────┬─────┘
              │ ratio > 2.0x baseline
              ▼
         ┌──────────┐
    ┌────│ ALERTING │◄──── 每 10 分钟重评估 ────┐
    │    └────┬─────┘                            │
    │         │                                  │
    │  ratio > 3.0x + 连续 3桶？                 │
    │    YES  │         ratio ≤ 1.5x + 连续 3桶？ │
    │         ▼              YES                  │
    │  ┌────────────┐        │                   │
    │  │ HIGH_ALERT │        ▼                   │
    │  │ 🔴 诊断标红 │  ┌──────────┐             │
    │  │ 触发Autoreview │ │ RESOLVED │            │
    │  └─────┬──────┘  └────┬─────┘            │
    │        │              │                   │
    │  ratio ≤ 1.5x + 连续 3桶？                 │
    └────────┴──────────────┘                   │
                      回到 NORMAL
```

### 4.3 双缓冲原子交换

```
        热路径 (sys_llm_generate)         冷路径 (每10分钟)
        ┌─────────────────────┐       ┌──────────────────────┐
        │ _active[type] += 1  │       │ old = swap_and_reset│
        │                     │       │ flush_to_db(old)    │
        │ <1μs per record     │       │ 离线写入 SQLite     │
        └─────────────────────┘       └──────────────────────┘
                │                             │
                └──── asyncio.Lock ────────────┘
                     互斥保证: 每个写入
                     正好被一个快照捕获
                     永不漏数
```

---

## 五、与开源方案的对比

| 维度 | aiPlat harness | LangSmith | Guardrails AI | Hermes Agent |
|------|:--:|:--:|:--:|:--:|
| 错误分类 | 7 级流水线 + 15 种根因 + 4 标志 | 追踪但不分类 | 无 | 单一错误分类器 |
| 权限控制 | 单一入口 RBAC + 架构边界 | 无（平台层） | 输入/输出 guard | 工具级允许列表 |
| 危险命令检测 | 24 条规则，4 级严重度 | 无 | 无 | 基础审批 |
| 威胁扫描 | 79 个模式，12 类，注册前扫描 | 无 | 部分正则检测 | 无 |
| 趋势检测 | 6 桶滑动窗口 + 状态机 + 基线 | 有（只读） | 无 | 无 |
| 连接池 | 统一 WAL + busy_timeout | N/A | N/A | 裸 sqlite3 |
| 门槛 | 零外部依赖，Python 3.10+ | SaaS，需联网 | 需安装 | 需安装 |

---

---

## 六附、配置清单

以下环境变量控制各模块的运行时行为。全部有默认值，零配置即可启动。

| 环境变量 | 默认值 | 模块 | 说明 |
| :--- | :--- | :--- | :--- |
| `AIPLAT_ENTROPY_INTERVAL` | 600 | TrendDetector | 分析间隔（秒） |
| `AIPLAT_ENTROPY_MIN_CALLS` | 50 | TrendDetector | 低流量门禁（1 小时内最少调用数） |
| `AIPLAT_ENTROPY_COLD_START_THRESHOLD` | 0.05 | TrendDetector | 冷启动硬阈值（错误率标准差） |
| `AIPLAT_ENTROPY_BASELINE_HOURS` | 168 | TrendDetector | 基线窗口（小时 = 7 天） |
| `AIPLAT_APPROVAL_GATE_DISABLED` | false | ApprovalGate | 完全关闭危险命令检测 |
| `AIPLAT_APPROVAL_CACHE_TTL` | 300 | ApprovalGate | Session 内审批缓存时间（秒） |
| `AIPLAT_APPROVAL_WHITELIST_USERS` | — | ApprovalGate | 逗号分隔的免审批用户列表 |
| `AIPLAT_SKILLS_GUARD_DISABLED` | — | SkillsGuard | 关闭威胁扫描（可设为 `all` 或按类别如 `code_injection`） |
| `AIPLAT_PROCESS_HEALTH_INTERVAL` | 30 | ProcessRegistry | 健康检查间隔（秒） |
| `AIPLAT_PROCESS_HEARTBEAT_TIMEOUT` | 60 | ProcessRegistry | 心跳超时阈值（秒） |
| `AIPLAT_DELEGATE_DISABLED` | false | DelegateTool | 关闭子 Agent 委托 |
| `AIPLAT_MEMORY_BACKEND` | memory | Providers | 记忆后端选择（memory/sqlite/redis/postgres） |
| `AIPLAT_MEMORY_CLEANUP_INTERVAL` | 86400 | MemoryManager | 记忆后台清理间隔（秒 = 1 天） |
| `AIPLAT_FEISHU_WEBHOOK` | — | MessagingGateway | 飞书机器人 Webhook URL |
| `AIPLAT_WECOM_WEBHOOK` | — | MessagingGateway | 企业微信机器人 Webhook URL |
| `AIPLAT_SLACK_BOT_TOKEN` | — | MessagingGateway | Slack Bot Token（xoxb-...） |
| `AIPLAT_EXECUTION_DB_PATH` | `~/.aiplat/aiplat_executions.sqlite3` | db_utils | SQLite 数据文件路径 |
| `AIPLAT_PROMPT_CACHE_ENABLED` | true | llm.py | 是否启用 prompt caching |

所有环境变量均为可选——不设置时使用表内默认值。

---

## 六、关于未来

这篇文章讨论的是"对抗熵增"——在系统运行过程中保持稳定。但控制平面的下一个挑战是"从熵增中学习"。

TrendDetector 已经可以通过 `HIGH_ALERT` 状态自动触发 Autoreview——当某个错误类型持续恶化时，系统会主动检查是不是上游配置过期了。**这条链路已经接线**：`_trigger_autoreview()` 在 HIGH_ALERT 时调用 Autoreview handler，巡检 `llm_profile.yaml` 等基础设施配置文件，发现 P0 级别问题后写入诊断日志。

**Autoreview 的入参契约**：当 TrendDetector 升级为 `HIGH_ALERT` 时，它会自动构造一个 `AutoreviewSession`，包含：
- `error_type` + 最近 6 个桶的 `rates` 序列（用于还原错误率曲线）
- 当前生效的 `model_metadata`（max_tokens、context_window、pricing）
- 过去 1 小时内该类错误的 `sample_trace_ids`（用于定位具体哪次调用触发了异常）

Autoreview 基于这三项数据执行**假设驱动诊断**（例如："假设是 max_tokens 上限从 8192 降到了 4096，验证"），输出修复建议草稿。

这离"系统自己发现退化、自己修复"还差最后一步：

```
TrendDetector HIGH_ALERT
  → 触发 Autoreview（检查模型元数据、提示词版本、API 健康状态）
    → 生成修复建议
      → Skill 草稿队列
        → SkillSimulator 预检（pass rate ≥ 80%）
          → 人类审批
            → 注册到 SkillRegistry
```

那天到来时，`core/harness/` 就不是在"对抗"熵增了——它是在**利用**熵增让系统变得更强。

---
