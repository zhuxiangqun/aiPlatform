# Skill Types & Discovery Contract（Skill 类型与发现/加载契约）

本文件定义 aiPlat 对 “目录化 skills（SKILL.md）” 的生产级落地规范，目标是复刻 OpenCode 的体验：**可发现（find）+ 按需加载（load）**，同时满足企业生产要求：**版本冻结、权限治理、可观测、可回滚、避免 prompt bloat**。

## 1. 目录与扫描（MUST）

系统 **MUST** 支持按 scope 扫描 skills（低优先级 → 高优先级，后者覆盖前者）：

- **engine（只读，随发布）**：`core/engine/skills/<skill_id>/SKILL.md`（或 `AIPLAT_ENGINE_SKILLS_PATH(S)` 覆盖）
- **workspace（可写，运行期资产）**：`~/.aiplat/skills/<skill_id>/SKILL.md`（或 `AIPLAT_WORKSPACE_SKILLS_PATH(S)` 覆盖）

生产环境 **SHOULD**：
- engine skills 目录为只读（镜像内/只读挂载）
- workspace skills 目录为持久化卷（多实例一致性由外部存储/发布流程保证）

## 2. 技能文件格式（MUST）

每个目录化 skill **MUST** 满足：
- 每 skill 一个目录：`<skill_id>/`
- 存在 `SKILL.md`
- `SKILL.md` 顶部包含 YAML frontmatter（`--- ... ---`），至少包含：
  - `name`（稳定 id，建议与目录名一致）
  - `description`
  - `version`（推荐 semver 或 commit）

## 3. 自动判别：规则型 vs 可执行型（MUST，默认保守）

系统 **MUST** 进行自动判别，并将结果写入技能元数据字段：`skill_kind = rule|executable`。

### 3.1 显式声明优先（MUST）

如果 frontmatter 包含：
- `executable: false` → **MUST 判定为 rule**
- `executable: true` 且同时提供 `runtime` 与 `entrypoint` → **MUST 判定为 executable**

> 生产推荐：团队规范要求所有可执行 skill 必须显式 `executable: true`。

### 3.2 结构推断（SHOULD，作为兜底）

若未显式声明，系统 **SHOULD** 根据目录结构进行保守推断：
- 存在 `handler.py` 或 `manifest.(json|yml|yaml)` 或可解析的 `entrypoint` → 可判定 executable
- 否则默认 rule

### 3.3 安全门槛（MUST）

即使判定为 executable，系统仍 **MUST** 通过安全门槛，否则降级为 rule 或拒绝加载：
- 必须声明 `permissions`（例如：`network`、`filesystem_write`、`exec` 等）
- 必须具备 provenance（来源 URL + 固定 ref/commit）与 integrity（hash）
- 默认权限为 `ask` 或 `deny`，不得默认 allow（除非在受控白名单）

## 4. find / load 接口（MUST）

系统 **MUST** 提供以下能力（以 Tool 或 Syscall 形式均可）：

1. `skill_find(query, limit, kind, category)`  
   - 返回 skills **摘要索引**（name/description/kind/version/metadata）
   - **MUST NOT** 返回 SOP 全文

2. `skill_load(name)`（规则型 skill）  
   - 读取 `SKILL.md` 正文（frontmatter 之后的 SOP）
   - 以可控方式注入 prompt（推荐 overlay）
   - 记录 `skill_hash/version` 到 meta / run_events

3. `skill_execute(name, args)`（可执行型 skill）  
   - 走 `sys_skill_call`
   - 受 PolicyGate/ApprovalGate 约束

## 5. 预算与 prompt bloat 防护（MUST）

系统 **MUST** 对 “可用 skills 列表” 做预算控制：
- `AIPLAT_SKILL_DESC_PER_SKILL_MAX_CHARS`
- `AIPLAT_SKILLS_DESC_MAX_CHARS`

当发生截断/隐藏时：
- **MUST** 记录统计（included/hidden/truncated/chars_total）
- **SHOULD** 引导使用 `skill_find`

## 6. compaction/长会话鲁棒性（SHOULD）

系统 **SHOULD** 在会话 compaction 后仍保持 skills 可用：
- 保留 skills 索引摘要（或在每轮 prompt 组装中按预算重新注入摘要）
- 允许在任意时刻再次 `skill_find/skill_load`

## 7. 生产分发与回滚（SHOULD）

团队/生产环境推荐流程：
- 规则型 skills：以 “skills 仓库/目录” 版本冻结（commit/tag），随发布进入 engine skills
- 可执行 skills：以 skill pack/包资产形式发布，支持 rollback/rollout，并强制验收

