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

| 框架 | 评估范围 | 验证脚本 | 预期 |
|:---|:---|:---|:--:|
| L1-L5 自主性 | 18 项 (六轴×3) | `verify-l4-pyramid.sh` + `verify-l4-depth.sh` | L5 逐层通过 + 30 tests PASS |
| 工程落地 | 54 项 (六维) | `verify-l4-claims.sh` | 31/31 PASS |
| 三层企业 | 30 项 (3层) | `verify_whitepaper_refs.sh` + 手动对照 | 28/28 refs + 人工复核 |

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

## 5. 一键验证

```bash
# 全量自动化
bash scripts/verify-l4-pyramid.sh    # L0→L5 31/31
bash scripts/verify-l4-depth.sh      # 30 tests
bash scripts/verify-l4-claims.sh     # 31 checks

# 引用真实性
bash scripts/verify_whitepaper_refs.sh  # 28 refs

# 行为层 (需 ./start.sh)
bash scripts/verify-l4-behavior.sh   # 5 场景
```

### 预期输出

```
verify-l4-pyramid.sh:   ✅ L5 (元循环工程) — 全层通过
verify-l4-depth.sh:     ✅ 30/30 PASS
verify-l4-claims.sh:    ✅ 31/31 PASS
verify_whitepaper_refs.sh: ✅ 28/28 refs verified
```

### 非自动化的验证项

| 框架 | 验证项 | 原因 |
|:---|:---|:---|
| 三层企业 | 12 项宏观得分 | 加权计算需人工判断 |
| 三层企业 | 9 项架构得分 | 需架构知识 |
| 工程 | 5.5 渗透测试 | 需第三方 |
| 工程 | 6.9 故障演练 | 需 Chaos 工具 |

---

## 6. 验证原则

| # | 原则 | 说明 |
|:--:|------|:---|
| 1 | **代码为唯一定论** | 设计文档不算数，`grep -c` 返回值 = 唯一证据 |
| 2 | **必须有负检查** | "有 X 能力"必须伴随"没有 Y 能力"的反证 |
| 3 | **必须可复现** | 所有命令可在任何克隆 repo 中运行 |
| 4 | **最低分原则** | 系统等级由最薄弱环节决定 |

---

> *验证协议版本 v1.0.0。所有自动化验证 < 60 秒完成。*
> *非自动化项需人工复核，已在 §5 标注。*
