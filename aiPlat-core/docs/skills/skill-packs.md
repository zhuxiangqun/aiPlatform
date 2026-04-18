# Skill Packs（技能包）

本文档描述 **Skill Pack**（技能包）的最小闭环实现：存储模型、API、manifest 规范、以及安装后如何让技能“立即生效”。

> 目标：让一组技能（SKILL.md）可以被打包、发布（publish version）、安装（install）并在 workspace scope 下自动 materialize 成可执行技能。

---

## 现状（As-Is）

### 数据模型（ExecutionStore）

- `skill_packs`：技能包本体（可变，类似“工作区草稿”）
- `skill_pack_versions`：技能包版本快照（publish 时从 pack 的 manifest 固化一份，`(pack_id, version)` 唯一）
- `skill_pack_installs`：安装记录（scope=engine|workspace）

> 代码证据：`core/services/execution_store.py`

---

## API（核心）

统一前缀：`/api/core`

### Skill Pack CRUD

- `GET /skill-packs`
- `POST /skill-packs`
- `GET /skill-packs/{pack_id}`
- `PUT /skill-packs/{pack_id}`
- `DELETE /skill-packs/{pack_id}`

### 发布与版本

- `POST /skill-packs/{pack_id}/publish`（请求体：`{ "version": "0.1.0" }`）
- `GET /skill-packs/{pack_id}/versions`

### 安装（并生效）

- `POST /skill-packs/{pack_id}/install`
  - 请求体示例：
    ```json
    {
      "version": "0.1.0",
      "scope": "workspace",
      "metadata": { "by": "admin" }
    }
    ```
  - 返回：`{ install, applied: [...] }`
    - `applied` 会逐个列出 manifest.skills 的 materialize/enable 结果（enabled / skipped + reason）

- `GET /skill-packs/installs?scope=workspace`

---

## manifest 规范（最小契约）

`manifest` 必须是 object；如果存在 `manifest.skills`，它必须是 array。

### skills 的两种写法（等价）

#### 1) 简写（string 列表）

```json
{
  "skills": ["pack_skill_hello", "pack_skill_search"]
}
```

#### 2) 完整写法（object 列表）

```json
{
  "skills": [
    {
      "id": "pack_skill_hello",
      "display_name": "Hello Skill",
      "category": "general",
      "description": "来自技能包的示例技能",
      "version": "0.1.0",
      "sop_markdown": "# Hello Skill\n\n（这里写 SOP）\n"
    }
  ]
}
```

### 归一化行为（重要）

服务端会将两种写法统一归一为：

```json
{
  "skills": [{ "id": "..." , "...": "..." }]
}
```

并在以下操作前强校验：
- create / update（当更新 manifest 时）
- publish（发布版本前）
- install（安装生效前）

非法输入会返回 HTTP 400。

---

## “安装即生效”（workspace scope）

当 `scope=workspace` 安装时：

1. 读取 manifest（优先 version 快照；否则读取 pack 当前 manifest）
2. 对 `manifest.skills` 中每个 skill：
   - **materialize** 为 workspace 目录化技能：写入 `~/.aiplat/skills/<skill_id>/SKILL.md`
   - 将 skill bridge 到执行层 `SkillRegistry`（确保可执行）
   - `enable`/`restore` 使其处于 enabled 状态

> 注意：如果 skill id 与 engine scope 冲突（reserved），会被跳过并在 `applied` 中返回原因。

---

## 最小建议（To-Be）

下一步建议增强：
- 为 manifest 增加更严格的字段校验（例如 category enum、version semver）
- 支持 “卸载（uninstall）” 与 “install 生效回滚”
- management 前端增加 manifest 模板/表单，减少手写 JSON

