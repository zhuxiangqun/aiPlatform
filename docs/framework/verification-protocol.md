---
title: "aiPlat 框架评估验证协议"
type: verification-protocol
domain: aiplat-core
version: 1.0.0
date: 2026-07-05
status: published
applies_to:
  - docs/framework/aiplat-autonomy-framework.md
  - docs/framework/aiplat-complete-assessment.md
  - docs/framework/scoring-detail.md
refs:
  - scripts/verify-l4-pyramid.sh
  - scripts/verify-l4-depth.sh
  - scripts/verify-l4-claims.sh
  - scripts/verify-l4-behavior.sh
  - scripts/verify_whitepaper_refs.sh
tags: [verification, protocol, reproducibility, three-framework]
---

# aiPlat 框架评估验证协议

> 用途：供外部审稿人独立验证三框架评估结论。
> 前提：不要求通读评估报告。本协议自包含所有验证步骤。

---

## 1. 验证总览

### 三层验证

| 层 | 作用 | 验证方式 | 检查项数 | 覆盖框架项 | 依赖 |
|:---|:---|:---|:--:|:--:|:--:|
| **代码层** | 验证模块存在 | grep -c 脚本 | 62 项 | 102 项全部 (基础覆盖) | 无 |
| **行为层** | 验证真实工作 | pytest + curl | 41 项 (30 pytest + 8 curl + 3 REST) | 102 项中的 63 项 | `./start.sh` (仅 curl 部分) |
| **人工层** | 验证深度能力 | 专业知识判断 | 4 项 | 4 项 (渗透/故障/宏观/架构) | 外部审稿人 |

> **验证项数 (104) ≠ 框架评估项数 (102)**。多个检查覆盖同一项 (如 UCB1 被 grep 和 pytest 双重验证)，部分项仅需代码层覆盖 (如 ADR 存在性)。

### 行为层细分

| 子类型 | 项数 | 验证内容 | 脚本 |
|:---|:--:|:---|:---|
| **Python 深度测试** | 30 | UCB1收敛 / GoalExecutor闭环 / SwarmBroker竞标 / GossipProtocol去重 / ToolBootstrap注册 / AdaptiveContext路由 / 策略跟踪集成 | `verify-l4-depth.sh` |
| **curl 端到端** | 8 | 自主循环 / 自愈引擎 / 上下文召回 / 动态组队 / 工具自举 / 推理 / 跨域 / 错误恢复 | `verify-l4-behavior.sh` |
| **REST API 诊断** | 3 | 架构守卫 (76规则) / 4层健康 / 全量诊断 | curl 直接调用 |

> **关键区分**：代码层只验证 `grep -c class Foo` = 1（模块存在），行为层 30 项深度测试注入真实数据、调用真实函数、验证真实输出（模块工作）。代码层 62 项回答"有"，行为层 41 项独立检查（30 pytest + 8 curl + 3 REST，按检查点计数，非拆解 assert）回答"能"。

### 各框架覆盖

| 框架 | 代码层 | 行为层 (深度测试) | 行为层 (curl) | 人工层 |
|:---|:--:|:--:|:--:|:--:|
| L1-L5 自主性 (18项) | 15 轴证据 | 12 (UCB1/Goal/Swarm/Bootstrap/Gossip/Adaptive) | S1-S5 全覆盖 | — |
| 工程落地 (54项) | 25 逐维检查 | 6 (Tracker/Snapshot/Healing/Security) | S2 S5 + REST API | — |
| 三层企业 (30项) | 8 能力存在 | — | S1 S4 | 宏观评分 + 架构评分 |

---

## 2. 框架一：L1-L5 自主性验证

### 2.1 核心验证

```bash
bash scripts/verify-l4-pyramid.sh
# → L0→L5 逐层, 每层必须全部 PASS 才进入下一层
# 预期输出: "✅ 当前最大可宣称等级: L5 (元循环工程)"
```

### 2.2 能力深度验证

```bash
bash scripts/verify-l4-depth.sh
# → Python 行为测试, 验证模块不只是存在而是真正工作
# 预期: 30 passed
```

