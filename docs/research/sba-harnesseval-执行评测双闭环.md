---
title: SBA × HarnessEval：AI 工程化的"执行-评测"双闭环
date: 2026-08-27
status: 定稿
tags: [SBA, HarnessEval, 评测, 证据树, 治理]
---

# SBA × HarnessEval：AI 工程化的"执行-评测"双闭环

## 0. 摘要

SBA（Skill-Based Architecture）与 HarnessEval 构成 AI 工程化中**一枚硬币的两面**：

- **SBA** 解决 Agent 如何"按照规则做事"（执行侧的知识路由与工作流约束）；
- **HarnessEval** 解决人类如何"评判 Agent 做得对不对"（评测侧的动态检查与证据追溯）。

本文档完成三层工作：① 核实 HarnessEval 项目事实并拆解其核心机制；② 建立 SBA × HarnessEval 对偶分析并做批判性审视（防止"自洽的谎言"与被 gaming）；③ 给出 aiPlat 的落地坐标——盘点已有评测侧零件、指出缺口，并记录本次已落地的**证据树（Evidence Tree）schema**。

## 1. HarnessEval 事实核实

- 项目：`MirroS-Lab/HarnessEval-W`（联合清华、英伟达等），论文 arXiv 2608.16859《HarnessEval-W: Agentifying the Evaluation of Visual Worlds》。
- 愿景：既然被测对象（Agent）已成为系统，评测本身也要成为系统——评测器不是"更大的 Judge 模型"，而是一条**可执行的评测工作流**（Plan → Route → Split → Verify），并产出 **Evidence Tree**（层级化可追溯证据链）。
- 首个试验场 HarnessEval-W 聚焦交互式世界模型（目标可见性、状态变化、时序因果、视野外一致性）。

### 1.1 四步评测工作流

| 阶段 | 动作 | 本质 |
|:---|:---|:---|
| Plan | 先理解案例，明确验证目标/状态/风险点 | 不急着给分，先定义"什么算对" |
| Route | 按需选择检查技能，记录为什么启用/跳过 | 动态装配评测器，而非静态加载全部指标 |
| Split | 把抽象判断拆成证据（目标定位/状态变化/因果顺序） | 复杂问题分解，交子 Agent 或专用工具调查 |
| Verify | 审计证据充分性与自洽性后再形成分数 | 结论建立在可验证证据链上 |

### 1.2 Evidence Tree（证据树）

把"检查路径、工具输出、子 Agent 发现、验证结果"串成层级化可追溯结构。分数下降时，可沿树分支定位到具体病因（对象识别 / 状态转移 / 因果链 / 技能覆盖不足）。

## 2. SBA × HarnessEval 对偶分析

| 维度 | SBA（执行侧） | HarnessEval（评测侧） |
|:---|:---|:---|
| 核心对象 | Agent 的行动（Action） | Agent 的产物/轨迹（Trajectory） |
| 路由机制 | 按任务路由到特定 Workflow | 按案例路由到特定检查技能包 |
| 知识组织 | references/ + rules/ + gotchas/ | 技能库（Observation / Causality / State Change / Persistence） |
| 验证契约 | Task Closure Protocol（爆炸半径分桶） | Evidence Tree（证据充分性与自洽性审计） |
| 失败处理 | 立即写回经验（原则 13） | 暴露评测边界（说明缺什么观测/工具/技能） |
| 演进逻辑 | 两次独立完成才固化（原则 14） | 暴露不确定性，不伪装成确定分数 |

两者合体构成 AI Agent 系统的"可观测性底座"：SBA 保证 Agent"不瞎干"（有规可循），HarnessEval 保证人类"不被骗"（分数有源、结论可溯）。

## 3. 批判性审视（三处修正）

### 3.1 "颠覆性"言过其实——这是连续性演进

τ-bench（Sierra）已是"真实 API 环境 + 轨迹级有限错误分类"；Trajectory-As-Judge 已用完整轨迹做判断。HarnessEval 的真增量只有两点：① 评测器本身是 agent（会检索、路由、拆子 Agent）；② 证据树是层级化可追溯结构。Plan/Route/Split/Verify 是把已有实践命名化。

### 3.2 证据树的自洽 ≠ 正确（防"自洽的谎言"）

两个共同错误的证据可以完美自洽（工具 A 的 bias 传给子 Agent B，B 的输出又回喂 A，闭环自证）。证据树必须引入第三条校验：**证据与外部事实（ground truth 或独立第三方工具）交叉验证**，而非只与链条内部节点交叉。

### 3.3 Goodhart 会从"分数"转移到"证据树形状"

一旦排行榜发布证据树，参赛者优化的就不再是能力，而是树的形状。防御手段：证据树与分数**联合发布且联合审计**，保留人工抽检——与架构守卫 §0.4"标注已修复必须附验证命令"同款逻辑。

