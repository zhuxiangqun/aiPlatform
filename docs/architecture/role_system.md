# aiPlatform 角色体系完整定义

**版本**: 1.0  
**日期**: 2026-07-01  
**原则**: 能做决策 ≠ 应该做决策。战略定方向(人)、Agent 做执行(系统)、半自动做辅助(人+AI)。

---

## 一、角色分类总览

| # | 角色 | 类型 | 分类依据 |
|---|------|:---:|------|
| 1 | CEO | 纯 Human | 战略决策需人类直觉和责任感 | <!-- 设计草案，当前由 admin 合并覆盖 --> |
| 2 | CFO | 纯 Human | 投入产出判断需人类权衡 | <!-- 设计草案，当前由 admin 合并覆盖 --> |
| 3 | PM | 纯 Human | 产品方向需人类同理心 | <!-- 设计草案，当前由 admin 合并覆盖 --> |
| 4 | 业务负责人 | **半自动 Human+Service** | 人设 KPI，系统服务自追踪预警 |
| 5 | 技术负责人 | **半自动 Human+Service** | 人做关键决策，系统服务日常调优 |
| 6 | 审批人 | 纯 Human | 高风险确认需法律责任 |
| 7 | FDE | 纯 Human | 客户沟通需人类交互 |
| 8 | BDE | 纯 Human | 代码开发需人类创造力 |
| 9 | 架构师 | 纯 Human | 技术决策需人类经验 |
| 10 | ⚡ 员工 | **纯 Agent** | 重复性任务完全可自动化 |
| 11 | 🛡️ 保安 | **纯 Agent** | 安全防御完全可自动化 |
| 12 | 🔍 顾问 | **纯 Agent** | 学习优化完全可自动化 |
| 13 | 🎯 协调员 | **纯 Agent** | 目标调度完全可自动化 |
| 14 | 终端用户 | 纯 Human | 使用 AI 的是人不是 AI |

---

## 二、纯 Human 角色（8 个）

**共性**: 需要人类特有的能力——战略直觉、法律责任感、客户信任关系、创造力。技术上可以自动化但**不应该**自动化。

### 2.1 👔 CEO

> **设计草案**：CEO 角色当前未作为独立角色实现。其职能（战略决策、KPI 审查）由 `admin` 角色合并覆盖。ValueDashboard 的 CEO 视角 Tab 为设计预留，未实现。

| 维度 | 说明 |
|------|------|
| **职责** | 判断 AI 投资是否推动公司核心战略目标 |
| **边界** | 只看价值不看技术细节。不操作任何系统配置 |
| **关注指标** | 总价值(¥) + 目标达成率(%) + 价值构成 |
| **频率** | 月度 |
| **入口** | `ValueDashboard` [CEO 视角] Tab |
| **操作** | 纯查看。发现偏离 → 通知业务负责人 |
| **为何不 Agent 化** | 战略方向判断需要人类对市场、竞争、组织的综合直觉，AI 可以提供数据但不应代替决策 |

### 2.2 💰 CFO

> **设计草案**：CFO 角色当前未作为独立角色实现。其职能（成本核算、ROI 分析）由 `admin` 角色合并覆盖。ValueDashboard 的 CFO 视角 Tab 为设计预留，未实现。

| 维度 | 说明 |
|------|------|
| **职责** | 核算 AI 成本和 ROI |
| **边界** | 只看财务指标。不参与 Agent 配置 |
| **关注指标** | AI 推理成本(¥) + 人工节省(¥) + ROI 比率 |
| **频率** | 月度 |
| **入口** | `ValueDashboard` [CFO 视角] Tab |
| **操作** | 查看 → 预算决策 → 通知技术负责人 |
| **为何不 Agent 化** | 预算分配涉及跨部门权衡和战略优先级，AI 无法替代 |

### 2.3 📊 PM

