# 审查报告生成器（持续交付）

本目录用于把结构化审查项 `reports/audit_findings.json` **自动生成**为可交付的 Word 报告：
- 输出：`reports/aiPlat_设计文档与实现一致性审查报告.docx`
- 变更日志：`reports/audit_changelog.md`

## 使用方式

在仓库根目录执行：

```bash
cd tools/audit-report
npm install
npm run audit:docx
```

生成成功后会覆盖更新：
`reports/aiPlat_设计文档与实现一致性审查报告.docx`

## 工作流规则（必须遵守）
1. `reports/audit_findings.json` 是唯一结构化事实源（禁止手工编辑 docx 来“改结论”）。
2. 每次修复/调整判定后，必须同时完成：
   - 更新 JSON 对应条目字段（status/fix/verification/updated_at）
   - 在 `reports/audit_changelog.md` 追加一条记录
   - 重新生成 docx（本工具）

