# E2 复核 — verify_doc_links 扩面（2026-10-23）

> 随用户「继续」执行（E0+E1 后下一批建议 E2+E3）。

## 边界（冻结）

| 级别 | 范围 |
|------|------|
| **fail** | `docs/DOCUMENT_SYSTEM.md`；`docs/**/README.md`（路径不含 `archive`/`_archive`）；`reports/docs-governance/README.md`；`docs/README.md` 已链到的维护区 `.md`（入口一层） |
| **warn** | `docs/**/README.md` 且路径含 `archive`/`_archive` |
| **不做** | 维护区全部正文；archive 升 fail |

## 实现

- `scripts/verify_doc_links.py`：动态收集 fail/warn 集；输出 `fail=N warn=M`。
- 同步声明：`docs/README.md` 门禁表、`DOCUMENT_SYSTEM.md` 校验命令注释。

## 验收

```text
Checked fail=26 warn=1 | broken fail=0 warn=0
✅ All fail-scope links valid
```

（断链清零见 E3。）
