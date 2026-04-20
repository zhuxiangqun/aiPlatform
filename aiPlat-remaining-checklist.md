# aiPlat Remaining Checklist（以 “可结束” 为目标）

> 目的：把“看起来一直在做但结束不了”的问题，拆成**可验收**的清单。  
> 规则：除非明确新增需求，否则**不再加新项**，按优先级逐一打勾直至清单清零/或达到 MVP 退出标准。

## MVP 退出标准（建议）

- **治理闭环可追溯**：核心高风险操作（repo changeset / prompt / tenant policy）都能产出 `change_id`，并能在 Change Control 查看证据链。
- **P0 运维可用**：management 上能完成“审阅 →（必要时）审批 → 放行/回滚 → 看到 autosmoke/测试结果”。
- **P0 可定位**：出现阻断时前端能展示结构化 gate 错误（含下一步动作/链接）。

---

## A. 治理闭环（Change Control / Approvals / Gate）

- [x] Repo changeset：record 产出 `change_id` + 非本地/高风险触发审批 + UI 审阅入口
- [x] Prompt：upsert/rollback/delete 产出 `change_id` + autosmoke gate + autosmoke 结果回写到同一 `change_id`
- [x] Tenant policy：upsert 产出 `change_id` + 写入 Change Control
- [x] **Approvals ↔ Change Control 反向联动（P0）**  
  - Approvals 列表/详情页展示关联 `change_id`（若存在），提供一键跳转 Change Control
- [x] **治理错误标准化（P0）**  
  - 统一使用 `_gate_error_envelope`（code/message/change_id/approval_request_id/next_actions/detail）
  - management 透传 core 的非 2xx 错误 payload（避免 gate envelope 在代理层丢失）
  - 前端统一用 `toastGateError` 展示（已局部接入）

---

## B. Prompt 平台化（从“库能力”→“平台能力”）

- [x] Prompt 模板：列表/查看/versions/diff UI（management 代理 + frontend 页面）
- [x] Gate：verification pending/failed 阻断新 upsert（rollback 作为恢复路径）
- [ ] **Prompt 变更 UI 完整闭环（P0）**
  - [x] 新建/编辑（upsert）表单 + require_approval/approval_request_id 支持
  - [x] Rollback UI（选择版本 → 回滚 → 看到 change_id/links）
  - [x] Delete UI（带审批）
  - [x] 在 Prompt 页面展示 autosmoke 状态/trace/job 链接（来自 metadata.verification + change control）
- [ ] **Prompt 灰度/发布语义（P1，可选）**  
  - 版本 pin / 灰度比例 / 回滚策略（若产品需要）

---

## C. Repo-aware 开发工作流（向 Claude Code 学的 P0 主线）

- [x] Repo changeset：patch/staged/tests/record + management Repo 页面审阅入口
- [ ] **Git primitives（P0）**
  - [x] commit（带建议 message + 审批/审计）
  - [x] branch 操作（create/switch）
  - [x] 将“recorded changeset”与 commit 建立关联（使用同一 change_id 写入 Change Control）
- [ ] **失败可恢复（P1）**
  - [ ] /undo /retry /stop 的一等能力（尤其是写文件/执行命令/发布类操作）

---

## D. Context 可观测（从“单次诊断”→“趋势与回归”）

- [x] Context/Prompt assemble 单次诊断页（config + assemble）
- [ ] **Context 指标沉淀（P1）**
  - [ ] 记录 tokens_in/out、cache_hit、compaction_applied、session_search_hits 等到 store（可按 tenant/session 聚合）
  - [ ] management Insights：趋势图/TopN/回归对比
  - [ ] Doctor 动作：建议开启压缩/缓存/会话搜索（必要时审批）

---

## E. Skill/插件生态（P0/P1）

- [x] Capability→Policy 辅助页面（从 capabilities(tool:xxx) 汇总 → 写入 tenant policy）
- [ ] **capabilities 数据源打通（P0）**
  - [ ] 后端确保从 `SKILL.md` front matter 提取 capabilities 并写入 skill metadata（而不是仅靠手工）
  - [ ] capability schema 校验（缺失/非法时 UI 告警）
- [ ] **插件元数据规范化（P0）**
  - [ ] 插件/skill pack：权限声明、依赖声明、测试声明、版本/升级/回滚策略
  - [ ] management UI：安装/升级/回滚的可视化流程
- [ ] **技能自生长闭环（P1）**
  - [ ] 学习产物必须落 workspace scope
  - [ ] 审批 + autosmoke 回归门禁 + 可回滚

---

## F. Onboarding Wizard（P0）

- [ ] **从 0 到可用的一键流程（P0）**
  - [ ] 逐步检测：依赖 → 配置 → 验证 → 运行
  - [ ] 每一步都能 Doctor→Action 自动修复（带审批/重试）
  - [ ] 导出一份 “onboarding 报告”（便于支持/排障）

---

## G. Exec Backends（P1）

- [x] Exec backend health 页面（current_backend + backends health + 标志位）
- [ ] **后端路由/切换（P1）**
  - [ ] 在 management 提供选择/切换入口（需审批）
  - [ ] 后端维度 metrics：success_rate/latency/policy_denied_count