> **设计草案**：PM 角色当前未作为独立角色实现。其职能（产品质量追踪、用户满意度）由 `admin` 角色合并覆盖。ValueDashboard 的 PM 视角 Tab 为设计预留，未实现。

| 维度 | 说明 |
|------|------|
| **职责** | 追踪 Agent 质量和使用效果 |
| **边界** | 关注产品指标和用户体验。不配置底层系统 |
| **关注指标** | 完成率(%) + 满意度(NPS) + 安全拦截数 |
| **频率** | 周度 |
| **入口** | `ValueDashboard` [PM 视角] Tab |
| **操作** | 查看 → 发现质量下滑 → 通知技术负责人 |
| **为何不 Agent 化** | 产品方向判断需要人类对用户痛点和市场趋势的理解 |

### 2.4 ✅ 审批人

| 维度 | 说明 |
|------|------|
| **职责** | 对 AI 发起的高风险操作做最终人工确认 |
| **边界** | 只审批高风险操作。不主动发起任何任务 |
| **关注指标** | 待审批队列长度 + 审批通过率 |
| **频率** | 实时 |
| **入口** | `ApprovalCenter` |
| **操作** | 收到通知 → 查看详情 → 同意/拒绝 |
| **为何不 Agent 化** | 高风险操作的法律责任必须由人类承担。Agent 可以建议但不能代替签字 |

### 2.5 🚀 FDE (Forward Deployed Engineer)

| 维度 | 说明 |
|------|------|
| **职责** | 把平台能力部署到客户业务场景，打通最后一公里 |
| **边界** | 项目制角色——客户从 0 到 1 时存在，稳定后移交退出 |
| **关注指标** | KPI 是否在达成 + 客户是否满意 |
| **频率** | 周/月（项目期内） |
| **入口** | 贯穿: `OnboardingWizard` → `EnterpriseKPIs` → `RoleManager` → `StrategyControl` → `ValueDashboard` → `UserWorkbench` |
| **操作流程** | 与客户对齐 → 7 步入驻 → 对接系统 → 定制 Agent → 设 KPI → 灰度上线 → 验证 → 移交 |
| **为何不 Agent 化** | 客户沟通、需求理解、信任建立是人类关系的核心。工具可以辅助但无法替代 |

### 2.5a ⚙️ Operator（运维）

| 维度 | 说明 |
|------|------|
| **职责** | 系统日常运维——监控、告警响应、故障恢复、基础设施维护 |
| **边界** | 只管理运行态。不创建 Agent/Skill，不碰业务指标（value）和终端使用（user） |
| **关注指标** | 节点健康 + 服务可用性 + 告警响应时间 |
| **频率** | 日常 |
| **入口** | `diagnostics` → `infra` → `platform` |
| **操作流程** | 监控大盘 → 告警响应 → 故障排查 → 审计回溯 |
| **为何不 Agent 化** | 故障根因分析需要人类对系统拓扑和业务上下文的综合判断 |

> **API/UI 分层设计**：operator 拥有 Agent/Skill 的 API 层只读和执行权限（用于脚本巡检和自动化运维），但前端不暴露 core 菜单组的 Agent/Skill/Tool 管理 UI。此设计符合 operator "只管运行态、不创建配置" 的职责边界。运行态监控通过 diagnostics 面板提供。

### 2.6 ⚙️ BDE (Back-End Developer)

| 维度 | 说明 |
|------|------|
| **职责** | 开发后端 API、数据模型、业务逻辑 |
| **边界** | 持续角色——负责系统的技术实现 |
| **关注指标** | 代码质量 + 测试通过率 + API 响应时间 |
| **频率** | 持续 |
| **入口** | IDE + pytest + Git |
| **操作** | 编写代码 → 测试 → 提交 → 上线 |
| **为何不 Agent 化** | 代码开发需要人类创造力。Agent 可以写代码片段但不能替代系统设计 |

### 2.7 🏗️ 架构师

