# SBA（skill-based-architecture）借鉴分析报告

> 分析对象：https://github.com/WoJiSama/skill-based-architecture（MIT，2026-04 创建，527★/45 fork）
> 分析方式：源码级审计（workflow 5 模块并行 + 真实缺陷人工复核）+ 18 条原则逐条映射 + aiPlat 应用工厂落地闭环
> 落地状态：10 个 PR 全部合并（#149-#158），系统契约 §5.2 契约 #14-#21
> 最后验证：2026-08-27

## 1. SBA 是什么

**元技能（Meta-Skill）框架**——一个用于生成/管理技能（Skill）的技能。将散落在各 AI Agent 入口文件（AGENTS.md/CLAUDE.md/.cursor/rules 等）的项目规则、工作流、经验教训，蒸馏为结构化的 `skills/<name>/` 目录，成为所有编码助手（Cursor/Claude Code/Codex/Windsurf/Gemini）任务前的**单一事实来源**。

自我限定：**是一个 Skill，不是 Agent 操作系统、任务数据库或执行运行时**。

## 2. 核心机制（代码审计确认）

| 机制 | 实现 | 代码证据 |
|------|------|---------|
| 证据驱动物化 | 盘点目标仓库证据 → 自动推导 direct/folder/broad 形态，用户不选层级 | scripts/scaffold-downstream.sh（SBA 上游）（63KB/1618 行，dry-run + mktemp 回滚） |
| 渐进严格度 | 只在压力下生长；骨架/肉拆分（architecture/references/conventions/gotchas） | references/progressive-rigor.md（SBA 上游） |
| 路由-知识分离 | routing.yaml 只选首 workflow，知识按需拉取；"读了不改变动作"= 失效模式 | templates/skill/routing.yaml（SBA 上游） |
| 自举生成防漂移 | 5 harness 薄壳由 YAML 生成 + check-self-shells 校验字节一致 | scripts/sync-self-shells.sh（SBA 上游） + check-self-shells.sh（SBA 上游） |
| 机器契约校验 | conformance.yaml（948 行）must_contain/in_order 短语断言 | templates/skill/conformance.yaml（SBA 上游） + check-version-conformance.sh（SBA 上游）（441 行手写 YAML 解析器） |
| 任务完成判断 | Requirement → Task Anchor → Native Plan → Task Closure（爆炸半径 A/B/C 桶） | templates/skill/workflows/task-closure.md（SBA 上游） |

## 3. 代码审计发现的真实缺陷（文档未承诺的盲区）

