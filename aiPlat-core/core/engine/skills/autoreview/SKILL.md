---
name: autoreview
display_name: 自动代码审查
description: >
  提交前自动审查代码质量。Diff-only模式——绝不审查全量文件。
  单引擎模式 reasoning 扫描 P0/P1，code_gen 扫描 P2 并生成修复补丁。
  面板模式(panel=true)仅在 focus=security 时启用三引擎并行投票。
version: 1.0.0
category: analysis
status: enabled
protected: true
execution_type: handler
execution_mode: inline

triggers:
  - 自动审查
  - code review
  - autoreview
  - 代码审查
  - review

skip_when: 用户仅询问最佳实践而不触发审查

permissions:
  - llm:generate
  - tool:file_read
  - tool:file_edit
  - tool:code_search
  - tool:git

effects:
  - type: read
    resources: [filesystem:workspace]
    idempotent: true
    rollback_available: false
  - type: write
    resources: [filesystem:workspace]
    idempotent: false
    rollback_available: true

input_schema:
  target:
    type: string
    required: true
    description: >
      审查目标。'diff'(当前未提交改动) | 'commit:<sha>' | 'branch:main'。
      禁止值: '.', '/', 'workspace', '*', '~', '..'
  focus:
    type: string
    default: comprehensive
    enum: [security, performance, style, comprehensive]
    description: >
      审查维度。security=全维度+面板模式可用, comprehensive=全维度单引擎,
      style=仅P2风格检查, performance=性能反模式
   panel:
    type: boolean
    default: false
    description: >
      多引擎面板模式。仅在 focus=security 时生效(reasoning+code_gen+chat 三引擎并行投票)。
      其他 focus 值自动降级为单引擎并记录 warning 日志。
  mode:
    type: string
    default: quick
    enum: [quick, deep]
    description: >
      quick=硬投票聚合(2-3s), deep=Aggregator LLM综合判断(10-15s, MoA风格)。
      deep 模式仅在 panel=true 且 focus=security 时生效。
      diff >500 行时自动建议切换到 deep。
  preset:
    type: string
    default: code_review
    description: >
      MoA preset。可选: code_review | architecture | security。
      自定义 preset 在 presets.yaml 中配置。
  auto_fix:
    type: boolean
    default: false
    description: >
      自动修复 P2 级(低风险)问题。每轮修复前 git stash -u checkpoint，
      两轮未收敛则回滚。P0/P1 不自动修。

output_schema:
  report:
    type: object
    required: true
    properties:
      score:              { type: number, description: "0-100(P0:-20,P1:-5,P2:-1)" }
      p0_count:           { type: integer }
      p1_count:           { type: integer }
      p2_count:           { type: integer }
      clean:              { type: boolean, description: "P0=0 且 P1<3" }
      scope_ok:           { type: boolean, description: "Scope Governor 检查通过" }
      abandoned:          { type: boolean, description: "自动修复因超出范围/未收敛而放弃" }
      issues:             { type: array, description: "全部分级问题" }
      common_findings:    { type: array, description: "多引擎共同发现(面板模式)" }
      unique_findings:    { type: object, description: "各引擎独有发现(面板模式)" }
      auto_fixed:         { type: integer, description: "自动修复的P2问题数" }
  markdown:
    type: string
    required: true
    description: "人类可读的Markdown审查报告"

completion_criterion: |
  1. 每个问题有明确的文件路径和行号
  2. P0(阻断)/P1(重要)/P2(建议) 三级分级，每级有改进建议
  3. clean=true 时输出 "autoreview clean: no accepted/actionable findings reported"

metadata:
  keywords:
    objects: [代码, PR, diff, commit]
    actions: [审查, review, 检查, 修复, 扫描]
  sop_goal: 自动审查 Diff 代码质量，分级输出问题，可选自动修复 P2
  sop_flow:
    - "获取 Git Diff（拒绝全仓库/全文件审查，大文件截断为函数签名+首尾200行）"
    - "单引擎/面板模式执行审查（引擎隔离，不读被审仓库Agent配置）"
    - "Scope Governor 建立审查基线，检查修改边界"
    - "可选自动修复 P2 问题（git stash -u checkpoint，两轮未收敛则回滚）"
    - "输出结构化审查报告（JSON + Markdown）"
---
# Autoreview — 自动代码审查 (Engine Skill)

## 审查维度
- **P0 (阻断)**: 安全漏洞、数据丢失、崩溃风险、认证绕过、注入攻击
- **P1 (重要)**: 逻辑错误、边界条件、并发安全、资源泄漏、错误处理缺失
- **P2 (建议)**: 代码风格、命名规范、可维护性问题、死代码、重复代码

## 审查模式
- **单引擎（默认）**: reasoning 扫 P0/P1，code_gen 扫 P2 + 生成补丁
- **面板模式（focus=security + panel=true）**: reasoning + code_gen + chat 三引擎并行投票

## Scope Governor 规则
1. 锁定初始 diff 的文件列表作为审查基线
2. 修复阶段不允许修改基线外的文件
3. 净增行数超过基线 50%时停止修复（P0 修复豁免：阈值翻倍至 100%）
4. 两轮修复未收敛 → git stash pop 回滚，上报人工决策

## 引擎隔离
- 审查者使用独立 `REVIEW_SYSTEM_PROMPT`
- `sys_llm_generate` 调用时 `inject_agent_config=False`
- 不读取被审仓库的 AGENTS.md / CLAUDE.md / .codex/ 配置

## 大文件保护
- Diff 超过 8000 tokens → 截断：保留函数签名 + 首尾200行 + dev/null 行
- 新增文件超过 3000 行 → 仅审查函数签名 + 关键逻辑片段

## 禁止
- 绝不接受 '.' '/' '*' '~' '..' 作为 target（拒绝全仓库审查）
- panel 模式仅在 focus=security 时真正启用（其他自动降级为单引擎）