| 维度 | 说明 |
|------|------|
| **职责** | 定义系统边界、审核技术方案、确保架构一致性 |
| **边界** | 重大决策时介入——不参与日常开发 |
| **关注指标** | 架构违规数 + 技术债务数 |
| **频率** | 重大决策时 |
| **入口** | 技术评审会 + `docs/architecture/` |
| **操作** | 审核方案 → 提出修正 → 决策 → 归档 |
| **为何不 Agent 化** | 架构决策需要多年经验积累和跨系统全局视野 |

### 2.8 👤 终端用户

| 维度 | 说明 |
|------|------|
| **职责** | 使用 AI 完成日常工作 |
| **边界** | 只使用不配置——不接触管理后台 |
| **关注指标** | 任务完成速度 + 结果准确性 |
| **频率** | 日常 |
| **入口** | `UserWorkbench` |
| **操作** | 选择能力 → 提交任务 → 看进度 → 查看结果 → 👍/👎 |
| **为何不 Agent 化** | 使用 AI 的是人。Agent 是工具，用户是使用者 |

---

## 三、半自动 Human+Service 角色（2 个）

**共性**: 关键决策需要人类判断，但监控、预警、常规调优可以由系统服务自动完成。KPIAgent 和 StrategyAgent 是 Python 系统服务（由 EvolutionEngine / API 调用），不是 AGENT.md 驱动的 Agent（不通过 ReActLoop 执行）。

### 3.1 📋 业务负责人 + KPIAgent

| 维度 | 说明 |
|------|------|
| **Human 职责** | 定义 KPI 目标(如"审批周期 5天→2天")、决定商业优先级 |
| **Agent 职责** | 自动追踪进度、检测偏离、发出预警、建议调整策略 |
| **边界** | Agent 只建议不执行——最终决策权始终在人手里 |
| **频率** | Human: 月度设目标 / Agent: 每日自动追踪 |
| **Human 入口** | `EnterpriseKPIs` + `BusinessGoals` |
| **系统服务** | `KPIAgent` (core/harness/agents/kpi_agent.py) — Python 服务，非 Agent.md 驱动 |

#### KPIAgent 设计（系统服务）

```python
class KPIAgent:
    """业务负责人的 AI 助手"""

    async def monitor(self, goal_id: str) -> Alert:
        """每日自动追踪目标进度，偏离时发出预警"""
        goal = await goal_tracker.get(goal_id)
        if goal.progress_pct < 0.7 and goal.current_value > goal.target_value * 1.2:
            return Alert(level="warning",
                message=f"{goal.description} 进度仅 {goal.progress_pct:.0%}，建议调整策略",
                suggested_action="将对应 Agent 切换为提速模式")
        return Alert(level="ok")

    async def suggest_strategy(self, goal_id: str) -> StrategySuggestion:
        """根据历史达成路径自动推荐最佳策略"""
        # 分析过去 3 个月的目标达成路径 → 推荐
        return StrategySuggestion(mode="speed", confidence=0.85)
```

| 接线点 | 触发 | 动作 |
|--------|------|------|
| `EvolutionEngine` Step 12 | 月度 | 检查所有 KPI → 偏离时 EventBus 通知 |
| `StrategyControl` 页面 | 用户打开时 | 展示 `suggest_strategy()` 建议 |
| `BusinessGoals` 页面 | 自动 | 实时显示 on_track/at_risk/behind 状态 |

### 3.2 🛠️ 技术负责人 + StrategyAgent

| 维度 | 说明 |
|------|------|
| **Human 职责** | 关键决策（回滚 Skill、切换大架构）、审核 AI 建议 |
| **Agent 职责** | 日常参数微调、自动响应告警、灰度放量 |
| **边界** | Agent 可执行常规调参(如调整 max_steps)，但涉及模型切换或 Skill 回滚必须人审批 |
| **频率** | Human: 关键决策时 / Agent: 日常自动 |
| **Human 入口** | `RoleManager` + `StrategyControl` |
| **系统服务** | `GoalAwareRouter` (已实现) + `CircuitBreaker` (已实现) + `ToolDriftDetector` (已实现) — 不通过 ReActLoop 执行 |