## 4. aiPlat 落地点位

### 4.1 已有评测侧零件

| HarnessEval 概念 | aiPlat 现有对应物 | 状态 |
|:---|:---|:---|
| 技能库 | `architecture_guard.sh` §77–§96 + Quality Bus 4 子系统 | ✅ |
| 证据规范 | `verify_claude_md_evidence.py`（claim/expect/operator/desc/got）+ conformance 契约 | ✅（扁平） |
| 基线/暴露边界 | ratchet 基线（`undefined_names_baseline.json`、`agent_conformance_baseline.json`）、CLAUDE.md §16 已知债务 | ✅ |
| 路由决策记录 | ❌ 全量扫描，无"为什么启用/跳过"记录 | 缺 |
| 证据树（层级化） | ❌ 扁平"命令→期望→实际值" | 缺 → **本次落地** |
| 评测轨迹确定性 | ❌ LLM 路由无确定性约束 | 缺 |
| 元认知（显式"无法判断"） | 部分（ratchet 容忍为最弱形态） | 缺强形态 |

### 4.2 本次落地：证据树 schema（`verify_claude_md_evidence.py --tree`）

```jsonc
{
  "case_id": "claude-md-evidence@<date>",
  "harness": "verify_claude_md_evidence.py",
  "verdict": { "score": 1.0, "confidence": "high", "summary": "N passed, M failed, K skipped, G known_gaps" },
  "branches": [
    {
      "claim": "CLAUDE.md 文件 <f> 的证据声明全部通过",
      "skill": "claude_md_evidence.file_verify",
      "route_reason": "文件包含（验证：grep …）或 <!-- verify: --> 证据声明",
      "sub_branches": [
        {
          "claim": "<声明描述>",
          "skill": "claude_md_evidence.grep",
          "route_reason": "HTML 注释/内联证据声明（<f>:L<line>）",
          "evidence": [
            { "tool": "shell:grep", "input": "<cmd>", "expect": N,
              "operator": "eq", "actual": N, "raw": "<stdout>",
              "status": "pass|fail|skipped", "detail": "got N (expected M)" }
          ],
          "verdict": "pass|fail|skipped"
        }
      ],
      "verdict": "pass|fail"
    }
  ],
  "known_gaps": [
    { "claim": "<✅ 声明未附验证>", "file": "<f>", "line": N,
      "gap": "✅ 声明未附带可执行验证（缺少 grep/验证命令）" }
  ]
}
```

设计要点（对应 HarnessEval 资产三要素）：
- **route_reason** —— 路由决策可审计（为什么启用这项检查）；
- **sub_branches** —— 失败可定位到具体文件/行/声明；
- **known_gaps** —— 元认知：显式列出"✅ 已修复但无验证命令"的声明（评测器的已知盲区），而不是假装全覆盖。

### 4.3 兼容性与接线

- 默认输出（扁平）与 `--strict` 行为**完全不变**，退出码语义保持（有 FAIL → 1）；
- `run_evidence` 返回值扩展为 `(passed, detail, actual_num, actual_raw)`，供树模式消费；
- 接线：`architecture_guard.sh` 支持 `AIPLAT_EVIDENCE_TREE_OUT` 环境变量落盘证据树（默认关闭，不影响门禁）。

验证命令：

```bash
python3 scripts/verify_claude_md_evidence.py --tree        # 证据树 JSON（stdout）
python3 scripts/verify_claude_md_evidence.py --tree --out <f>  # 落盘
python3 scripts/verify_claude_md_evidence.py --strict      # 回归：默认行为不变
```

## 5. 下一步（未落地）

1. **路由决策记录**：架构守卫 §77–§96 每次执行记录"启用/跳过了哪些检查项及原因"，写入审计日志；
2. **评测轨迹确定性**：LLM 参与的路由增加种子与确定性约束，保证证据树可复现；
3. **外部事实交叉**：对高风险证据引入独立第三方验证（防"自洽的谎言"）；
4. **诊断面板消费**：证据树接入 FDE 诊断面板，按树分支展示失败定位。

## 5.5 回写自动度与实施边界（2026-08-27 讨论收敛）

### 5.5.1 自动度光谱

评测→回写闭环的自动化程度决定信任模型，分四档：

| 自动度 | 环节 | 风险 | 控制点 |
|:---|:---|:---|:---|
| L0 全人工 | 评测→人看报告→人改知识库 | 无自动化风险，慢 | — |
| L1 半自动 | 评测发现缺陷 → 人确认 → 写回 | 低 | 人工确认门槛 |
| L2 自动+门槛 | 评测自动登记 `gotchas/`（待验证）→ 两次独立成功 → 升级 `rules/` | 中 | **原则 14 门槛** |
| L3 全自动 | 评测失败 → 直接更新 references → 下次直接生效 | 高 | 无 |

