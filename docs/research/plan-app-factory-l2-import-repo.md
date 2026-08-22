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
  → { files: [{path, size, lang}], total }
     （供前端展示导入了什么，用户勾选"这次改哪些"）

POST /projects/{project_id}/update-prd
  body: { prd: { ..., modify_files: ["src/auth/login.py"], scope_note: "..." } }
  → 现有端点复用（builder.py:216 已存在）
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

### 3.4 code_generation 的 prompt 注入（关键）

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

## 变更需求
用户要求：在 src/auth/login.py 增加验证码逻辑，保持现有代码风格
```

**注入实现**：在 `pipeline_engine._run_stage_skill` 的 code_generation 分支前，检测 `state.imported_repo` → 读被引用文件 → 拼进 stage 输入。引擎不关心业务（保持 §5.8 边界），只做"读文件→附加到输入"的通用能力。

### 3.5 安全（重点）

| 风险 | 防护 |
|---|---|
| zip-slip 路径穿越 | 解压时校验每个 entry 的解析路径在 import_root 内（`Path.resolve()` 前缀检查） |
| 读取任意路径 | `existing_path` 白名单：只允许 `~/.aiplat/**`、`AIPLAT_HOME/**` 下的目录 |
| 覆盖未要求改的文件 | 部署目录 = imported + 新产物分开管理；`_deploy_result_files` 只写 stage 声明的 `deploy_files_target_dir` |
| 敏感信息（密钥） | manifest 跳过 `.env`/`*.pem`/`secrets/`；注入 prompt 前过滤疑似密钥行 |
| 体积 | zip ≤ 50MB，文件数 ≤ 500，单文件 ≤ 2MB（超出截断为预览） |

### 3.6 回滚

- 导入前状态：`_final_state` 每次变更前自动快照到 `_final_state.bak`（复用现有 `_snapshot` 机制）
- 用户可 `rollback_prd` 回到导入前 PRD
- 部署目录：`imported/` 与 `current/` 分离，`rollback_stage` 不影响 imported

## 4. 前端改动（最小）

| 元素 | 位置 | 说明 |
|---|---|---|
| "导入既有代码"按钮 | `Factory/index.tsx` 项目详情区 | 触发 zip 上传或路径输入 |
| 导入文件列表 | 项目详情新增折叠区 | 展示 manifest，勾选"本次修改"文件 |
| PRD 编辑框提示 | 现有 PRD 编辑 | 提示可引用 `imported/xxx.py` 路径 |

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

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| 后端 `import_repo` + manifest + 安全 | 0.5 天 |
| code_generation prompt 注入 + 引擎通用读文件 | 0.5 天 |
| 回滚/快照 | 0.25 天 |
| 前端（上传/列表/勾选） | 0.25 天 |
| 测试（6-8 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 2 天** |

## 7. 与后续层级的关系

- **L2 做完**：AI 能"看既有代码、改指定文件"——从 1 到 2 可行
- **L3（增量引擎）**：L2 的 prompt 注入验证有效后，加"只重生成受影响文件 + diff 合并"——从 1 到 N
- **L4（多模块编排）**：模块级项目 + API 集成——从 1 到 100 的架构路径

## 8. 风险与开放问题

1. **LLM 上下文上限**：大仓库 manifest 大，prompt 只能注入"被引用文件全文 + 其余清单"。复杂系统仍受单次生成窗口限制 → L3 解决。
2. **"看懂既有代码"的深度**：L2 是"把文件给 AI 看"，不是"让 AI 理解整个系统架构"。系统级重构（跨模块影响分析）需要 L3+ 的架构理解能力。
3. **代码风格一致性**：靠 prompt 指令约束（"保持现有风格"），无自动 lint/格式化门——可后续加。
4. **existing_path 的权限**：白名单限制在 AIPLAT_HOME 内，跨目录导入需管理员确认（复用 `require_admin_access` 模式）。
