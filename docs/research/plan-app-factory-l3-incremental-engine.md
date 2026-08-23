# L3 设计：增量 diff 合并引擎（从 L2"整文件重写"→"只改受影响文件 + 可审批合并"）

> **状态**：✅ **已实施**（2026-08-23，PR #83 合并；实施落地记录见 §10，与设计的差异已标注）
> **目标**：把 L2 的"重写而非合并"升级为"**限定范围的 AI 修改 + 机器 diff + 人工审批合并**"——彻底解决评审指出的"重写语义黑箱"残余风险（L2 设计文档 §8 风险 5/7/8）。
> **关联**：《plan-app-factory-l2-import-repo.md》§7（L3 = "只重生成受影响文件 + diff 合并"）+ 埋点阈值（skip_pytest_gate >40% 触发 L3 优先级）。

---

## 1. 背景：为什么需要 L3

### L2 的两个真实痛点（评审确认 + 上线风险）

| # | 痛点 | L2 现状 | 后果 |
|---|---|---|---|
| 1 | **无关文件被重写** | 用户勾选 A.py，AI 只重写 A.py——**但** A.py 内部**所有**代码都会被 AI 重新生成（不只需求相关的部分） | 原有暗坑/性能 Hack/隐式全局变量可能丢失（虽然对外接口保留） |
| 2 | **改动黑箱** | AI 重写后直接覆盖部署目录，无 Diff 视图，用户只能"事后人工对比 imported/ 原件" | 部署后发现逻辑变了才发现，试错成本高（§3.9 靠 Build Log 刷屏提醒缓解，不根治） |

### L3 解决什么

1. **影响面限定**：只对"受变更需求影响的文件"重生成（不是勾选文件内部全量重写，而是连勾选文件都只改相关区域）
2. **改动可见**：AI 修改 → 系统 diff（新旧对比）→ **用户审批合并**（merge review）→ 才应用
3. **与 L2 并存**：`full_rewrite`（L2 现状，默认）与 `incremental_merge`（L3）双策略，按需选择

### L3 不做的事（边界）

- ❌ 不做"AI 自动合并代码"（自动应用未经审批的合并仍是安全红线）
- ❌ 不做系统级重构/跨模块影响分析（那是 L4 多模块编排）
- ❌ 不保证"AI 只改需求相关的行"绝对精确——但 **AI 改动会在 diff 中显式暴露，由用户审批把关**

---

## 2. 目标

1. 用户勾选文件 + 填意图后，可选择 **`incremental_merge`（增量合并）** 模式
2. AI 只重生成**受影响文件集**（用户勾选文件 + import 引用分析扩展），且指令要求"只改与需求相关的区域，其余与旧文件一致"
3. 系统对每个受影响文件计算 **diff（新旧对比）**，生成**合并预览**
4. 用户**审批合并**（逐文件查看 diff → 通过/驳回），通过后才写入部署目录
5. 全程可回滚（merge 前快照 + imported/ 原件）

---

## 3. 设计方案

### 3.1 数据流

```
用户                                  应用工厂
 │  ① 选择 merge_strategy=incremental_merge
 │     勾选 src/auth/login.py + 意图"增加验证码"
 ├────────────────────────────────────▶│  ② import-repo（L2 已有）→ imported/ 原件
 │                                      │  ③ ImpactAnalyzer：受影响文件集
 │                                      │     = 勾选文件 + import 引用分析
 │  ④ start → code_generation stage    │
 ├────────────────────────────────────▶│  ⑤ prompt 注入（L2 体系 + 增量指令）：
 │                                      │     - imported 清单 + 受影响文件全文
 │                                      │     - 意图锚点 + 增量指令
 │                                      │     （只改相关区域，输出完整新文件）
 │  ⑥ 产出：每受影响文件的新版本       │
 │                                      │  ⑦ DiffMerger：新旧 diff → 合并预览
 │  ⑧ 前端 merge 审批界面              │
 │     逐文件查看 diff → 通过/驳回      │
 ├────────────────────────────────────▶│  ⑨ 通过 → 写部署目录 + Build Log 记录
 │                                      │     驳回 → 反馈重新生成（L2 已有 regenerate）
```

### 3.2 配置字段（PipelineStageConfig 新增）

