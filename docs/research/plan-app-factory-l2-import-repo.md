# L2 设计：应用工厂"导入既有代码"输入通道（从 0→1 生成器 → 1→100 演进器第一步）

> **状态**：设计文档（2026-08-22，待评审）
> **目标**：让应用工厂第一次具备"接触既有代码"的能力——用户导入现有仓库，AI 看得见既有文件、按变更需求增量修改，而非从零全量重生成。
> **关联**：《应用工厂分析报告.md》§"从 1 到 100"三缺口中的缺口 1（输入只认需求文字，不认既有代码）。

---

## 1. 背景：为什么需要 L2

### 现状（代码实证）
| 项 | 现状 | 证据 |
|---|---|---|
| 输入 | 只有 `requirement`（文字）+ `prd_data` | `builder_session.py:90,155` |
| 既有代码 | 无导入入口，引擎只 `rmap.scan(output_dir)` 扫自己刚生成的目录 | `pipeline_engine.py:6046` |
| 重建 | `rebuild_project` = 用现有 PRD 全量重跑 | `builder_project_service.py:1402` |
| 产物形态 | code 模式 `≤15 个文件`的 MVP 快照，非可演进系统 | `code_generation/SKILL.md:116-119` |

### L2 解决的痛点
**"从 1 到 100"的第一步 = 让 AI 看得见已有的"1"**。现在 AI 对既有代码完全盲视——PRD 里写"基于现有 login.py 增加验证码"，AI 根本不知道 login.py 长什么样，只能从零写一个（要么覆盖要么重复）。

### L2 不做的事（边界）
- ❌ 不做增量 diff 合并引擎（那是 L3）
- ❌ 不做多模块编排（那是 L4）
- ❌ 不保证"重构整个系统"——只保证"AI 能读既有代码、改你指定的文件"

## 2. 目标

1. 用户能把**既有代码目录/仓库**导入一个项目（上传 zip 或贴路径）
2. 导入的代码**进入 `_final_state`**，成为 code_generation 的可见上下文
3. 用户需求里引用既有文件时，AI **真的能看到文件内容**并按其风格修改
4. 产出保留"导入代码 + 新改动"两部分（不覆盖用户没让改的文件）
5. 全程可回滚（导入前状态可恢复）
6. **语义透明**：向用户明确告知"被改文件是重写而非合并"（前端红字警告），杜绝"以为只加几行、实际整文件重来"的误判
7. **路径精确**：勾选文件时强制绑定"修改意图"，AI 不猜路径、用户不依赖 AI 猜目录

## 3. 设计方案

### 3.1 数据流

```
用户                                  应用工厂
 │  ① POST /projects/{id}/import-repo   │
 │  （zip 上传 或 existing_dir 路径）     │
 ├──────────────────────────────────────▶│  ② 解压/复制到 ~/.aiplat/apps/{项目}/imported/
 │                                      │  ③ 扫描生成文件清单 manifest.json
 │                                      │     {path → size/hash/lang/概要首行}
 │  ④ 写 PRD："基于 imported/ 下的代码，  │
 │     在 src/auth/login.py 增加验证码"   │
 ├──────────────────────────────────────▶│  ⑤ start → code_generation stage
 │                                      │  ⑥ prompt 注入：
 │                                      │     - imported 文件清单
 │                                      │     - 被引用文件的完整内容
 │                                      │     - 变更需求
 │  ⑦ 产出：new_files + modified_files   │
 │  （部署目录含 imported + 新改动）       │
```

### 3.2 API 设计

```
POST /projects/{project_id}/import-repo
  body: { source: "zip_upload" | "existing_path", zip?: UploadFile, path?: str }
  → { status, imported_files: int, manifest_path, manifest }

GET  /projects/{project_id}/imported-files
  → { files: [{path, size, lang, has_tests}], total }
     （供前端展示导入了什么，用户勾选"这次改哪些" + 填写每文件修改意图）

POST /projects/{project_id}/pre-check-import
  body: { path: "src/auth/login.py" }（可为空 = 全项目）
  → { deps: [{file: "requirements.txt", missing: ["pymysql>=1.0"]}], warn: "tests/ 不存在，pytest 门禁将无法运行" }
     （依赖预检：扫描 requirements.txt/go.mod/package.json，提示缺失依赖可能导致测试失败；
       tests/ 目录检测：无测试 → 返回 Warning，前端展示"可跳过测试门禁"开关）

POST /projects/{project_id}/update-prd
  body: { prd: { ..., modify_files: [
           {path: "src/auth/login.py", intent: "登录增加验证码校验"},
           {path: "src/models/user.py", intent: "用户表增加验证码字段"}
         ], scope_note: "..." } }
  → 现有端点复用（builder.py:216 已存在），modify_files 由纯路径数组升级为"路径 + 意图"绑定
```

