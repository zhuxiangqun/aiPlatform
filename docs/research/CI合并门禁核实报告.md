# CI 合并门禁核实报告（分支保护配置实测）

> **核实问题**：CI 是否真正 gating 合并？宪法测试 24 failed 是否会阻止合入 main？
> **核实方法**：gh CLI 查询 GitHub API 分支保护配置 + CI 运行记录 + git 分支关系。
> **核实时点**：2026-08-15。

---

## 0. 结论（一句话）

**CI 不 gating 合并——main 分支保护已启用（要求 1 个 PR review），但 `required_status_checks.contexts` 为空数组 []，未要求任何 workflow 的 status check 通过。宪法测试 24 failed 不会阻止任何合入。**

---

## 1. 分支保护配置（GitHub API 实测）

```json
GET /repos/zhuxiangqun/aiPlatform/branches/main/protection
{
  "required_status_checks": {
    "strict": true,
    "contexts": [],      ← 关键：空！无强制 status check
    "checks": []         ← 同样空
  },
  "required_pull_request_reviews": {
    "required_approving_review_count": 1   ← 需 1 人 review
  },
  "enforce_admins": { "enabled": false }   ← admin 不受保护
  "required_signatures": { "enabled": false }
}
```

**解读**：
- ✅ 分支保护**存在**（需 PR + 1 review）
- ❌ **required_status_checks.contexts = []** → **没有任何 CI workflow 被设为必须通过的 status check**
- ⚠️ enforce_admins = false → 管理员可绕过

**这意味着**：即使 constitution 测试 24 failed、architecture_guard 4 FAIL，只要 1 人 review 通过就能合并。

---

## 2. 实证：CI 失败但提交照常进 main

**push 触发的 CI 全部 failure（2026-08-04 批次）**：

| workflow | 状态 |
|---|---|
| Architecture Guard | ❌ failure |
| aiplat-genericity-guard | ❌ failure |
| AI Penetration Test | ❌ failure |
| L5 Verification Suite | ❌ failure |
| aiPlat Contracts Guard | ❌ failure |
| ci.yml | ❌ failure |
| docs-verify.yml | ❌ failure |

**但提交照样进了 main**——因为分支保护不要求这些 status check。**"CI 红"与"能否合并"完全脱钩。**

**定时（schedule）CI 同样持续 failure**：L5 Verification Suite + AI Penetration Test 从 8-12 到 8-15 连续多天全红。

---

## 3. 当前分支状态（重要上下文）

| 项 | 值 |
|---|---|
| 本地 main 领先 origin/main | **213 个未推送提交** |
| 本地最新 | `9afd7742`（含我今天的守卫修复 93b7c25c + aiPlat-bot 宪法修复 8c6a5154） |
| origin/main 最新 | `8d8ae825`（事件驱动进度管道，aiPlat-bot 并行推的） |
| 结论 | 本地大量修复（含宪法违规修复）**未推送**，远端 CI 未反映这些修复 |

**重要发现**：`8c6a5154`（fix: 宪法测试违规 — infra 硬编码 aiPlat fallback 清空 + phase 字符串分支改 skill_name）**已在本地 main**——aiPlat-bot 正在**并行修复宪法违规**（与我审计时相比，infra 硬编码和 phase 分支已被修掉一部分）。本地 213 个未推送提交里可能包含更多修复。

---

## 4. 结论与建议

### 4.1 当前状态判定

| 问题 | 答案 |
|---|---|
| CI 是否 gating 合并？ | ❌ **不 gating**（required_status_checks.contexts = []） |
| 宪法 24 failed 会阻止合并吗？ | ❌ 不会 |
| 有 PR review 要求吗？ | ✅ 需 1 人 review（但 enforce_admins=false，admin 可绕过） |
| CI 红灯被忽视了吗？ | ✅ 是（8-04 push 全 failure 仍合入；8-12~8-15 定时 CI 持续红） |
| 本地修复推送了吗？ | ❌ 213 个提交未推送（含宪法违规修复） |

### 4.2 改进建议

| 优先级 | 项目 | 说明 |
|---|---|---|
| **P0** | **启用 required_status_checks**：把 `architecture-guard` / `constitution` / `ci.yml` 设为必过 context | 让 CI 真正 gating，宪法违规会阻止合入 |
| **P0** | **推送本地 213 个修复**（含 8c6a5154 宪法修复 + 93b7c25c 守卫修复） | 让远端 CI 反映修复进展 |
| **P1** | 设置 enforce_admins=true（防 admin 绕过） | 保护更严格 |
| **P1** | 清理定时 CI 的持续 failure（L5 Verification/AI Pentest 连续红） | 消除噪音 |

### 4.3 设置方法（供执行）

```bash
# 设置 required status checks（需要 admin 权限）
gh api -X PATCH repos/zhuxiangqun/aiPlatform/branches/main/protection/required_status_checks \
  -f strict=true \
  -f contexts[]=architecture-guard \
  -f contexts[]=constitution \
  -f contexts[]=ci
# 或 UI：Settings → Branches → main → Require status checks to pass before merging
# 勾选: Architecture Guard / Run constitution tests / CI
```

---

## 5. 核实方法局限

1. 分支保护配置为 GitHub API 实时查询（2026-08-15），配置可能随时变更
2. 本地 213 个未推送提交的具体内容未逐一核查（仅确认 8c6a5154 含宪法修复）
3. "CI 失败仍合入"基于 8-04 push 记录——若这些提交是直接 push（非 PR），分支保护本就不适用（直接 push 到 main 若 admin 可绕过保护）
