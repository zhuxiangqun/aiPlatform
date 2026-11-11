# DOCUMENT_SYSTEM v2.4 — Batch 0：文档宪法自检

> 状态：Completed（2026-11-11），先于 954 份文档迁移。
> 来源：对 v2.3/v2.4 的只读核验；只列修订，不改现有文档。

## 1. 结论

v2.4 的结构（目录、类型、角色边界）已成形，但**文档宪法自身仍不自洽**：

```text
数字声明失效
引用失效
章节编号/计数错误
规则与 CI 脱节
```

因此 v2.4 不能只做目录迁移，必须先做 Batch 0。

## 2. P0：数字与引用必须可执行

### B0-01 恢复数字声明治理

v2.4 当前缺少 v2.3 的“数字声明治理”章节。必须恢复，并改为：

| 声明项 | 当前值 | 验证命令 | 最后验证 |
|---|---|---|---|
| Engine Skills | 以命令为准 | `find aiPlat-core/skills -name SKILL.md | wc -l` | 2026-11-11 |
| HookPhase | 以命令为准 | grep HookPhase 枚举 | 2026-11-11 |
| Arch Guard 规则 | 以命令为准 | `grep -c '^  - id:' aiPlat-core/core/management/arch_guard_rules.yaml` | 2026-11-11 |
| 本体引擎模块 | 以命令为准 | `ls aiPlat-core/core/harness/ontology_engine/*.py | wc -l` | 2026-11-11 |
| 本体引擎行数 | 以命令为准 | `wc -l aiPlat-core/core/harness/ontology_engine/*.py` | 2026-11-11 |
| docs 一级目录数 | 以命令为准 | `find docs -maxdepth 1 -type d | wc -l` | 2026-11-11 |

规则：

- 数字不写死，写“当前值 + 验证命令 + 最后验证日期”；
- 验证命令返回空或失败 → 阻断；
- CI 不能只“检测变化不阻断”。

### B0-02 修正引用路径

- `engine/skills/*/SKILL.md` → `aiPlat-core/skills/*/SKILL.md`
- `hook_manager.py` → `aiPlat-core/core/harness/infrastructure/hooks/hook_manager.py`
- `arch_guard_rules.yaml` → `aiPlat-core/core/management/arch_guard_rules.yaml`
- `ontology_engine/*.py` → `aiPlat-core/core/harness/ontology_engine/*.py`
- `DEPLOYMENT.md` / `TESTING_GUIDE.md` 示例 → 当前 `docs/manuals/` 实际文件
- “根 CLAUDE.md §16 已知债务” → 指向真实章节或删除

### B0-03 新增自检脚本

新增：

```text
scripts/verify_document_system.py
```

检查：

- 章节编号重复；
- 数字声明有验证命令；
- 验证命令执行成功；
- 引用文件存在；
- “五个/六个”等计数与表格一致；
- 已知问题不指向已删除文件。

验收：

```text
python3 scripts/verify_document_system.py → 0
```

## 3. P1：恢复被删掉的章节

### B0-04 恢复六个 CLAUDE.md 定位

标题从“五个 CLAUDE.md”改为“六个 CLAUDE.md”：

```text
根 + aiPlat-core + aiPlat-infra + aiPlat-platform + aiPlat-management + aiPlat-app
```

### B0-05 恢复已知问题并清理僵尸项

- `docs/index.md` 已合并到 `docs/README.md`；
- 删除“docs/index.md 断链已修复”僵尸条目；
- 保留真实已知问题，标注日期和 owner。

### B0-06 修复章节编号

- 原 `§2.2 骨架规则`、`§2.3 设计时效`、`§2.2 边界规则` 的重复编号；
- 统一为 2.1 / 2.2 / 2.3 / 2.4；
- 清理 §2.3 末尾孤立 `|` 残片。

### B0-07 修复规则与执行脱节

骨架过期写“自动归档或删除”，但 CI 只告警：

- 要么提供自动脚本；
- 要么改为“告警 + 人工确认后归档”；
- 不能保留“自动”描述却无自动机制。

## 4. 验收标准

```text
1. 数字声明全部有可执行命令
2. 命令执行非空且不报错
3. 所有引用文件存在
4. 六个 CLAUDE.md 计数一致
5. docs/index.md 僵尸条目不存
6. 章节编号无重复
7. verify_document_system.py 通过
```

## 5. 不在 Batch 0 范围

- 954 份文档迁移；
- 目录搬迁；
- 内容重写；
- 业务程序修改。

这些在 Batch 1+ 处理。