### 3.3 核心实现：`import_repo`（builder_project_service.py 新增）

```python
async def import_repo(self, project_id: str, *, zip_bytes: bytes = b"", existing_path: str = "") -> Dict:
    """把既有代码导入项目，生成 manifest，注入 _final_state.imported_repo。"""
    proj = self._projects.get(project_id) or raise ValueError("project not found")

    # 目标目录（独立于部署目录，防覆盖）
    import_root = os.path.join(_apps_home, project_id, "imported")
    os.makedirs(import_root, exist_ok=True)

    if zip_bytes:
        # 解压 zip 到 import_root（安全：拒绝 zip-slip 路径穿越）
        _safe_extract_zip(zip_bytes, import_root)
    elif existing_path:
        # 复制用户指定目录（校验在允许的 home 范围内）
        shutil.copytree(existing_path, import_root, dirs_exist_ok=True)

    # 扫描生成 manifest
    manifest = _scan_imported(import_root)   # [{path, size, sha256, lang, first_line}]

    # 写进 _final_state（重建时 AI 可见）
    state = self._load_pipeline_state(project_id) or {}
    state["imported_repo"] = {"root": import_root, "manifest": manifest, "imported_at": now}
    self._save_pipeline_state(project_id, state)

    proj["imported_repo"] = True
    self._save_projects()
    return {"status": "ok", "imported_files": len(manifest), "manifest": manifest[:100]}
```

### 3.4 行为契约：重写而非合并（关键——评审补充）

**这是 L2 最重要的语义约束，必须对用户透明**：

现有引擎的 `code_generation/SKILL.md` 是**整文件生成**模式（≤15 文件 MVP 快照）。因此 L2 对"被修改文件"的真实行为是：

> **AI 读取旧文件（全文注入 prompt）→ 按变更需求重新生成一整个新文件**，而不是"在第 N 行插入改动"。

后果：用户勾选的 `login.py` 会被**完整重写**——原有暗坑、边界处理、性能优化写法可能丢失（虽然 AI 被要求"保持现有风格"，但模型不保证逐行保留）。这不是 bug，是 L2 的**能力边界**（增量 diff 合并是 L3）。

**强制措施（三层）**：
1. **前端红字警告**（勾选文件时展示，见 §4）：
   > ⚠️ 当前版本将**根据旧代码重写**该文件，而非合并改动。请确认已备份，且你接受"该文件整体重生成"的结果。
2. **prompt 行为指令**（注入到 code_generation，见 §3.5）：
   > 对 modify_files 中的文件：必须基于注入的旧文件内容**重写**该文件以满足变更需求；重写时保留原有对外接口（函数签名、类名、路由路径）、关键边界处理与注释中标记的已知坑。未在 modify_files 中的文件一律不得触碰。
3. **验收可测**（§5 验收 8）：生成后断言"对外接口保留"（如 `def login(` 仍存在、`@router.post("/login")` 仍存在）。

**回滚兜底**：因为语义是"重写"，回滚（`rollback_prd` / `imported/` 原件）是用户唯一的后悔药，§3.7 保证导入前状态可恢复——这是本设计必须做扎实的原因。

### 3.5 code_generation 的 prompt 注入（关键）

在 `code_generation/SKILL.md` 的 input_schema 基础上，流水线 start 时若 `_final_state.imported_repo` 存在，向 code_generation 注入**额外上下文**：

```
## 既有代码（imported_repo）
以下文件已存在于项目 imported/ 目录，按需参考/修改，不要重写未要求改的文件：
- src/auth/login.py（368 行, python）
  ── 内容预览（前 120 行）────────────────
  <实际文件内容>
  ──────────────────────────────────────
- src/models/user.py（201 行, python）...
（只注入被需求引用的文件全文，其余仅清单）

## 行为契约（重写而非合并）
对 modify_files 中列出的文件：必须基于注入的旧文件内容【重写】该文件以满足变更需求。
重写时保留：原有对外接口（函数签名/类名/路由路径）、关键边界处理、注释中标记的已知坑。
未在 modify_files 中的文件一律不得触碰、不得覆盖。

## 变更需求（含意图锚点，路径已由用户确认，无需猜测）
用户要求修改以下文件（路径 = 用户勾选确认，意图 = 用户填写的修改目标）：
1. src/auth/login.py — 意图：登录增加验证码校验
2. src/models/user.py — 意图：用户表增加验证码字段
```