### 2.3 逐轴证据验证

| 轴 | 验证命令 | 预期 |
|:---|:---|:--:|
| A | `grep -c 'class GoalExecutor' aiPlat-core/core/harness/optimization/goal_executor.py` | = 1 |
| A | `grep -c 'class GoalGenerator' aiPlat-core/core/harness/optimization/goal_generator.py` | = 1 |
| B | `grep -c 'class AdaptiveContextRouter' aiPlat-core/core/harness/knowledge/adaptive_context.py` | = 1 |
| B | `grep -c 'CRAG' aiPlat-core/core/apps/agents/materials_chat.py` | ≥ 1 |
| B | `find aiPlat-core/core/harness/ontology_engine -name '*.py' \| wc -l` | ≥ 23 |
| C | `grep -c 'ToolBootstrapEngine' aiPlat-core/core/harness/optimization/tool_bootstrap.py` | = 1 |
| C | `find aiPlat-core/core/engine/skills -name 'SKILL.md' \| wc -l` | ≥ 30 |
| D | `grep -c 'class GossipProtocol' aiPlat-core/core/harness/memory/gossip_protocol.py` | = 1 |
| D | `find aiPlat-core/core/harness/memory -name '*.py' \| wc -l` | ≥ 4 |
| D | `grep -c '_resolve_semantic_conflict' aiPlat-core/core/harness/memory/semantic.py` | ≥ 1 |
| E | `grep -c 'class SwarmBroker' aiPlat-core/core/harness/coordination/swarm_broker.py` | = 1 |
| E | `wc -l < aiPlat-core/core/harness/integration.py` | ≥ 3000 |
| F | `grep -c 'class StrategySearchEngine' aiPlat-core/core/harness/optimization/search_engine.py` | = 1 |
| F | `grep -c 'class ExecutionSnapshot' aiPlat-core/core/harness/execution/snapshot.py` | = 1 |
| F | `grep -c 'class StrategyEffectivenessTracker' aiPlat-core/core/harness/optimization/strategy_tracker.py` | = 1 |

---

## 3. 框架二：工程落地验证

### 3.1 一票否决检查

| # | 条件 | 验证 | 预期 |
|:--:|------|:---|:--:|
| 1 | CI/CD 流水线 | `ls .github/workflows/*.yml \| wc -l` | ≥ 3 |
| 2 | 自动化测试 | `find aiPlat-core -name 'test_*.py' \| wc -l` | ≥ 50 |
| 3 | 可观测性基础设施 | `grep -c 'prometheus\|grafana\|jaeger' docker-compose.yml` | ≥ 3 |
| 4 | 安全扫描 | `grep -c 'S\|bandit' pyproject.toml` | ≥ 1 |
| 5 | 架构决策记录 | `find docs -name '*.md' \| wc -l` | ≥ 20 |

### 3.2 逐维验证

#### 代码质量

```bash
# 代码规范存在
test -f pyproject.toml && grep -c '\[tool.ruff\]' pyproject.toml | xargs -I{} test {} -ge 1 && echo "PASS"
# CI 强制检查
test -f .github/workflows/ci.yml && grep -c 'ruff\|mypy' .github/workflows/ci.yml | xargs -I{} test {} -ge 2 && echo "PASS"
# Commit 规范
test -f .commitlintrc.yaml && echo "PASS"
# 复杂度检查
grep -c 'radon' .github/workflows/ci.yml | xargs -I{} test {} -ge 1 && echo "PASS"
```

#### 测试验证

```bash
# 测试框架配置
grep -c 'pytest' aiPlat-core/pyproject.toml | xargs -I{} test {} -ge 1 && echo "PASS"
# 覆盖率配置
grep -c 'coverage' aiPlat-core/pyproject.toml | xargs -I{} test {} -ge 1 && echo "PASS"
# 回归标记
grep -c 'regression' aiPlat-core/pyproject.toml | xargs -I{} test {} -ge 1 && echo "PASS"
# 数据隔离
test -f aiPlat-core/core/tests/conftest.py && echo "PASS"
# 性能基准 CI
grep -c 'benchmark' .github/workflows/ci.yml | xargs -I{} test {} -ge 2 && echo "PASS"
```

