# FDE POC 标准化操作手册

> FDE 到客户现场后, 1-3 天内完成从"客户模糊需求"到"一个可 demo 的 AI 工作系统"的全过程。

last_synced: 2026-07-07
status: published
owner: fde

---

## 0. POC 是什么

POC (Proof of Concept / 概念验证) 是 FDE 在客户现场展示 aiPlat 价值的最快方式。
**不要追求生产级完整度**——追求速度 + 客户真实数据的即时效果。

## 1. 时间预算

| 场景 | 总时间 | 适用条件 |
|------|:--:|------|
| **轻 POC**（只用一个 Skill） | **4-6h** | 客户数据简单, 只需知识问答演示 |
| **标准 POC**（完整 Pipeline） | **1-2 天** | 需要多 Agent 协作 + 数据注入 |
| **深度 POC**（多 Agent + 定制） | **3-5 天** | 客户需要深度定制 Skill |

## 2. 标准化流程

### 阶段 0：行前准备（出发前 1h）

| 操作 | 工具 | 耗时 |
|------|------|:--:|
| 打包离线部署包 | FDE Dashboard → Tab 2 部署管理 → 点击"打包" | 5min |
| 确认客户行业 | 查看客户 CRM 记录 | 5min |
| 下载对应行业 POC 模板 | `~/.aiplat/profiles/poc-{industry}.yaml` | 1min |
| 准备 USB/硬盘拷贝离线包 | `aiplat-offline-*.tar.gz` 复制到移动存储 | 10min |

### 阶段 1：现场诊断（到现场后 2h）

| 操作 | 工具 | 产出 |
|------|------|------|
| 与客户方关键人开会 | 了解痛点、数据源、现有系统 | 会议纪要 |
| 填写诊断表单 | FDE Dashboard → Tab 3 客户诊断 → 填写 9 字段 | — |
| 提交诊断 | 点击"提交诊断"→ AI 生成报告 | 诊断报告（含 Top 3 机会） |

### 阶段 2：快速部署（30min）

| 操作 | 命令/工具 |
|------|------|
| 解包 | `tar -xzf aiplat-offline-*.tar.gz` |
| 安装 | `cd aiplat-offline && ./install.sh` |
| 加载行业 POC Profile | FDE Dashboard → Tab 6 POC 工具箱 → 点击对应行业按钮 |
| 验证 | `curl localhost:8002/api/core/health` |

### 阶段 3：数据注入（1-3h）

| 操作 | 工具 | 说明 |
|------|------|------|
| 收集客户数据文件 | 向客户要 Excel/CSV/PDF/TXT | 至少 3-5 个文件 |
| 批量注入 | FDE Dashboard → Tab 6 → 选择文件 → 点击"执行数据注入" | 后台调 `poc_data_inject` Skill |
| 验证注入结果 | 查看进度条 → 确认 records > 0 | 注入失败的文件在 errors 中显示 |
| 快速检索验证 | MaterialsChat 或 Agent 对话中问"我们X数据如何？" | AI 应引用注入的数据 |

### 阶段 4：POC 搭建（2-4h）

| 操作 | 工具 |
|------|------|
| 打开 Agent 管理 | 管理端 → Core → Agent 管理 |
| 选择 POC Profile | 查看 `poc-{industry}` 下预设的 Agent |
| 用 AI 自动填充配置 | 在 Agent 编辑页 → 输入角色描述 → AI 自动生成 AGENT.md |
| 可视化装配 Pipeline | WorkflowCanvas → 拖拽节点 → 连接 Agent → 保存 |
| 测试 Pipeline | 运行 Pipeline → 确认产出 |

### 阶段 5：现场 Demo（1h）

| 步骤 | 话术/操作 |
|:--:|------|
| 1. 介绍 aiPlat | "这是 aiPlat, 一个能自己进化+上前线的 AI 平台" |
| 2. 演示知识问答 | 用客户自己的数据问一个问题 |
| 3. 演示 Pipeline | 跑一遍完整 Agent 流程 |
| 4. 让客户上手 | 让客户自己问一个问题 |
| 5. 总结 | "今天用了您的真实数据, 您看哪些场景我们继续深入?" |

### 阶段 6：收尾（30min）

| 操作 | 工具 |
|------|------|
| 提交现场反馈 | FDE Dashboard → Tab 5 现场反馈 → 填写问题/环境/方案 |
| 记录客户意向 | 在反馈中标注客户优先级 |
| 同步到总部 | 联网后运行 `sync-field-feedback.sh` 或自动同步 |

## 3. 关键验收清单

- [ ] 客户真实数据注入成功（`records > 0`）
- [ ] AI 回答引用了客户数据（非通用知识）
- [ ] Agent Pipeline 成功执行一次完整流程
- [ ] 客户现场提了一个问题, AI 即时回答
- [ ] 现场反馈已提交

## 4. 常见问题处理

| 问题 | 解决方案 |
|------|------|
| 客户数据文件过大 (>50MB Excel) | handler.py 自动截断 max_rows=500, 不影响 Demo 效果 |
| 客户环境无网络 | 离线包已自带依赖, 无需网络 |
| OCR 解析慢 (>30s/页) | 先注入 CSV/TXT 文件做快速 Demo, PDF OCR 后台跑 |
| Agent 回答不准确 | 检查 POC Profile 是否正确加载 → 重新注入数据 → 调整 Agent prompt |