```
merge_strategy: str = "full_rewrite"   # "full_rewrite"(L2 默认) | "incremental_merge"(L3)
merge_review_required: bool = False    # incremental_merge 时强制 true（用户审批门禁）
```

- `full_rewrite`：完全保持 L2 行为（行为契约 prompt + 覆盖）
- `incremental_merge`：注入增量指令 + 产出 diff 预览 + 强制审批

### 3.3 影响面分析：`ImpactAnalyzer`（新增，platform builder 侧）

```python
def analyze_impact(import_root: str, modify_files: list, manifest: list) -> dict:
    """确定受影响文件集：用户勾选 + import 引用分析（v1 范围）。"""
    affected = {m["path"] for m in modify_files}          # 用户勾选（必改）
    # v1：只做一阶引用分析（成本可控）
    #  - 被勾选文件 import 的项目内文件 → 可能受接口变化影响
    #  - import 了勾选文件的项目内文件 → 调用方可能受影响
    refs = _scan_imports(import_root, affected)           # 正则/简单解析 import/from
    affected |= {p for p in refs if p in manifest_paths}  # 限定在已导入文件内
    return {"affected": sorted(affected), "analysis": refs}
```

**v1 边界**：只分析 Python（`import x` / `from x import y`）一阶引用；其他语言/多阶引用不做（标记为"未覆盖，需人工确认"）。影响面分析结果在**前端展示**（用户可取消勾选被自动加入的文件）。

### 3.4 增量生成 prompt 策略：`IncrementalGenerator`（core prompt 注入扩展）

在 L2 的 `inject_imported_context` 注入基础上，`merge_strategy=incremental_merge` 时**替换行为契约块**：

```
## 行为契约（增量修改）
对以下受影响文件：基于注入的旧文件内容进行【增量修改】——
1. 只修改与变更需求相关的区域；其余代码必须与旧文件【逐字节一致】（包括注释、格式、顺序）
2. 输出每个受影响文件的【完整新版本】（## FILE: 格式），不要输出 diff 片段
3. 保留：原有对外接口（函数签名/类名/路由路径）、关键边界处理、注释中标记的已知坑
4. 若某文件无需任何修改，明确标注 "## UNCHANGED: <path>"（不输出新版本）

## 受影响文件（用户确认 + 影响面分析）
1. src/auth/login.py — 意图：登录增加验证码校验
```

**为什么输出完整新文件而非 diff**：LLM 生成 unified diff 格式不稳定（行号/hunk 头易错），全文件输出 + 系统用 difflib 计算 diff 更可靠（L3 设计决策 1）。

### 3.5 Diff 合并：`DiffMerger`（新增，platform builder 侧）

```python
def build_merge_preview(original: str, new: str, path: str) -> dict:
    """新旧文件 diff → 合并预览（三路：base=imported 原件, new=AI 新版本）。"""
    diff_lines = list(difflib.unified_diff(
        original.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
    hunks = _group_hunks(diff_lines)          # 按 @@ 分块
    return {
        "path": path,
        "changed_lines": sum(1 for l in diff_lines if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))),
        "hunks": hunks,                        # [{header, lines}]
        "unchanged": len(original.splitlines()) - changed,  # 保持一致的代码行数
    }

def apply_merge(project_id, previews, original_root, deploy_dir) -> dict:
    """用户审批通过后：新版本写入部署目录 + 记录 merge 审计。"""
    # 安全：写入前 py_compile / tsc 语法验证（按文件类型）
    #      接口保留验证（AST 提取函数签名对比，仅 Python）
    #      merge 前快照（deploy_dir 备份到 deploy.prev）
```

**合并语义**：以 AI 新版本为"基"写入部署目录；但**未变化的行**（diff 中 unchanged hunk）本应与旧文件一致——若 AI 擅自改了未要求区域，diff 会显示这些改动，用户审批时可见（这就是"改动可见"的保障）。

### 3.6 安全（重点）