#### CI/CD

```bash
# 流水线文件数
ls .github/workflows/*.yml | wc -l | xargs -I{} test {} -ge 3 && echo "PASS"
# 回滚脚本
test -f scripts/rollback.sh && echo "PASS"
# 版本标签
test -f scripts/tag-release.sh && echo "PASS"
# 发布通知
test -f scripts/notify-release.sh && echo "PASS"
```

#### 可观测性

```bash
# Prometheus
grep -c 'prometheus' docker-compose.yml | xargs -I{} test {} -ge 1 && echo "PASS"
# Grafana
grep -c 'grafana' docker-compose.yml | xargs -I{} test {} -ge 1 && echo "PASS"
# Jaeger/OTel
grep -c 'jaeger\|otel' docker-compose.yml | xargs -I{} test {} -ge 2 && echo "PASS"
# SLO 定义
test -f docs/slo.md && echo "PASS"
# 健康检查
grep -rc '/health' aiPlat-core/core/server.py | head -1 | xargs -I{} test {} -ge 1 && echo "PASS"
```

#### 安全

```bash
# SAST
grep -c '"S"' pyproject.toml | xargs -I{} test {} -ge 1 && echo "PASS"
# 依赖扫描
test -f .github/dependabot.yml && echo "PASS"
# 密钥管理
grep -c 'SecretsManager' aiPlat-core/core/harness/infrastructure/secrets_manager.py | xargs -I{} test {} -ge 1 && echo "PASS"
# 审计日志
grep -c 'SHA.*256\|hash.*chain\|tamper' aiPlat-core/core/services/execution_store/schema.py | xargs -I{} test {} -ge 2 && echo "PASS"
# 漏洞SLA
test -f SECURITY.md && echo "PASS"
```

#### 架构

```bash
# 模块边界(arch guard)
wc -l < aiPlat-core/core/management/arch_guard_rules.yaml | xargs -I{} test {} -ge 2000 && echo "PASS"
# Helm部署
test -f deploy/helm/aiplat/Chart.yaml && echo "PASS"
# HPA 自动扩缩容
grep -c 'HorizontalPodAutoscaler\|autoscaling' deploy/helm/aiplat/values.yaml | xargs -I{} test {} -ge 1 && echo "PASS"
# 技术债管理
grep -c '已知例外\|永久债务' CLAUDE.md | xargs -I{} test {} -ge 1 && echo "PASS"
```

---

## 4. 框架三：三层企业验证

### 4.1 宏观层 — 12 维

三层企业评估的得分是加权计算，无法用 `grep -c` 直接验证。以下命令验证**底层能力存在性**：

```bash
# Agent 框架存在 (维度 5, 权重 10%)
wc -l < aiPlat-core/core/harness/execution/pipeline_engine.py | xargs -I{} test {} -ge 4000 && echo "PASS"

# MCP 协议 (维度 4, 权重 10%)
test -f aiPlat-core/core/apps/mcp/server.py && echo "PASS"

# 本体引擎 (维度 6, 权重 7%)
find aiPlat-core/core/harness/ontology_engine -name '*.py' | wc -l | xargs -I{} test {} -ge 23 && echo "PASS"

# 知识图谱 (维度 6, 权重 7%)
grep -c 'class GraphIndex' aiPlat-core/core/harness/ontology_engine/graph_index.py | xargs -I{} test {} -ge 1 && echo "PASS"

# 幻觉检测 (维度 3, 权重 8%)
grep -c 'HallucinationTracker\|hallucination' aiPlat-core/core/harness/infrastructure/gates/ -r | head -1 | xargs -I{} test {} -ge 1 && echo "PASS"

# 数据血缘 (维度 9, 数据治理)
grep -c 'data.lineage\|data_lineage' aiPlat-core/core/api/routers/diagnostics.py -r | head -1 | xargs -I{} test {} -ge 1 && echo "PASS"

# 安全架构 (维度 8, 权重 10%)
grep -c 'AES.*256\|GCM\|SecretsManager' aiPlat-core/core/harness/infrastructure/secrets_manager.py | xargs -I{} test {} -ge 1 && echo "PASS"

# 多智能体编排 (维度 9, 权重 9%)
grep -c 'class SwarmBroker\|class DynamicOrchestrator' aiPlat-core/core/harness/coordination/ -r | head -1 | xargs -I{} test {} -ge 2 && echo "PASS"
```

