---
purpose: aiPlat 多仓库工作区级 AI 编程规约（兜底）
scope: workspace-root
language: zh-CN
---

# aiPlat 工作区级 AI 编程规约（Workspace Root）

此文件是 **工作区兜底规约**，用于在系统执行链路中自动推断到 workspace root 时仍然能注入/强制基本规则。

如果你的任务明确针对某个仓库，请优先遵守对应仓库根目录的更细化规约：
- 后端：`aiPlat-core/CLAUDE.md`
- 管理端：`aiPlat-management/CLAUDE.md`

---

## 通用强制规则（适用于所有仓库）
1. **不确定先问**：需求/边界不清晰先澄清，列选项与推荐默认方案。
2. **最小改动面**：只改需求相关代码；不顺手重构/格式化/改无关注释。
3. **简单优先**：不引入未要求的新抽象、新依赖、新框架层。
4. **验收闭环**：交付必须包含可验证证据（后端 pytest/py_compile，前端 npm build）。