**注入实现**：在 `pipeline_engine._run_stage_skill` 的 code_generation 分支前，检测 `state.imported_repo` → 读被引用文件 → 把 **modify_files 的 {path, intent} 绑定**与**行为契约指令**拼进 stage 输入。引擎不关心业务（保持 §5.8 边界），只做"读文件→附加到输入"的通用能力。

### 3.6 安全（重点）

| 风险 | 防护 |
|---|---|
| zip-slip 路径穿越 | 解压时校验每个 entry 的解析路径在 import_root 内（`Path.resolve()` 前缀检查） |
| 读取任意路径 | `existing_path` 白名单：只允许 `~/.aiplat/**`、`AIPLAT_HOME/**` 下的目录 |
| 覆盖未要求改的文件 | 部署目录 = imported + 新产物分开管理；`_deploy_result_files` 只写 stage 声明的 `deploy_files_target_dir` |
| 敏感信息（密钥） | manifest 跳过 `.env`/`*.pem`/`secrets/`；注入 prompt 前过滤疑似密钥行 |
| 体积 | zip ≤ 50MB，文件数 ≤ 500，单文件 ≤ 2MB（超出截断为预览） |

### 3.7 回滚

- 导入前状态：`_final_state` 每次变更前自动快照到 `_final_state.bak`（复用现有 `_snapshot` 机制）
- 用户可 `rollback_prd` 回到导入前 PRD
- 部署目录：`imported/` 与 `current/` 分离，`rollback_stage` 不影响 imported
- 语义兜底：因为 L2 是"重写"而非"合并"（§3.4），回滚是用户唯一的后悔药——导入前快照 + `imported/` 原件必须保证可完整恢复

### 3.8 测试门禁与依赖预检（评审补充——防流水线卡死）

**痛点**：L2 修改代码后，`pipeline_eval.py` 会跑 `real_pytest` 验证通过率。但导入的既有代码可能**根本没有测试用例**，或测试因**依赖缺失**（数据库连不上、包未装）直接报错——`real_pytest` 会红掉，流水线卡死，用户改一个简单函数却永远无法部署。

**对策（导入阶段双检测 + 门禁逃生舱）**：

| 检测 | 时机 | 行为 |
|---|---|---|
| `tests/` 目录检测 | `import_repo` 扫描 manifest 时（`has_tests` 标记进 manifest） | 无 tests/ → 导入响应带 `warn: "项目无测试用例，pytest 门禁无法运行"`，前端展示 Warning 横幅 + 高级配置"跳过测试门禁"开关 |
| 依赖预检 | `pre-check-import` 接口（§3.2） | 扫描 `requirements.txt` / `go.mod` / `package.json`，对缺失声明依赖给出提示（不阻塞，仅预警） |
| 门禁逃生 | 用户勾选"跳过测试门禁" → 写入 PRD 配置字段 `skip_pytest_gate: true` | `pipeline_eval.py` 检测该字段：true 时 `pass_rate_source` 走 `estimated`（LLM 估算）而非 `real_pytest`，流水线不卡死；**估算必须带 `pass_rate_estimate_reason`**（复用现有 deploy_to_app 字段） |

**边界**：跳过门禁是**用户显式选择**（前端开关 + PRD 字段），默认不跳过；security 类变更（涉及认证/支付）即使勾选跳过，前端二次确认。

## 4. 前端改动（最小）

| 元素 | 位置 | 说明 |
|---|---|---|
| "导入既有代码"按钮 | `Factory/index.tsx` 项目详情区 | 触发 zip 上传或路径输入 |
| 导入文件列表 | 项目详情新增折叠区 | 展示 manifest（含 `has_tests` 标记） |
| **修改意图绑定**（评审补充） | 文件列表勾选区 | 每个勾选文件必须填写一句"修改意图"（如"登录增加验证码"），**空意图不能提交**（提交按钮 disabled + 红字提示"请为每个文件填写修改意图"） |
| **重写警告**（评审补充） | 勾选区顶部红字横幅 | ⚠️ **当前版本将根据旧代码重写该文件，而非合并改动。请确认已备份，且你接受"该文件整体重生成"的结果。** |
| 测试门禁开关（评审补充） | 高级配置折叠区 | 导入响应含 `has_tests=false` 警告时展示："项目无测试用例，pytest 门禁无法运行" + "跳过测试门禁"开关（写入 `skip_pytest_gate`）；security 类变更二次确认 |
| PRD 编辑框提示 | 现有 PRD 编辑 | 提示可引用 `imported/xxx.py` 路径，且 modify_files 已由勾选+意图生成 |

