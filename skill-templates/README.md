# Skill Templates（可导入模板）

本目录提供两份“规则型 Skill（SKILL.md）”模板，用于把文章中的 **planner / generator / evaluator** 方法论落地到 aiPlat。

## 模板列表
- `planner-product-spec/`：把简短需求扩展为可交付 spec + tasks + handoff.json  
- `evaluator-webapp-qa/`：对 Web 应用做 QA 评估，输出结构化评分/问题清单（用于闭环迭代）

## 如何导入（手动，不会自动执行）
你可以在管理画面 **应用库 → Skill市场/安装器** 里选择来源类型为：
- 本地目录（path）：指向本目录（或其父目录）并设置 subdir 为 `skill-templates`

或把这两个子目录打包成 zip 走 zip 导入。

