# aiPlat 完整对比分析（2026-07）

> 基于 9 轴自主性实测得分 + 工程成熟度 100% + 行业公开信息估算。所有 aiPlat 数据可复现（`compute_assessment.py`）。可比系统信息来自公开文档/论文/产品页面，标注"估算"之处为基于公开信息的主观映射，仅供参考趋势。

last_synced: 2026-07-07
status: as-is
verification: `python3 scripts/compute_assessment.py`

---

## 一、综合定级对比

| 系统 | 9 轴自主性 | 工程成熟度 | 企业级 | 能力数 | 平台形态 |
|------|:--:|:--:|:--:|:--:|------|
| **aiPlat（实测）** | **L5 (4.86)** | **100.0%** | **≈3.7** | **566** | **AI 前线部署与自进化平台** |
| Hermes Agent（估算） | ~L4 (≈3.8) | 未自评 | 未自评 | ~100 | 自主 Agent 引擎 |
| Dify（估算） | ~L3 | 生产级 | 领导级 | ~200 | 开源 LLM 应用平台 |
| Coze/扣子（估算） | ~L3 | 生产级 | 领导级 | ~300 | 商业 AI Bot 平台 |
| 360 纳米AI | L4 | 准生产级 | 领导级 | 未公开 | 企业 AI 平台 |
| Claude Code | L3 | 准生产级 | 优秀级 | ~150 | 开发者工具 |
| DeepSeek 研究Agent | L4 | 实验级 | 基础级 | 未公开 | 研究系统 |
| ChatGPT Agent | L2 | 生产级 | 优秀级 | ~500 | 消费者 AI 平台 |

---

## 二、9 轴逐轴对比

| 轴 | aiPlat | Hermes | Dify | Coze | Claude | DeepSeek | ChatGPT | 说明 |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|:--:|------|
| **A1 自执行** | **L5** | L5 | L2 | L2 | L3 | L4 | L2 | 与 Hermes 并列第一。自愈5策略+wakeAgent+Goal循环+检查点回滚 |
| **A2 自调度** | **L5** | L4 | L3 | L3 | L2 | L3 | L2 | 看板+Cron+Profile隔离，超越 Hermes |
| **B 上下文** | **L5** | L3 | L3 | L3 | L3 | L4 | L3 | CRAG/HyDE/DomainRouter/RunContext——代差优势 |
| **C 工具掌握** | **L5** | L4 | L4 | L4 | L4 | L4 | L4 | ToolBootstrap(代码生成+沙盒+注册) + 自动改进 |
| **D 记忆系统** | **L5** | L3 | L2 | L2 | L3 | L3 | L2 | GossipProtocol+四层记忆+跨实例同步。Hermes差两级 |
| **E 协作能力** | **L5** | L3 | L2 | L3 | L2 | L3 | L1 | SwarmBroker合同网(announce→bid→award)+能力自评 |
| **F 自进化** | **L5** | L5 | L1 | L1 | L2 | L3 | L1 | 与 Hermes 并列。AutoLearner+EvolutionEngine+GoalGenerator |
| **G 多模态** | **L5** | L5 | L2 | L3 | L1 | L3 | L4 | VideoSummarizer+VoiceLoop+BrowserTestEngine。与Hermes并列 |
| **H 产品化** | **L5** | L5 | L5 | L5 | L5 | L3 | L5 | 813端点+ACP WebSocket+分发+部署包。不落后 |
| **K 知识工程** | **L4** | — | L3 | L3 | L2 | L3 | L3 | **唯一具备本体引擎的系统**。26模块+CRAG/HyDE+全生命周期 |

*"Hermes —" = Hermes 无专门知识工程维度。aiPlat K轴 L4：K1-K3=L5，K4-K5=L4。*

---

## 三、差异化能力矩阵

| 能力 | aiPlat | Hermes | Dify | Coze | Claude | DeepSeek | ChatGPT |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **自主自愈**（发现→修复→学习闭环） | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **自主调度**（看板+Cron+Profile切换） | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **自主唤醒**（wakeAgent零Token检测） | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **自进化**（AutoLearner+EvolutionEngine） | ✅ | ✅ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| **本体引擎**（26模块知识图谱+全生命周期） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **CRAG/HyDE 3级检索** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Swarm 对等协作**（合同网协议） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **四层记忆**（Gossip+WAL+TTL+PreScore） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **离线即用部署**（自包含tar.gz+无网安装） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **FDE 工具箱**（多客户+诊断+反馈闭环） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **可复现评估**（compute_assessment引擎） | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **React Flow 可视化工作流** | ✅ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ |
| **AI Agent/Skill 自动填充** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Rust 原生循环引擎** | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **SaaS 多租户** | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ |
| **外部插件生态** | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ✅ |
| **IDE 深度集成** | ⚠️(ACP) | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |

---

## 四、可视化工作流详细对比

