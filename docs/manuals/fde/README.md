# FDE 现场交付体系 — 文档导航

**FDE**（Field Deployment Engineer）是 aiPlat 的核心用户角色——负责到客户现场完成 AI 系统交付。

### 你是谁？选文档

| 我是… | 看这篇 | 5分钟能上手 | 
|------|------|:---:|
| **第一天加入，完全不知道怎么用** | [01 - 快速入门](./01-fde-quickstart.md) | ✅ |
| **我要从零交付一个全新客户域** | [06 - 标准交付 SOP](./06-sop-domain-delivery.md) | ✅ |
| **日常交付客户项目** | [02 - 交付操作手册](./02-fde-delivery.md) | ✅ |
| **需要理解完整交付方法论** | [05 - 实施流程](./05-fde-implementation-process.md) | — |
| **已交付项目需要维护监控** | [03 - 运维与自演进](./03-fde-operations.md) | ✅ |
| **我要扩展系统（创建Agent/Workflow）** | [04 - 管理与扩展](./04-fde-admin.md) | — |

### 阅读路线图

```
新人入职          日常交付           交付后            系统扩展
    │                │                 │                  │
    ▼                ▼                 ▼                  ▼
┌──────────┐   ┌──────────┐    ┌──────────┐       ┌──────────┐
│ 快速入门  │→  │ 交付操作  │ →  │ 运维自演进 │       │ 管理与扩展 │
│ (5分钟)  │   │ (核心手册) │    │ (持续维护) │       │ (Agent等) │
└──────────┘   └──────────┘    └──────────┘       └──────────┘
```

以上 4 篇是**操作流程**，按角色从入门到日常交付到运维到扩展。

[05 - 实施流程](./05-fde-implementation-process.md) 是**方法论参考**——角色定义、输入输出契约、验收标准、质量门。适合 PM 和 FDE 负责人制定交付计划时查阅，不是操作手册。
```

### 系统访问

| 服务 | 地址 |
|------|------|
| FDE 工作台（前端） | `http://localhost:5173/diagnostics` → FDE Dashboard |
| 平台 API | `http://localhost:8003/api/platform/apps/fde/` |
| Core API | `http://localhost:8003/api/platform/apps/fde/` |

### 相关文档

- [交付手册模板](../fde/fde-delivery-manual.md) — 交付后自动生成的客户验收文档
- [输入输出文档模板](./templates/) — 10 个标准文档模板（客户档案/诊断报告/签收单等）
- [标书审查实例](./examples/bid-review/delivery-manual.md) — 投标场景实操参考
- [知识管理手册](../knowledge-management.md) — 知识库反馈闭环
- [本体引擎手册](../ontology.md) — 域本体与 FDE 集成