#### StrategyAgent 设计（系统服务）

```python
class StrategyAgent:
    """技术负责人的 AI 助手"""

    async def auto_adjust(self, goal_id: str) -> AdjustResult:
        """根据目标状态自动微调参数（仅限安全范围内的调整）"""
        status = await goal_tracker.get_status_for_routing()
        result = AdjustResult()

        if status["has_lagging_goal"]:
            result.adjustments.append(
                {"param": "max_steps", "from": 15, "to": 10, "reason": "目标落后，减少冗余步骤"})
        if status["security_incidents"] > 3:
            result.adjustments.append(
                {"param": "force_hitl_external", "from": False, "to": True, "reason": "安全事件增多"})

        # 自动执行安全范围内的调整
        for adj in result.adjustments:
            await self._apply_adjustment(adj)
        return result
```

| 接线点 | 触发 | 动作 |
|--------|------|------|
| `DynamicRouter._decide_next` | 每次调度前 | `GoalAwareRouter.adjust()` |
| `EvolutionEngine` Step 7 | 夜间 | `ToolDriftDetector.detect_all()` |
| `sys_tool_call` 返回后 | 实时 | `record_call()` + `_check_realtime()` |

---

## 四、纯 Agent 角色（4 个）

**共性**: 任务确定、边界清晰、不需要人类判断。系统自动运行，零人工介入。

### 4.1 ⚡ 员工 (Employee)

| 维度 | 说明 |
|------|------|
| **职责** | 快速、低成本完成重复性确定任务 |
| **技术实现** | `ReActLoop` + 轻量模型(qwen2.5-coder:7b) + 确定性工具 |
| **优化目标** | 最大化效率价值(efficiency_saved) |
| **触发** | 用户通过 `UserWorkbench` 提交任务 / Pipeline 自动调度 |
| **管理入口** | `RoleManager` 分配 Agent 到此角色 |
| **为何是 Agent** | 合同 OCR、字段提取、报表生成——任务确定、边界清晰、可自动执行 |
| **核心组件** | `ReActLoop.run()` + `sys_tool_call()` + `PipelineEngine.run()` |

### 4.2 🛡️ 保安 (Guard)

| 维度 | 说明 |
|------|------|
| **职责** | 防御攻击、检测异常、拦截风险 |
| **技术实现** | `ImmuneMemory` + `CircuitBreaker` + `ApprovalGate` + `ToolDriftDetector` |
| **优化目标** | 最大化安全价值(safety_value) — 每拦截一次攻击 = 避免 ¥50,000 |
| **触发** | 每次 `sys_tool_call` 自动运行 / 每次 `sys_llm_generate` 入口扫描 |
| **管理入口** | `RoleManager` 查看攻击记忆数 |
| **为何是 Agent** | 安全扫描必须实时、无延迟、不依赖人类判断——速度决定防御有效性 |
| **核心组件** | `ImmuneMemory.scan()` + `CircuitBreaker` + `_check_realtime()` |

### 4.3 🔍 顾问 (Advisor)

| 维度 | 说明 |
|------|------|
| **职责** | 从成功/失败中学习、生成 Skill、持续优化 |
| **技术实现** | `SkillOpt` 双通道 + `AutoLearner` + `PatternAccumulator` + `SkillSimulator` |
| **优化目标** | 最大化质量价值(quality_value) + 创新价值(innovation_value) |
| **触发** | `_try_feed_learning_pipeline` 每次交互后 / EvolutionEngine Step 2/8/10 |
| **管理入口** | `RoleManager` 查看草稿数 |
| **为何是 Agent** | 模式识别、数据驱动优化——人类无法从几千条轨迹中找出模式 |
| **核心组件** | `analyze_failure()` + `analyze_success()` + `SkillSimulator.validate() → PCP 审批管道 → SkillRegistry` |