**结论：落地停在 L2，不启用 L3。** 依据：
- 评测器也有误报（Grounding 检查器有偏、Trajectory 判定误报），自动改写知识库会把评测 bias 固化成 Agent 行为规则且不可逆；
- RAG 知识库是生产资产，被污染的代价 > 自动化速度收益。

### 5.5.2 回写采用 ratchet 模式，而非"更新模式"

与 aiPlat 已验证的 ratchet 哲学（§96 agent 符合度、F821 基线）一致：

- **记录失败是安全的**（`gotchas/` = 失败日志，永远可逆）；
- **改写知识是不安全的**（`rules/`/`references/` = 变更，需要门槛）；
- 升级路径 = 原则 14（两次独立验证成功才固化），且升级前保留待验证标记。

### 5.5.3 两个兜底门槛

1. **误报率兜底**：评测器 confidence < 0.7 的失败只提示、不登记（防评测误报污染 gotchas 本身）；
2. **风险分桶**：低风险知识（内部 FAQ 类）可放宽到 L2 快速路径，高风险知识（法务/生产变更）必须 L1 人工确认——与 SBA 爆炸半径分桶同构。

### 5.5.4 引用核实结论

- `harness-evals`（[harness/harness-evals](https://github.com/harness/harness-evals)）：真实存在，但为 Harness 公司独立产品，与 HarnessEval **同名撞车，非同一项目**；
- `rag-eval-harness`（[muhammadwaqasmbd/rag-eval-harness](https://github.com/muhammadwaqasmbd/rag-eval-harness) 等）：个人/小型项目，**不属于 HarnessEval 生态**；
- ITBench-AA / otel-demo / readiness_probe：真实（IBM K8s 沙箱基准）；
- "45 分钟→10 分钟" AWS DevOps Agent 案例：无直接来源，**待核实**，不得写入正式结论。

### 5.5.5 落地状态（2026-08-27 已实施）

| 项 | 实现 | 状态 |
|:---|:---|:---|
| 证据树 schema | `verify_claude_md_evidence.py --tree`（branches/sub_branches/evidence/route_reason/known_gaps） | ✅ 已合入（PR #164） |
| L2 回写链路本体 | `aiPlat-platform/governance/experience_feedback/`（register_failure / record_verification / confirm_promotion 状态机） | ✅ 已合入 |
| 守卫失败自动登记 | `architecture_guard.sh` FAIL 分支自动 `--register architecture-guard-fail`（gotchas 登记；验证/升级由后续运行或人工触发） | ✅ 已合入 |
| 守卫路由决策记录 | `architecture_guard.sh` `AIPLAT_GUARD_TRACE_OUT` 落盘 routing_trace（run_id/mode/route_trace[check, enabled, reason_selected, reason_skipped, result]/failed_guards/verdict）——为什么启用/跳过某项检查可审计 | ✅ 已合入 |
| 外部事实交叉 | `verify_claude_md_evidence.py` evidence 节点 `cross_checks`（grep 检索路径存在性验证，防"自洽的谎言"）；默认模式打印 `⚠ CROSS-CHECK` WARN 不阻断。上线即捕获 **A2 假阳性**（`builder.py` 路径已迁移，原验证命令基于缺失文件自证通过）并修复 A2 验证命令 | ✅ 已合入 |
| 兜底门槛① | `MIN_CONFIDENCE=0.7` 以下拒收（只提示不登记） | ✅ 实现内建 |
| 兜底门槛② | `risk=high` 升级需 `confirm_promotion` 人工确认（`promoted:review` 态） | ✅ 实现内建 |
| 原则 14 门槛 | 连续 2 次独立验证成功才升级；同 case 重复不计数；连续 2 次失败判 rejected | ✅ 实现内建 |

状态机（10 项 pytest 全过 + CLI 冒烟）：

```text
register_failure(confidence≥0.7) → pending
  ├─ record_verification(success) ×2（独立 case）→ promoted（low 自动 / high 需人工确认）
  └─ record_verification(fail) ×2 → rejected（经验无效）
```

存储：JSON（`AIPLAT_EXPERIENCE_FILE` 配置，默认 `$AIPLAT_HOME/experience_feedback.json`）。
验证命令：

```bash
pytest aiPlat-platform/tests/test_experience_feedback.py -q          # 10 passed
python3 aiPlat-platform/governance/experience_feedback/experience_feedback.py --status
```

## 6. 结论

从"尺子"到"探针"：AI 工程化正在把提示词工程升级为工作流工程、把模型评测升级为系统审计。若 SBA 的军规是写给 Agent 的《罗伯特议事规则》，HarnessEval 就是写给人类的《证据法与审计准则》——让 AI 系统在复杂真实环境中**既能可靠行动，又能被清晰问责**。
