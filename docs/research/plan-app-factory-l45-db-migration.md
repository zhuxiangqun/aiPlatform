# L4.5 设计：数据库 schema 变更与迁移编排（AI 改模型 → 数据库自动跟上）

> **状态**：设计文档（2026-08-23，待评审）
> **目标**：L2-L4 让 AI 演进**代码**，但数据库 schema 变更（AI 给 User 模型加了 `verification_code` 字段，数据库没有对应迁移）未编排——部署后代码读新字段直接报错。L4.5 补齐：**检测模型变更 → 生成迁移（up/down）→ 与 L3 merge 审批联动 → 破坏性变更阻断 → 可回滚**。
> **关联**：《plan-app-factory-l4-multi-module.md》§7（L4.5 候选）+ L3 merge_engine（merge 后触发迁移预览）+ L4 cross_module（跨模块字段引用）。

---

## 1. 背景：为什么需要 L4.5

### 真实痛点（L2-L4 的隐性缺口）

| 场景 | 现状 | 后果 |
|---|---|---|
| AI 给 `User` 模型加 `verification_code` 字段并生成新代码 | 代码更新了，**数据库没有对应列** | 部署后 SELECT/INSERT 报 `no such column` |
| AI 把 `status` 字段从 `int` 改成 `str` | 代码按新类型写，DB 还是旧类型 | 运行时类型错乱 |
| AI 删除某个字段 | 旧数据还在该列，新代码不读 | 数据孤儿（相对无害）但表结构陈旧 |

### L4.5 解决什么

1. **Schema 变更检测**：AI 新版本模型定义 vs 旧版本 → 结构化 diff（字段增删改/表增删）
2. **迁移生成**：diff → up/down DDL 自动生成（v1 纯 SQL，不绑定 ORM）
3. **迁移编排**：与 L3 merge 审批联动——merge 通过后自动出现"迁移预览"→ 审批 → 应用 → 记录迁移历史
4. **破坏性变更门禁**：删字段/改类型 → 标记 destructive + 阻断（除非用户显式确认）
5. **回滚**：down 脚本 + 迁移历史（可回退到任意已应用版本）

### L4.5 不做的事（边界）

- ❌ 不做 ORM 绑定（v1 纯 SQL DDL，Alembic/具体 ORM 适配是后续）
- ❌ 不做数据迁移（只做 schema 迁移；数据回填/清洗是 v2）
- ❌ 不做分布式数据库/多租户 schema 隔离（平台 DBA 职责）

---

## 2. 目标

1. 从模块代码中提取模型 schema（v1：SQLAlchemy Column + Pydantic Field，AST 解析）
2. 新旧 schema 对比 → `SchemaDiff`（added/removed/type_changed columns + tables）
3. diff → 迁移 `up`/`down` DDL 生成（ADD/DROP/ALTER/CREATE/DROP TABLE）
4. **破坏性变更检测**：removed column / type change → `destructive: true`，merge 或迁移应用被阻断
5. merge-apply 后自动触发"迁移预览"→ 用户审批 → 应用 → 历史记录
6. 跨模块字段引用断裂检测（其他模块引用被删除的字段 → 阻断）
7. 回滚（down 应用 + 历史追溯）

---

## 3. 设计方案

### 3.1 数据流

```
L3 merge-apply（代码已应用）
  → SchemaExtractor：提取 merge 后模块代码中的模型定义（AST）
  → 与"变更前"schema 对比（SchemaDiffAnalyzer）
  → 有 diff？
     ├─ 无 → 完成（无迁移）
     └─ 有 → MigrationGenerator 生成 up/down DDL
           → 破坏性检测（removed/type_changed → destructive）
           → 前端迁移预览（up/down SQL + destructive 标记 + 跨模块引用）
           → 用户审批（通过 → 应用迁移 + 记录历史；驳回 → 不应用）
           → 回滚入口（down 应用）
```

### 3.2 API 设计

```
GET  /projects/{project_id}/migrations              # 迁移历史
POST /projects/{project_id}/migration-preview       # merge 后生成迁移预览（触发 schema diff）
POST /projects/{project_id}/migrations/apply        # 应用迁移（body: {migration_ids: [...]}）
POST /projects/{project_id}/migrations/{id}/rollback  # 应用 down 回滚
```

### 3.3 SchemaExtractor（新增，AST 解析模型定义）