### 4.4 🎯 协调员 (Orchestrator)

| 维度 | 说明 |
|------|------|
| **职责** | 根据业务目标动态调度员工/保安/顾问的资源分配和策略 |
| **技术实现** | `BusinessGoalTracker` + `GoalAwareRouter` + `DynamicRouter` |
| **优化目标** | 最大化目标达成率(progress_pct → 100%) |
| **触发** | `DynamicRouter._decide_next` 每次调度前 / EvolutionEngine Step 12 |
| **管理入口** | `StrategyControl` 查看当前策略 |
| **为何是 Agent** | 目标感知调度需要实时读取 KPI 状态并注入决策——人类无法在每次 Agent 调度时介入 |
| **核心组件** | `GoalAwareRouter.adjust()` + `DynamicRouter._decide_next` 目标注入 |

---

## 五、角色协作全景

```
                        企业决策层 (纯 Human)
              ┌─────────────┼─────────────┐
             CEO            CFO            PM
              │              │              │
              └──────────────┼──────────────┘
                             │ (战略指示)
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
         业务负责人        技术负责人       审批人
        (系统服务)        (系统服务)        (纯Human)
              │              │              │
    ┌─────────┼──────────────┼──────────────┼─────────┐
    │         │              │              │         │
    ▼         ▼              ▼              ▼         ▼
  员工      保安           顾问          协调员     终端用户
(纯Agent) (纯Agent)     (纯Agent)     (纯Agent)   (纯Human)
    │         │              │              │         │
    └─────────┴──────────────┴──────────────┴─────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            FDE        BDE       架构师
         (纯Human)  (纯Human)  (纯Human)
```

---

## 六、Agent 化判断标准

将角色转化为 Agent 必须同时满足以下**全部 4 条**：

| # | 标准 | CEO | CFO | PM | 业务 | 技术 | 审批 | FDE | BDE | 架构 | 员工 | 保安 | 顾问 | 协调 | 用户 |
|---|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **任务边界清晰** | ✗ | ✗ | ✗ | △ | △ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 2 | **不需人类判断** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✗ |
| 3 | **不需承担法律责任** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4 | **不需人类创造力** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **结论** | **人** | **人** | **人** | **S** | **S** | **人** | **人** | **人** | **人** | **A** | **A** | **A** | **A** | **人** |

> ✓ = 满足, ✗ = 不满足, △ = 部分满足, A = Agent (纯 Agent), S = 系统服务 (半自动)

---

## 七、系统入口速查

| 角色 | 画面入口 | 频率 |
|------|---------|:---:|
| CEO | `ValueDashboard` [CEO Tab] | 月度 |
| CFO | `ValueDashboard` [CFO Tab] | 月度 |
| PM | `ValueDashboard` [PM Tab] | 周度 |
| 业务负责人 | `EnterpriseKPIs` + `BusinessGoals` | 周度 |
| 技术负责人 | `RoleManager` + `StrategyControl` | 日常 |
| 审批人 | `ApprovalCenter` | 实时 |
| FDE | `OnboardingWizard` → ... → `UserWorkbench` | 项目制 |
| BDE | IDE + pytest + Git | 持续 |
| 架构师 | 技术评审 + `docs/architecture/` | 重大决策时 |
| ⚡ 员工 | 系统自动 | 每次任务 |
| 🛡️ 保安 | 系统自动 | 每次调用 |
| 🔍 顾问 | 系统自动 | 每次交互 |
| 🎯 协调员 | 系统自动 | 每次调度 |
| 终端用户 | `UserWorkbench` | 日常 |
| 新客户 | `OnboardingWizard` | 一次性 |

> 参见：[私有控制平面 — aiPlat 四层防御体系](articles/private-control-plane.md) 了解更多 PolicyGate/ApprovalGate 的设计细节。
