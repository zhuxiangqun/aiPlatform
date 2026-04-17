#!/usr/bin/env markdown
# 目录化 Skills（SKILL.md）

> 这里存放 **目录化技能**（面向 Agent Skill / SOP 注入模式），与 `core/apps/skills/`（技能系统引擎代码）区分开。
>
> ⚠️ 更新：为实现“核心能力层（engine）”与“对外应用库（workspace）”严格分离，目录化 Skill 目前按两套来源加载：
> - **引擎内置（engine，仅核心能力层使用）**：`aiPlat-core/core/engine/skills/<skill_id>/SKILL.md`
> - **应用库（workspace，对外/用户可用）**：`~/.aiplat/skills/<skill_id>/SKILL.md`
>
> 本目录 `aiPlat-core/skills/` 作为历史遗留与测试样例保留，不再作为默认扫描路径（除非你通过环境变量显式覆盖）。

## 默认扫描路径

aiPlat-core 的 HTTP Server 启动时，会扫描：
- engine 默认：`<aiPlat-core>/core/engine/skills/`
- workspace 默认：`~/.aiplat/skills/`

可覆盖（建议按 scope 分开配置）：
- `AIPLAT_ENGINE_SKILLS_PATH` / `AIPLAT_ENGINE_SKILLS_PATHS`
- `AIPLAT_WORKSPACE_SKILLS_PATH` / `AIPLAT_WORKSPACE_SKILLS_PATHS`

## 目录结构（约定）

```
skills/
  <skill_name>/
    SKILL.md              # 必须（YAML frontmatter + SOP 正文）
    handler.py            # 可选（自定义处理器/适配器）
    references/           # 可选（参考文档，按需读取）
    scripts/              # 可选（确定性脚本，按需读取/沙箱执行）
```

## 示例
- `skills/hello-skill/`：最小示例（用于验证 discover/match）