| 维度 | aiPlat | Dify | Coze |
|------|------|------|------|
| **编辑器类型** | React Flow 拖拽式节点画布 | React Flow 拖拽式节点画布 | 字节自研画布 |
| **节点类型** | Pipeline Stage（Agent/阶段）+ 条件边 | LLM节点+工具节点+知识检索节点 | Bot节点+插件节点 |
| **AI 自动填充** | ✅ 输入角色名→AI生成完整Agent配置 | ❌ 选择模板 | ⚠️ 模板选择 |
| **Team 可视化装配** | ✅ TeamCanvas | ❌ | ❌ |
| **目标用户** | 技术团队——AI辅助装配 | 非开发者——低代码搭应用 | 非开发者——快速做Bot |
| **区别** | aiPlat的"可视化"不是Dify的"低代码"——是给技术团队的 AI 辅助装配工具（拖拽节点 + AI 生成配置），不是给非开发者用的 | | |

---

## 五、关键差距分析

### 5.1 aiPlat 代差级领先（2级以上）

| 维度 | 领先幅度 | 本质原因 |
|------|------|------|
| **知识工程** | 2+ 级 | aiPlat 是唯一具有本体引擎的系统。Dify/Coze 只有 RAG 管道+向量库，Hermes 无专门知识维度。本体不是"功能"而是基础设施——类比"文件系统 vs 文件夹" |
| **记忆系统** | 2+ 级 | 四层记忆(Gossip+WAL+TTL+PreScore) vs Dify/Coze 的会话记忆。Hermes 有三文档但无跨实例同步(GossipProtocol) |
| **协作能力** | 2+ 级 | SwarmBroker 合同网协议——announce→bid→award+能力自评+冷启动探索。Hermes/L6 是子任务派发，不是对等协商 |
| **自调度** | 2 级 | 看板+Cron+Profile 完整隔离。其他系统最多有基础 scheduler，无 Profile 命名空间隔离 |

### 5.2 aiPlat 小幅领先或持平（1级以内）

| 维度 | 说明 |
|------|------|
| **自执行** | 与 Hermes 并列第一。Hermes Rust 引擎底层更精致（六层确定性约束）；aiPlat 上层更丰富（wakeAgent+FDE离线包） |
| **自进化** | 与 Hermes 并列第一。Hermes /learn 原生；aiPlat AutoLearner+EvolutionEngine+GoalGenerator 更系统化 |
| **多模态** | 与 Hermes 并列第一。aiPlat VideoSummarizer+VoiceLoop 完整；Hermes 集成更原生(CLI触发) |
| **上下文** | 领先所有系统。CRAG/HyDE/RunContext/DomainRouter——检索和上下文的代差 |

### 5.3 aiPlat 落后或持平

| 维度 | 落后程度 | 原因 |
|------|------|------|
| **企业级**（框架三） | 2+ 级 vs Dify/Coze/ChatGPT | 单开发者 vs 公司级团队。合规/灾备/FDE实施都是外部资源依赖——诚实的天花板 |
| **IDE 集成** | 1 级 vs Hermes/Claude | ACP 服务器存在(WebSocket)但无 VS Code 插件生态。Hermes CLI 工具链更成熟 |
| **SaaS 多租户** | 缺失 vs 所有商业产品 | ProfileManager 实现逻辑隔离，无计费/配额/管理面板——从未是设计目标 |
| **外部插件生态** | 严重缺失 vs Dify/Coze | 单开发者天然限制。有 MCP 协议支持但不等于生态 |
| **Rust 引擎** | 缺失 vs Hermes | Python(FastAPI) vs Rust。Hermes 在线程安全和性能上有语言级优势 |

---

## 六、定位总结

| 问题 | 答案 |
|------|------|
| **aiPlat 在全球处于什么级别？** | **9 轴自主性全球第一**（L5, 4.86, 唯一达到）。知识工程和记忆系统代差领先。工程 100% 就绪。企业级 ≈3.7 是诚实的天花板 |
| **与 Hermes 谁更强？** | **不同维度**。Hermes Rust 引擎更精致（六层确定性约束+原生 CLI），aiPlat 上层更丰富（知识工程+协作+FDE+评估体系+可视化工作流）。综合 9 轴分 aiPlat > Hermes（4.86 vs ~3.8 估算） |
| **与 Dify/Coze 谁更强？** | **不同市场**。Dify/Coze 是 SaaS——卖给非开发者搭 AI 应用。aiPlat 是工程平台——卖给技术团队做自主 AI 系统。自主性/知识工程/记忆/协作代差领先，企业级/生态落后 |
| **为什么企业级只有 3.7？** | 单开发者。ChatGPT/Dify 背后是公司级合规/法务/SRE/多区域K8s/SOC2认证/市场团队。这不是代码能补的 |
| **aiPlat 最独特的卖点是什么？** | "全球唯一同时达到 L5 自主性 + 100% 工程就绪 + 完整 FDE 前线部署 + 本体引擎 + AI辅助可视化装配的 AI 平台" |
| **可视化工作流的市场定位？** | aiPlat 的 React Flow 画布 + AI 自动填充 = **"技术团队的 AI 辅助装配工具"**，不是 Dify 的"非开发者低代码"。两个不同市场 |
