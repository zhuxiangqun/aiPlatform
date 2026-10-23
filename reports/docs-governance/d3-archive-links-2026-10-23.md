# D3 复核 — archive 断链 / 过期快照（2026-10-23）

> 批准：用户「继续」（D2 之后）。方案 §3.3：修链 / 标注失效 / 删除分判。

## 扫描范围

- `docs/archive/**/*.md` 相对 Markdown 链接是否可解析（排除 http/mailto/#）
- 结果：**broken = 1**（仅探针文件）

## 探针分判

| 文件 | 已知问题 | Q1 | Q2 | R6 | 证据 |
|------|----------|----|----|-----|------|
| `docs/archive/doc_full_scan_report.md` | `./ARCHITECTURE_STATUS.md` 不存在 | 无现行操作责任 | 有：历史扫描留存（archive README 已登记） | **修链** + 强化失效说明 | 真源仍在 `aiPlat-core/docs/ARCHITECTURE_STATUS.md`（479 行）；断链≠无留存价值 → **不删** |

处置：文首改为指向 `../../aiPlat-core/docs/ARCHITECTURE_STATUS.md`，并写明原相对链从未落在 archive。

## 其它 archive 文件

相对链接扫描无第二处断链 → 本批 **无额外修链 / 无删除**。  
（根 `reports/` 与其它仓内对 `ARCHITECTURE_STATUS` 的文字引用不在本批路径扫描内。）

## 验收（§3.3）

| 项 | 结果 |
|----|------|
| 探针 R6 类型写明 | **修链**（兼标注失效语境） |
| 删除 | **0** |
| 修链后目标存在 | `test -f aiPlat-core/docs/ARCHITECTURE_STATUS.md` → 是 |
| archive 相对链复扫 | broken **0** |