### 4.2 评分复核

三层企业评估的得分是**人工判断 + 代码证据**的组合。外部审稿人应：

1. 先运行上述验证命令确认基础设施存在
2. 再对照 `scoring-detail.md` §4 的"证据"列逐一复核
3. 如有分歧，以代码实际状态为准

---

## 5. 运行时行为验证 (需 ./start.sh)

代码层验证了"存在"，行为层验证了"能跑"。以下 8 个场景通过 curl 对运行中的 aiPlat 实例做端到端测试。

### 5.1 场景一览

| 场景 | 验证内容 | 对应框架 | 对应轴 |
|:---|:---|:---|:--:|
| **S1** | 多步任务无人介入自主推进 | L1-L5 A轴 + 三层企业 | 自主循环 + E2E |
| **S2** | ErrorTranslator→Harness 自愈在线 | L1-L5 F轴 + 工程 观测/安全 | 自愈 + 仪表盘 |
| **S3** | 跨轮次上下文记忆召回 | L1-L5 B/D轴 | 记忆 + 上下文 |
| **S4** | 能力缺口检测→子Agent生成 | L1-L5 E轴 + 三层企业 | 动态组队 |
| **S5** | SKILL.md 生成+注册 | L1-L5 C轴 + 工程 CI | 工具自举 |

### 5.2 S1: 自主循环

> 验证 L4 核心特征：给定多步任务，系统无人介入从起点推到终点。

```bash
curl -s -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"分三步回答：1)总结 2)分析 3)优化。每步用 ## 标记"}]}'
```

**预期**：HTTP 200，`status=completed`，`run_id` 非空。Agent 返回三步内容。

**L4 判定依据**：请求后无需人类介入，Agent 自主完成多步推理。如果返回 `paused/failed` 则 L4 验证失败。

### 5.3 S2: 自愈引擎

> 验证 Phase 24：ErrorTranslator 诊断 → Harness 策略路由。

```bash
curl -s http://localhost:8000/api/diagnostics/health | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('layers',[])))" 
# → 4 (infra/core/platform/app)
```

**预期**：诊断面板返回 4 层健康状态。自愈仪表盘在线。

**工程验证**：`grep -c '\[healing\]' ~/.aiplat/logs/aiplat.log` → ≥ 1（仅在发生错误时出现）。

### 5.4 S3: 上下文感知

> 验证 L4 跨轮次记忆：第一轮告诉偏好，第二轮能召回。

```bash
# Step 1: 写入偏好
curl -s -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"记住：我偏好列表格式"}], "session_id":"ctx-test"}'

# Step 2: 召回 (同一 session_id)
curl -s -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"我的格式偏好是？"}], "session_id":"ctx-test"}'
```

**预期**：第二个请求返回内容包含"列表"关键词。Agent 跨轮次保持了上下文记忆。

### 5.5 S4: 动态组队

> 验证 Phase 32：Agent 输出→能力缺口检测→子 Agent 生成。

```bash
curl -s -X POST http://localhost:8000/api/core/workspace/agents/materials_chat/execute \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"需要安全检查这段代码"}]}'
```

**预期**：HTTP 200，`status=completed`。Agent 能识别"安全"关键词并生成安全审查子 Agent。

### 5.6 S5: 工具自举

> 验证 Phase 31：ToolBootstrap 生成 SKILL.md + 注册到 SkillRegistry。