## 5. 验收标准

| # | 验收 | 方法 |
|---|---|---|
| 1 | 上传 zip 后 manifest 生成，文件数正确 | `pytest` 单测：zip 含 3 文件 → imported_files=3 |
| 2 | code_generation prompt 含被引用文件内容 | 单测：mock state.imported_repo + 需求引用 login.py → 断言输入含其内容 |
| 3 | 未要求改的文件不被覆盖 | 集成：导入 A.py+B.py，要求改 A.py → B.py 内容不变 |
| 4 | zip-slip 被拒绝 | 单测：恶意 zip（../evil.txt）→ 异常且未写出 |
| 5 | 密钥文件不进 manifest/prompt | 单测：.env 不在 manifest |
| 6 | 回滚可用 | 集成：import → start → rollback_prd → 状态恢复 |
| 7 | 前端能展示导入列表并勾选 | 手动验证 + tsc/build |
| 8 | **行为契约生效（评审补充）**：prompt 含"重写而非合并"指令；生成后对外接口保留 | 单测：mock 生成结果断言 prompt 含行为契约文案；集成：导入含 `def login(` 的 login.py → 要求加验证码 → 断言产出仍含 `def login(` / 路由路径 |
| 9 | **意图绑定生效（评审补充）**：modify_files 为 {path, intent}，prompt 注入含 intent，空 intent 被拒绝 | 单测：update-prd 传空 intent → 422；mock 断言 prompt 含 "意图：登录增加验证码校验" |
| 10 | **测试门禁逃生（评审补充）**：无 tests/ → 导入响应含 has_tests=false + 前端可勾选 skip_pytest_gate → pipeline_eval 走 estimated 不卡死 | 集成：导入无 tests/ 的项目 → skip_pytest_gate=true → 断言 pass_rate_source=estimated + estimate_reason 非空 |
| 11 | **依赖预检（评审补充）**：pre-check-import 返回依赖清单与缺失提示 | 单测：构造含 requirements.txt 的 zip → 断言响应含 deps 列表 |

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| 后端 `import_repo` + manifest + 安全 | 0.5 天 |
| code_generation prompt 注入（含行为契约指令 + 意图锚点）+ 引擎通用读文件 | 0.5 天 |
| `pre-check-import` 依赖预检 + tests/ 检测 + `skip_pytest_gate` 逃生 | 0.25 天 |
| 回滚/快照 | 0.25 天 |
| 前端（上传/列表/勾选/意图输入/红字警告/门禁开关） | 0.5 天 |
| 测试（10-12 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 2.5 天** |

## 7. 与后续层级的关系

- **L2 做完**：AI 能"看既有代码、改指定文件"——从 1 到 2 可行
- **L3（增量引擎）**：L2 的 prompt 注入验证有效后，加"只重生成受影响文件 + diff 合并"——从 1 到 N
- **L4（多模块编排）**：模块级项目 + API 集成——从 1 到 100 的架构路径

## 8. 风险与开放问题

1. **LLM 上下文上限**：大仓库 manifest 大，prompt 只能注入"被引用文件全文 + 其余清单"。复杂系统仍受单次生成窗口限制 → L3 解决。
2. **"看懂既有代码"的深度**：L2 是"把文件给 AI 看"，不是"让 AI 理解整个系统架构"。系统级重构（跨模块影响分析）需要 L3+ 的架构理解能力。
3. **代码风格一致性**：靠 prompt 指令约束（"保持现有风格"），无自动 lint/格式化门——可后续加。
4. **existing_path 的权限**：白名单限制在 AIPLAT_HOME 内，跨目录导入需管理员确认（复用 `require_admin_access` 模式）。
5. **重写语义误用（评审指出）**：用户误以为"只加几行"而接受重写结果 → 已在 §3.4 用前端红字警告 + prompt 行为指令 + 接口保留验收三层缓解；仍存残余风险（AI 无法 100% 保留所有细节），L3 diff 合并彻底解决。**这是 L2 上线前必须让用户认知到的边界。**
6. **测试真空期（评审指出）**：老项目无测试/依赖缺失导致 real_pytest 卡死 → §3.8 的 tests/ 检测 + skip_pytest_gate 逃生 + pre-check 依赖预检缓解；estimated 通过率可信度低于 real_pytest，需在 PRD 中显式展示估算原因。