| 风险 | 防护 |
|---|---|
| AI 改了未要求区域 | diff 显式展示所有变更行，**用户逐文件审批**（merge_review_required） |
| 合并后语法错误 | 写入前按类型验证：Python `py_compile`，TS `tsc --noEmit`（后端能力，前端轮询结果） |
| 对外接口丢失 | Python AST 提取新旧函数签名/类名/路由装饰器对比，缺失 → 合并预览标红 + 阻断 |
| 回滚 | merge 前 `deploy_dir` 快照到 `deploy.prev`；`imported/` 原件始终保留 |
| 影响面误判 | 分析结果前端展示，用户可取消勾选（分析是建议，用户是最终决定） |

### 3.7 回滚

- merge 前：`deploy.prev` 快照（复用 L2 prev 模式）
- 用户可 `rollback_stage` 回到 merge 前状态
- `imported/` 原件永不被覆盖（与 L2 一致）

---

## 4. 前端改动

| 元素 | 位置 | 说明 |
|---|---|---|
| **合并模式选择** | L2 导入面板 | "修改模式"单选：`整文件重写（L2，默认）` / `增量合并（L3，推荐）`——后者显示"改动将逐文件审批"说明 |
| **影响面展示** | 勾选区 | 显示 ImpactAnalyzer 自动加入的文件（"影响面分析：新增 src/models/user.py（被 login.py import）"，可取消） |
| **合并审批界面** | 项目详情新面板 | 逐文件 diff 展示（`+` 绿 / `-` 红 / unchanged 灰），顶部摘要（改动行数/未变行数/接口保留状态）；每文件"通过 / 驳回"；全部通过后"应用合并" |
| **接口警告** | 审批界面 | AST 检测到接口缺失 → 文件标红 + 禁止通过 |
| **Build Log** | 运行记录 | 应用合并后记录 `Merged N files (incremental_merge)` + 每文件 diff 摘要 |

## 5. 验收标准

| # | 验收 | 方法 |
|---|---|---|
| 1 | incremental_merge 模式只重生成受影响文件集 | 集成：勾选 login.py，ImpactAnalyzer 产出集合含 login.py（+ 引用文件）→ 部署目录中未受影响文件字节不变 |
| 2 | 未受影响文件不被触碰 | 集成：导入 A.py+B.py，merge 改 A.py → B.py 内容 hash 不变 |
| 3 | 增量指令注入生效 | 单测：mock prompt → 断言含"增量修改/逐字节一致/## UNCHANGED" |
| 4 | 无需修改的文件标注 UNCHANGED | 单测：mock AI 输出 `## UNCHANGED: x.py` → 不生成新版本 |
| 5 | diff 预览正确 | 单测：构造旧/新文件 → hunks 数量与 changed_lines 正确 |
| 6 | 语法验证拦截 | 集成：AI 输出语法错误 Python → merge 应用前被拦截 |
| 7 | 接口保留检测 | 单测：新版本删除 `def login(` → 预览标红 + 阻断 |
| 8 | 审批门禁 | 集成：未审批 → 部署目录不更新；全部通过 → 更新 |
| 9 | 回滚可用 | 集成：merge → rollback → deploy.prev 恢复 |
| 10 | 与 L2 并存 | 单测：merge_strategy=full_rewrite → 行为契约 prompt（L2）不变 |

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| ImpactAnalyzer（影响面分析 + 前端展示） | 0.5 天 |
| prompt 增量指令注入（core，merge_strategy 配置驱动） | 0.5 天 |
| DiffMerger（diff/预览/语法/接口验证/快照） | 1 天 |
| 前端（模式选择/影响面/合并审批界面） | 0.75 天 |
| 测试（10 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 3.25 天** |

## 7. 与后续层级的关系

- **L3 做完**：改既有代码从"黑箱重写"升级为"**可见、可审批的增量修改**"——从 1 到 N 可行
- **L4（多模块编排）**：跨模块影响分析（不只一阶 import）+ 模块级项目——从 1 到 100 的架构路径

## 8. 风险与开放问题