```python
def extract_schema(code_files: Dict[str, str]) -> Dict[str, Any]:
    """从代码中提取 {table: {column: {type, nullable, primary}}}. v1: SQLAlchemy + Pydantic."""
    schema = {}
    for rel, content in code_files.items():
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # SQLAlchemy: class X(Base): __tablename__ = "users"; id = Column(Integer, primary_key=True)
                tablename = _find_tablename(node)          # __tablename__ = "..."
                if tablename:
                    schema.setdefault(tablename, {})
                    for stmt in node.body:
                        if isinstance(stmt, ast.Assign) and _is_column(stmt):
                            col = _column_info(stmt)       # {type, nullable, primary}
                            schema[tablename][stmt.targets[0].id] = col
                # Pydantic: class User(BaseModel): id: int; name: str
                elif _is_pydantic(node):
                    schema.setdefault(_snake(node.name), {})
                    for stmt in node.body:
                        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.annotation, ast.Name):
                            schema[_snake(node.name)][stmt.target.id] = {"type": stmt.annotation.id}
    return schema
```

**v1 类型映射**：SQLAlchemy `Integer/String/Boolean/DateTime/Float` → SQL `INTEGER/TEXT/BOOLEAN/DATETIME/FLOAT`；Pydantic `int/str/bool/float/datetime` → 同。

### 3.4 SchemaDiffAnalyzer（新增）

```python
def diff_schema(old: dict, new: dict) -> dict:
    """{added_tables, removed_tables, added_columns: {table: [...]}, removed_columns: {...}, type_changed: {...}}"""
    # 逐表逐列对比，输出四类变更 + destructive 标记
    return {"added_tables": [...], "removed_tables": [...],
            "added_columns": {t: [...]}, "removed_columns": {t: [...]},
            "type_changed": {t: {col: (old_type, new_type)}},
            "destructive": bool(removed_columns or type_changed or removed_tables)}
```

**破坏性定义**（v1）：
- `removed_columns`（删除列）→ destructive（数据仍在，新代码不读——但表结构变化需谨慎）
- `type_changed`（类型变更）→ destructive（数据可能不兼容）
- `removed_tables` → destructive
- `added_columns`/`added_tables` → 非破坏性（可自动应用，仍需审批）

### 3.5 MigrationGenerator（新增）

```python
def generate_migration(diff: dict, project_id: str) -> dict:
    """diff → {id, up_sql, down_sql, destructive, created_at}"""
    up, down = [], []
    for t in diff["added_tables"]:  up.append(f"CREATE TABLE {t} (...);")  # 需列定义
    for t in diff["removed_tables"]: up.append(f"DROP TABLE {t};")
    for t, cols in diff["added_columns"].items():
        for c in cols: up.append(f"ALTER TABLE {t} ADD COLUMN {c};")
    for t, cols in diff["removed_columns"].items():
        for c in cols: up.append(f"ALTER TABLE {t} DROP COLUMN {c};")
    for t, changes in diff["type_changed"].items():
        for c, (old, new) in changes.items(): up.append(f"ALTER TABLE {t} ALTER COLUMN {c} TYPE {new};")
    # down = 反向（ADD↔DROP, TYPE 换回）
    return {"id": f"mig_{uuid}", "up_sql": "\n".join(up), "down_sql": "\n".join(down),
            "destructive": diff["destructive"]}
```

### 3.6 迁移编排（builder 集成）

- **merge_preview 时**：附加 `schema_diff` 摘要（"模型变更：+2 字段 / -1 字段（破坏性）/ 1 类型变更（破坏性）"）——前端 merge 审批可见
- **merge_apply 后**：触发 `migration-preview` → 生成迁移（存 `proj["pending_migrations"]`）→ 前端展示 up/down SQL + destructive 横幅
- **迁移审批**：通过 → 应用（存 `proj["migrations"]` 历史）+ 记录 `applied_at`；驳回 → 保留 pending
- **破坏性门禁**：destructive 迁移**默认阻断**（需用户显式勾选"我了解数据影响，确认应用"）
- **回滚**：`POST migrations/{id}/rollback` → 应用 down + 标记 rolled_back

### 3.7 跨模块字段引用（与 L4 衔接）

- 删除/改类型的字段若被**其他模块**引用（如 billing 读 `user.status`）→ 迁移预览标注"跨模块影响：billing 依赖 user.status"→ 阻断（复用 L4 cross_module 的 entity 证据）
- v1 实现：`cross_module.verify_changed_module_contracts` 的 entity 检测扩展到字段级（类名 + 字段名）

### 3.8 安全与回滚

- 迁移 SQL **仅预览不自动执行**（默认）；应用前二次确认（destructive 必须显式勾选）
- 迁移历史不可变（append-only）；回滚 = 应用 down + 标记，不删除历史
- schema 提取只读代码（AST），不连接真实数据库（v1 无 DB 连接；真实 DB 适配 v2）

---

## 4. 前端改动