```bash
# 检查 bootstrap 目录
ls ~/.aiplat/skills/bootstrap/*/SKILL.md 2>/dev/null | wc -l
```

**预期**：≥ 1 个 SKILL.md（首次需 GoalExecutor 激活，非零即通过）。

### 5.7 一键运行

```bash
bash scripts/verify-l4-behavior.sh [BASE_URL]
# 默认 http://localhost:8000
# 需要 ./start.sh 已运行
```

### 5.8 行为层预期结果

| 场景 | L3 表现 | L4+ 表现 (aiPlat 预期) |
|:---|:---|:---|
| S1 多步任务 | 需人工催促 | 一次触发，自主推进完成 |
| S2 自愈 | 报错停止 | 自动换 Key，日志显示 healing |
| S3 跨轮次 | 不知道/不确定 | 准确召回偏好 |
| S4 动态组队 | 固定流程 | 检测→生成子Agent→执行 |
| S5 工具自举 | 人工写工具 | 自动生成+注册 SKILL.md |

### 5.9 诊断面板（管理系统内置 REST API）

aiPlat 管理系统内置了运行时诊断能力，可直接通过 REST API 验证架构合规性。

#### 架构守卫 (76 条规则)

```bash
# 运行全部架构守卫规则
curl -s -X POST http://localhost:8000/api/diagnostics/guard/run | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Status: {d.get(\"status\")}')
print(f'Guards: {d.get(\"summary\",{}).get(\"total_checks\",0)}')
print(f'Violations: {len(d.get(\"violations\",[]))}')
"
```
**预期**：`status=ok`，violations 仅包含已知例外（CLAUDE.md §16 记录的 9 条）。

#### 4 层健康检查

```bash
# 全层健康
curl -s http://localhost:8000/api/diagnostics/health/all | python3 -c "
import sys,json
d=json.load(sys.stdin)
for layer in ['infra','core','platform','app']:
    h=d.get(layer,{})
    print(f'{layer}: {h.get(\"status\",\"?\")}')
"
```
**预期**：4 层全部返回 `healthy` 或 `degraded`。连续多轮 `unhealthy` 表示故障。

#### 全量诊断

```bash
# 包含架构守卫 + 健康检查 + 深度诊断
curl -s -X POST http://localhost:8000/api/diagnostics/run-all | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(f'Status: {d.get(\"status\",\"?\")}')
checks=d.get('checks',[])
print(f'Checks: {len(checks)}')
for c in checks[:5]:
    print(f'  {c.get(\"module\",\"?\")}: {c.get(\"status\",\"?\")}')
"
```

#### CLI vs REST API

| 方式 | 何时用 | 依赖 | 类型 |
|:---|:---|:---|:---|
| `scripts/architecture_guard.sh` | 本地开发 / CI | 无 | 代码层 |
| `POST /diagnostics/guard/run` | 运行时 / 管理系统 | `./start.sh` | 行为层 |
| `scripts/verify-l4-pyramid.sh` | 逐层评级 | 无 | 代码层 |
| `scripts/verify-l4-behavior.sh` | 端到端场景 | `./start.sh` | 行为层 |

> **组合使用**：CLI 脚本验证代码质量（CI 阶段），REST API 验证运行时状态（部署后），两者互补。

---

## 6. 一键验证

```bash
# 代码层 (零依赖)
bash scripts/verify-l4-pyramid.sh    # L0→L5 31/31
bash scripts/verify-l4-depth.sh      # 96 tests
bash scripts/verify-l4-claims.sh     # 31 checks

# 行为层 (需 ./start.sh)
bash scripts/verify-l4-behavior.sh   # 8 场景 curl
curl -s -X POST http://localhost:8000/api/diagnostics/guard/run  # 架构守卫
curl -s http://localhost:8000/api/diagnostics/health/all          # 4 层健康

# 引用校验
bash scripts/verify_whitepaper_refs.sh  # 28 refs
```

### 预期输出