1. **"AI 只改相关区域"不保证**：增量指令是软约束，AI 可能改多余区域——靠 diff 显式暴露 + 用户审批兜底（L3 的核心价值正在于此：不信任 AI 自律，信任可见性 + 人审）。
2. **引用分析精度**：v1 只做 Python 一阶 import；JS/多阶/动态导入未覆盖 → 影响面可能漏文件 → 前端"影响面"标注"仅供参考"，用户可自行补勾选。
3. **合并冲突**：同一文件被 AI 与用户手动修改的并发场景——L3 只处理"AI 新版本 vs imported 原件"单路合并；用户手动改部署目录后 merge 覆盖的问题用 `deploy.prev` 快照 + 审批时"旧版本已变更"检测缓解。
4. **token 成本**：输出完整新文件比输出 diff 贵（大文件场景）——v1 接受，后续可加"diff 输出模式"降本（AI 生成 diff 格式校验通过后启用）。
5. **接口检测语言覆盖**：v1 仅 Python AST；TS/其他语言用文本标记兜底。
6. **与 skip_pytest_gate 的关系**：merge 审批不替代测试门禁；审批通过后仍走 pytest（除非用户显式跳过）。

---

## 9. 与 L2 的衔接清单

| L2 资产 | L3 复用/扩展 |
|---|---|
| `inject_imported_context` 注入 | 保留；`merge_strategy` 决定注入"重写契约"（L2）还是"增量指令"（L3） |
| `behavior_prompt` / `intent_anchor_block` | 增量指令替换 behavior_prompt；意图锚点不变 |
| `imported/` 与部署目录隔离 | 原件即 merge 的 base（三路合并的 base） |
| prev 快照模式 | 扩展为 `deploy.prev`（merge 前） |
| Build Log regenerated 警告 | 升级为 `Merged N files (incremental_merge)` 记录 |
| 前端勾选/意图/手册弹窗 | 加"修改模式"单选 + 影响面展示 + 合并审批界面 |

---

## 10. 实施落地记录（2026-08-23，PR #83）

### 10.1 落地范围（验收 10 项全部通过）

| 模块 | 落地位置 | 状态 |
|---|---|---|
| ImpactAnalyzer（影响面分析 + 叶子模块名 fallback） | `aiPlat-platform/builder/merge_engine.py` | ✅ |
| DiffMerger（diff 预览/语法/接口 AST/apply 快照/imported 基线） | 同文件 | ✅ |
| merge-preview / merge-previews / merge-apply 端点 | `aiPlat-platform/api/routers/builder.py` | ✅ |
| 增量行为契约（_L3_INCREMENT_PROMPT）+ rebuild 按策略选 prompt | `builder_project_service.py` | ✅ |
| PipelineStageConfig.merge_strategy + merge_review_required | `aiPlat-core/core/schemas_builder.py` | ✅ |
| 引擎剔除 `## UNCHANGED:` 标记 | `pipeline_engine.py` `_deploy_file_blocks` | ✅ |
| 前端修改模式单选 + 逐文件 diff 审批界面 | `Factory/index.tsx` + `builderTeamApi.ts` | ✅ |

### 10.2 与设计的差异（代码优先原则标注）

| 设计（§） | 实际实现 | 说明 |
|---|---|---|
| §3.3 影响面"Python 一阶 import 引用" | 增补**叶子模块名 fallback**：`import user` 在完整模块 key 匹配失败时，用最后一段（如 "user"）匹配唯一文件 | 覆盖裸模块 import 常见写法 |
| §3.5 apply_merge | 以 **imported/ 全量复制为部署基线**，再用通过审批的新版本覆盖受影响文件 | 保证部署目录完整（UNCHANGED 文件从原件保留），不依赖 deploy_to_app 的 FILE 块解析 |
| §3.2 merge_strategy 作为 stage 字段 | 字段保留在 PipelineStageConfig（配置载体），但**实际选择由 platform 侧 `confirmed_prd.merge_strategy` 驱动**（rebuild 时选 prompt），引擎不做策略分叉 | 更符合最小改动面 + 项目级选择语义；stage 字段为将来按 stage 覆盖预留 |
| §3.6 接口检测"Python AST" | `_extract_signatures` 提取函数/类/**路由装饰器路径**（`@router.get("/x")`），缺失即阻断 | 路由路径也纳入接口保护 |

### 10.3 验证

- 测试：`test_l3_merge_engine.py`（动态 10）+ `test_l3_merge_static.py`（静态 7）= **17 passed**（与 L2 34 + freshness 8 合计 59）
- 架构守卫 exit 0 + engine guard clean（无新 state key）+ 前端 tsc/build + Rule 6 全绿
- contracts：acceptance 1.42 + 鉴权规范 §13 + run spec 五十轮 + boundary + capability 登记