| 元素 | 位置 | 说明 |
|---|---|---|
| 迁移预览 | merge 审批后新面板 | up/down SQL 展示（代码块）+ destructive 红横幅 + 跨模块影响标注 + "应用迁移/驳回" |
| 迁移历史 | 项目详情新折叠区 | 迁移列表（id/时间/destructive/状态：applied/rolled_back/pending） |
| 回滚入口 | 迁移历史 | 每条 applied 迁移的"回滚"按钮（确认后应用 down） |

## 5. 验收标准

| # | 验收 | 方法 |
|---|---|---|
| 1 | SchemaExtractor 提取 SQLAlchemy 模型 | 单测：`class User(Base): __tablename__="users"; id=Column(Integer, primary_key=True)` → {users: {id: {...}}} |
| 2 | SchemaExtractor 提取 Pydantic 模型 | 单测：`class User(BaseModel): id: int` → {user: {id: {type: int}}} |
| 3 | 新增字段 diff | 单测：old 无 `verification_code`，new 有 → added_columns 含之，非 destructive |
| 4 | 删除字段 → destructive | 单测：old 有 `secret`，new 无 → removed_columns + destructive=true |
| 5 | 类型变更 → destructive | 单测：`status: int` → `status: str` → type_changed + destructive=true |
| 6 | 迁移 up/down 成对 | 单测：ADD COLUMN 的 down 是 DROP COLUMN；TYPE 变更的 down 是换回 |
| 7 | merge 后迁移预览 | 集成：merge_apply → migration-preview 返回迁移 |
| 8 | 破坏性阻断 | 集成：destructive 迁移 apply 未确认 → 拒绝 |
| 9 | 迁移历史 + 回滚 | 集成：apply → 历史记录 → rollback → down 应用 + 标记 |
| 10 | 无模型变更 → 无迁移 | 单测：diff 为空 → generate_migration 返回 None |
| 11 | 跨模块字段引用阻断 | 集成：billing 读 user.status，迁移删 status → 预览标阻断 |
| 12 | 前端迁移面板 | 手动验证 + tsc/build |

## 6. 工作量

| 模块 | 工作量 |
|---|---|
| SchemaExtractor（AST：SQLAlchemy + Pydantic） | 0.75 天 |
| SchemaDiffAnalyzer（diff + destructive 判定） | 0.5 天 |
| MigrationGenerator（up/down DDL） | 0.5 天 |
| 迁移编排（preview/apply/rollback + 历史） | 0.75 天 |
| 跨模块字段引用（L4 扩展） | 0.5 天 |
| 前端（迁移预览/历史/回滚/破坏性横幅） | 0.75 天 |
| 测试（12 例）+ 契约同步 | 0.5 天 |
| **合计** | **约 4.25 天** |

## 7. 与后续层级的关系

- **L4.5 做完**：AI 改模型 → 数据库自动迁移预案 → 审批应用——代码与 schema 同步演进
- **v2（数据迁移）**：数据回填/清洗/类型转换脚本（不只 schema）
- **v3（ORM 适配）**：Alembic/具体 ORM 迁移集成 + 真实 DB 连接验证

## 8. 风险与开放问题

1. **AST 提取精度**：SQLAlchemy 的 `Column` 参数写法多样（`Column("name", String)` vs `Column(String)`）；v1 支持常见写法，复杂写法（混合/继承/动态表名）漏检 → 标注"模型提取可能不完整，破坏性变更以人工确认兜底"。
2. **真实 DB 验证缺失**：v1 不连真实数据库（迁移 SQL 正确性靠人工审阅 + 测试 DDL 文本）——真实 DB 适配 v2。
3. **并发迁移**：多模块同时迁移的冲突（同一表被两个模块改）→ v1 按 merge 顺序串行 + 历史记录冲突提示。
4. **迁移应用环境**：当前"应用"是记录状态（标记 applied）+ 可选执行（AIPLAT_DB_EXECUTE=true 时对配置的 DB 执行）——默认不自动执行真实 SQL（安全红线）。
5. **与 skip_pytest_gate 关系**：迁移审批独立于测试门禁；即使跳过测试，破坏性迁移仍需显式确认。

---

## 9. 与 L2/L3/L4 的衔接清单

| 既有资产 | L4.5 复用/扩展 |
|---|---|
| L3 merge_engine（previews/decisions） | merge_apply 后自动触发 migration-preview；merge_preview 附加 schema_diff 摘要 |
| L4 cross_module（entity 证据） | 扩展到**字段级**引用（删字段被其他模块读 → 阻断） |
| L4 module_id 体系 | 迁移按模块归属（`module_id` 字段），模块级迁移历史 |
| proj 状态存储 | `pending_migrations` / `migrations`（append-only 历史） |
| 前端 blocked 横幅模式 | destructive 迁移红横幅复用 |
