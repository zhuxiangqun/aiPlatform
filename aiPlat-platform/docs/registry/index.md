# registry 模块（Platform Layer 2：服务注册与发现）

## 定位

`registry/` 提供平台级服务注册、配置发现和依赖管理。

## 已实现能力

| 能力 | 状态 |
|------|:--:|
| Skill 注册 / 发现 / 版本管理 | ✅ |
| Agent 注册 / 启用 / 禁用 | ✅ |
| 工具注册（ToolRegistry） | ✅ |
| 技能市场发布工作流（提交→预检→审核） | ✅ |
| Config Registry（配置发现） | ✅ |
| Skill 安装计划（Git/URL 安装） | ✅ |

## 边界

- 注册中心存储元数据（名称/版本/状态），不存储实体代码
- 代码存储和执行在 core 层
- 市场发布流程：提交 → SkillSimulator 预检 → 人工审核 → 发布