| 严重度 | 缺陷 | 证据 |
|:---:|------|------|
| 🔴 | 自举豁免：上游强制下游 SKILL.md ≤90 行，自身 body 120+ 行，CI `--phase 7` 绕过 | check-all.sh + 实测 |
| 🔴 | 悬挂 hook：`.claude/settings.json:21` 指向已删除的 agent-behavior-gate.sh（每次 Write/Edit 触发失败） | settings.json vs 删除记录 |
| 🟠 | 行数预算表全面漂移（smoke-test 1356>980 等 8+ 文件超限），"预算触发评审"无机器强制 | wc -l vs README |
| 🟠 | 清单类文档漏登（REFERENCE by-topic 漏 3 文件、vendor 漏 2 protocol-block） | 交叉比对 |
| 🟠 | 死代码：scaffold-downstream.sh:913 perl 模式与生成文本不匹配 | 源码比对 |
| 🟡 | 计划文档内嵌 /Users/shiqi/ 绝对路径、无 CI、手写 YAML 解析器脆弱 | docs/plans/* |

**教训**：防漂移体系需按"维护面"而非"文件类型"设计覆盖；避免"规约管下游、不管自己"。

## 4. 18 条原则 → aiPlat 应用工厂逐条映射

### ✅ 已机器化落地

| 原则 | aiPlat 落地 | PR |
|------|-----------|-----|
| 3 规则必须被正确激活 | 生成 skill triggers 进路由表 + description 一致 | #153/#152 |
| 5 验证与风险匹配，不用测试数量代替证据质量 | conformance 7 类断言 | #149 |
| 9 路由只选首 workflow，渐进拉取 | triggers 必填 + body ≤150 行预算 | #151 |
| 2 默认核心更小但完整 | body_max_lines 预算 | #151 |
| 10 成功退出码 ≠ 阶段完成 | deploy_to_app 证据门控（real_pytest pass_rate=0 拒部署） | #155 |
| 13 失败经验立即写回 | conformance 拒绝写回审计 + 聚合规范建议 | #156 |
| 17 需求是根，Plan 只拥有达成它的细节 | agent_engineering Step 1.5 验收派生（completion_criterion 引用 PRD AC，禁止偷换验收） | #155 |

### 🟢 待评估

| 原则 | 内容 | 评估 |
|------|------|------|
| 12 Change Contract 贯通 | 生成 skill 的 input/output schema 与 stage 产物 key 契约一致（上游 output → 下游 input 链校验） | 大改造（stage 产物 key 契约体系），需独立立项 |
| 11 Plan 逻辑覆盖与物理材料化分离 | 生成 pipeline 中间产物只在有恢复/交接压力时落盘 | 中（artifact 膨胀治理） |
| 8 局部可行动性与单一语义所有权并存 | 生成 skill 触发短语（局部）与完整定义（唯一）分离 | 已部分覆盖（triggers/description 一致） |
| 18 低自由度执行下沉脚本 | 生成 skill 确定性逻辑（输入校验/格式化）下沉脚本 | 与 execution_type prompt/handler 选择相关 |

### 🔵 理念参考（不直接落地）

原则 6（跨 harness 优雅降级——生成的 skill 是否兼容 Cursor 等外部 harness）、7（SBA 吸收工程复杂度，用户只承担业务决策）、14（完整流程两次独立完成才固化）、15（用户原话先于提炼）、16（完成承诺只覆盖绑定交付物）。

## 5. aiPlat 落地全景（10 个 PR 全部合并）

| PR | 内容 | 关键产出 |
|----|------|---------|
| #149 | A1/A2 conformance 契约 + schema 对齐 | `generated_conformance.py` / `generated_conformance.yaml` + 注册循环校验（真实 video_sense 8 项违规被捕获） |
| #150 | B1 生成骨架化 | agent_engineering 内嵌 SKILL.md 完整模板（字段不得删减 + 三执步） |
| #151 | B2 路由-知识分离 | triggers 必填 + body ≤150 行上下文预算 |
| #152 | B2 深化 + C3 | description/triggers 一致 + video_sense 真实产物 frozen 基线 |
| #153 | B2 注册路由侧 | discovery trigger_conditions fallback 到 triggers（生成物注册即路由可达） |
| #154 | CI 门禁 | 架构守卫 §95 自举校验（契约改弱即 FAIL） |
| #155 | 原则 10+17 | 证据门控（pass_rate=0 拒部署）+ 验收派生 + 修复 P1-14 import 回归 |
| #156 | 原则 13 | conformance 拒绝写回审计 + 聚合规范改进建议 |

**生成物治理五层闭环**：模板约束（B1）→ 契约验收（A1）→ 路由可达（B2 路由侧）→ 真实产物回归（C3）→ CI 门禁（§95）。

## 6. 测试与质量

- conformance 测试 21 项 + 证据门控 6 项 + 路由 3 项（持续守护）
- 架构守卫 95 节全绿；每个 PR CI 全绿（3 pytest + 2 contracts-guard + Architecture Compliance + e2e-docker）
- 系统契约 §5.2 扩至 21 条；审计报告 §7.5 全标注

## 7. 结论

SBA 是**规则治理元模式**的优秀参考：把"文档会腐化"变成可机器验证的失败。aiPlat 应用工厂已将其核心哲学（生成物契约、路由-知识分离、任务完成判断、失败写回）落地为机器强制机制，并规避了 SBA 自身的自举豁免缺陷。剩余高价值项为原则 12（stage 产物 key 契约贯通），需独立立项评估。