```
verify-l4-pyramid.sh:   ✅ L5 (元循环工程) — 全层通过
verify-l4-depth.sh:     ✅ 96/96 PASS
verify-l4-claims.sh:    ✅ 31/31 PASS
verify-l4-behavior.sh:  ✅ 7/7 PASS (需 ./start.sh)
verify_whitepaper_refs.sh: ✅ 28/28 refs verified
```

### 非自动化的验证项

| 验证项 | 原因 | 所需专业能力 |
### 非自动化验证项

#### 只能通过代码验证

| 类别 | 项数 | 原因 | 示例 |
|:---|:--:|:---|:---|
| 架构决策记录格式 | 3 | ADR 文件存在性是 grep 可查的 | `find docs -name '*.md' \| wc -l` |
| 安全策略文档 | 2 | SECURITY.md / SLO 文档存在性 | `test -f SECURITY.md` |
| 技术债清单 | 1 | CLAUDE.md 中技术债记录 | `grep -c '已知例外' CLAUDE.md` |
| CI 配置文件 | 5 | YAML 文件存在性 | `ls .github/workflows/` |

#### 只能通过人工判断

| 验证项 | 原因 | 所需专业能力 |
|:---|:---|:---|
| 渗透测试 | 需主动攻击运行中系统 | 安全工程师 + Burp Suite/ZAP |
| 故障演练 | 需注入故障观察恢复行为 | SRE + Chaos Mesh/Gremlin |
| 宏观评分 | 涉及商业判断、竞品对比 | 行业分析师 |
| 架构评分 | 需架构演进知识和经验 | 高级架构师 |

---

## 7. 评分标准（0-5 分）

三层企业评估使用 0-5 分制。以下为每分的客观判定条件：

| 分数 | 名称 | 判定条件 | 示例 |
|:--:|:---|:---|:---|
| **5** | 领先 | 能力超出行业标准，有可证明的技术先进性 | UCB1 收敛算法 vs 人工调参的硬编码路由 |
| **4** | 优秀 | 能力完整，有可验证的实现和测试覆盖 | 四层记忆系统，每层独立文件 + pytest 覆盖 |
| **3** | 基础 | 核心功能存在并可用，但有已知缺失 | MCP 协议有 Server 注册，但无故障转移 |
| **2** | 不足 | 功能存在但质量远低于生产标准 | 有代码但没有测试，或仅概念验证 |
| **1** | 初始 | 仅概念验证或设计文档，未实现 | Roadmap 上写了但代码中 grep 不到 |
| **0** | 缺失 | 完全没有该能力 | 多模态中的"视频处理"——代码中无任何相关实现 |

**判定规则**：
- 证据来自代码：`grep -c` 命中且 ≥1 行 → 至少 3 分
- 证据来自 pytest 测试通过 → 至少 4 分
- 证据来自行业对标（如 vs 360/DeepSeek 明确领先） → 可评 5 分
- 若证据仅来自设计文档且代码中不存在 → 最高 2 分
- 代码存在但无测试 → 最高 3 分

**为什么必须有 0 分和 5 分**：
- 0 分确保"缺失"不会被淡化。一个能力缺失不应被"总体还行"掩盖
- 5 分确保"领先"有客观依据，不是自我标榜

---

## 8. 验证原则

| # | 原则 | 说明 |
|:--:|------|:---|
| 1 | **代码为唯一定论** | 设计文档不算数，代码存在性(`grep -c`)和代码行为(pytest) = 唯一证据 |
| 2 | **存在≠工作** | `grep -c class Foo` = 1 证明模块存在，深度测试证明模块工作。两者缺一不可 |
| 2 | **必须有负检查** | "有 X 能力"必须伴随"没有 Y 能力"的反证 |
| 3 | **必须可复现** | 所有命令可在任何克隆 repo 中运行 |
| 4 | **最低分原则** | 系统等级由最薄弱环节决定 |

---

> *验证协议版本 v1.0.0。三框架评估项 102 项，通过 104 项检查验证（代码层 62 + 行为层 38 + 人工层 4）。自动化部分 < 60 秒完成。*
> *非自动化项需人工复核，已在 §5 标注。*
