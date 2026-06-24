# aiPlat 系统质量全面诊断报告

> 生成时间: 2026-06-23 | 增量更新: 2026-06-24 (记忆子系统 7 项硬化合入)
> 诊断范围: 全仓库 (aiPlat-core + aiPlat-platform + aiPlat-management + aiPlat-infra)
> 诊断方法: 结构完整性 + 接线完整性 + 工具正确性 + 能力可达性 + 路径契约 五维交叉验证

---

## 一、接线完整性

### 1.1 发现阶段

系统扫描发现 6 个 Phase 0-6 模块"已创建但从未接线"（1500+ 行死代码）：

| 模块 | Phase | 功能 | 原状态 | 现状态 |
|------|:---:|------|:---:|:---:|
| `semantic_cache.py` | 0.3 | L1+L2+L3 语义缓存 | 0 callers | ✅ 已接线 |
| `hallucination_tracker.py` | 3.1 | NLI 事实核查 + Faithfulness | 0 callers | ✅ 已接线 |
| `parallel_executor.py` | 1.2 | Sub-Agent FanOut Map-Reduce | 0 callers | ✅ 已接线 |
| `on_error_reflector.py` | 4.1 | Agent 连续失败→反思 Hook | 0 callers | ✅ 已接线 |
| `gateway/__init__.py` | 2.3 | 飞书/企微/Slack 消息网关 | 0 callers | ✅ 已接线 |
| `implicit_feedback.py` | 4.2 | 用户行为隐式反馈 | 0 callers | ✅ 已接线 |

### 1.2 接线 bug 修复

| 模块 | 问题 | 修复 |
|------|------|------|
| `on_error_reflector` | `for o in str(o)` 迭代字符而非列表 | → `for o in recent` |
| `ParallelExecutor` | 仅用 Semaphore 控制，核心 FanOut 未用 | → `parallel_analyze()` 接入 pipeline_engine |
| `LatentStageCache` | L3 fallback（最后备用） | → 升级为 L2 primary 缓存层 |
| `EmbeddingBridge` | 5000 字符阈值触发 | → 移除阈值，始终压缩 |
| `EnterpriseGateway` | 启动但从未触发推送 | → 审批暂停事件触发 `handle_message()` |
| `SemanticCache.invalidate` | 仅 wiki HTTP 更新清缓存 | → `write_page()` 内部 + KB re-index 全覆盖 |
| `SemanticCache.invalidate` | O(N) SCAN→DELETE 全量清除 | → INCR version O(1) 原子切换 + L1主动清 + 版本窗口 (2026-06-24) |
| `ProvenanceScanner` | 仅 HTTP POST 端点触发 | → 嵌入 `write_page()` 覆盖 9 个程序化路径 |

### 1.3 方法级完整性

对 6 个已接线模块的 18 个关键方法做了详细验证：

| 模块 | 方法数 | 已调用 | 完整度 |
|------|:---:|:---:|:---:|
| `semantic_cache.py` | 3 | 3 | 100% |
| `hallucination_tracker.py` | 3 | 3 | 100% |
| `parallel_executor.py` | 3 | 2 (map 内包) | 67% |
| `on_error_reflector.py` | 1 | 1 | 100% |
| `gateway/__init__.py` | 3 | 3 | 100% |
| `implicit_feedback.py` | 2 | 2 | 100% |

---

## 二、守卫/诊断/测试程序自身质量

### 2.1 审计发现

对全部 27 个守卫/诊断/图谱/评估程序做了自检，发现 9 项关键问题：

| # | 工具 | 问题 | 严重度 | 已修复 |
|:---:|------|------|:---:|:---:|
| 1 | `guard_frontend.py` §45 | `content[:300]` 截断 → 4 条误判 | P0 | ✅ |
| 2 | `guard_frontend.py` §45 | `backend_dirs` 缺 management → 10 条误判 | P0 | ✅ |
| 3 | `guard_frontend.py` §46 | macOS BSD grep 不认 `\s+` → 0 违规检测 | P0 | ✅ |
| 4 | `caller_verify.sh` | `set -euo pipefail` 索引构建崩溃 | P0 | ✅ |
| 5 | `method_verify.sh` | DEAD 方法仍 exit 0 → phase_check 永远 PASS | P0 | ✅ |
| 6 | `arch_guard_rules.yaml` | 2 条规则路径指向旧位置 (knowledge/→ontology_engine/) | P1 | ✅ |
| 7 | `arch_guard_rules.yaml` | 重复 rule ID `skill_nested_revisions` | P1 | ✅ |
| 8 | `tests/wiring/` | 2 个空测试 (无断言) + 1 个弱断言 | P1 | ✅ |
| 9 | `architecture_guard.sh` | phase_check 软失败 (WARNING) | P1 | ✅ |

### 2.2 自测试覆盖

| 指标 | 修复前 | 修复后 |
|------|:---:|:---:|
| 有自测试的程序 | 1/27 (4%) | **27/27 (100%)** |
| 工具自测试总数 | 25 | **125** |
| CI 集成 | ❌ | ✅ `architecture_guard.sh` 自动执行 |

---

## 三、API 路径契约

### 3.1 跨语言路径验证

新增 `guard_frontend.py` §45 自动检测前端 API 调用与后端路由不匹配：

| 问题 | 数量 | 状态 |
|------|:---:|:---:|
| MCP 路径 `mcp/{scope}/servers` → `{scope}/mcp/servers` | 6 条 | ✅ 已修复 |
| `kbApi.documentQuery` `/documents/query` → `/kb/query` | 1 条 | ✅ 已修复 |
| `kbApi.reingestDocument` `/documents/{id}/refresh` → `/kb/documents/{id}/reingest` | 1 条 | ✅ 已修复 |
| `ImportBar` `/skills/install-from-directory` → `/wiki/skills/install-from-directory` | 1 条 | ✅ 已修复 |
| `KnowledgeBase` `/maintain/model-log` → `/wiki/maintain/model-log` | 1 条 | ✅ 已修复 |
| `UploadModal` `/documents/ingest-directory` | 1 条 | ⚠️ 已知债务（前端占位，后端未实现） |
| `UploadModal` `/kb/watch` | 1 条 | ⚠️ 已知债务（同上） |
| Wiki 重复路由 `GET /wiki/golden-queries/seed` | 1 条 | ✅ 已删除 |

### 3.2 内部 API 路径

| 问题 | 数量 | 状态 |
|------|:---:|:---:|
| `POST /api/core/permissions/grant` 端点不存在 | 1 | ⚠️ 静默失败在 try/except 中 |
| `POST /api/core/plugins/{id}/disable` 端点不存在 | 1 | ⚠️ 已知债务 |
| UI 按钮路径指向已迁移端点 | 4 | ⚠️ 已知债务 |

---

## 四、能力可执行性

### 4.1 能力声明清单

从 AIPLAT_ARCHITECTURE_REPORT.md（31 章）和 AIPLAT_ROADMAP.md（Phase 0-6）提取了 41 条系统能力声明，建立了结构化清单 `capability_manifest.yaml`。

### 4.2 三维交叉验证

每条能力从三个维度验证：

```
声明 × 模块可达性 × 方法级调用
```

验证结果：

| 域 | 能力数 | 完整 | 部分 | 未激活 |
|------|:---:|:---:|:---:|:---:|
| 执行内核 | 7 | 6 | 1（内部方法） | 0 |
| Agent | 3 | 2 | 1（工厂模式） | 0 |
| Skill | 3 | 3 | 0 | 0 |
| 知识引擎 | 5 | 4 | 1（内部方法） | 0 |
| RAG 检索 | 5 | 3 | 2（内部方法） | 0 |
| 可观测性 | 3 | 3 | 0 | 0 |
| 安全合规 | 3 | 2 | 1（工厂模式） | 0 |
| 自学习 | 6 | 5 | 1 | 0 |
| 企业能力 | 5 | 5 | 0 | 0 |
| 工具/门户 | 1 | 0 | 1（内部函数） | 0 |
| **总计** | **41** | **33** | **8** | **0** |

关键发现：**0 条能力完全不可达，0 条能力零方法调用。** 所有 41 条声明的核心能力均可从入口点到达。

---

## 五、检测体系架构

```
architecture_guard.sh (CI 每次运行)
├── architecture_guard.py (165 条 grep 规则)
├── capability_convergence.py
├── guard_ast_behavior.py
├── guard_frontend.py (§43 代理 §44 契约 §45 路径 §46 导入)
├── pytest tests/tool_correctness/ (125 tests)
│   ├── guard_frontend 自测试 (25 tests)
│   ├── arch_guard 自测试 (11 tests)
│   ├── code_graph 自测试 (16 tests)
│   ├── caller_verify 自测试 (5 tests)
│   ├── phase_check 自测试 (8 tests)
│   ├── 工具不变量测试 (10 tests)
│   ├── 能力清单测试 (5 tests)
│   └── 批量集成测试 (18 tests + 15 others)
├── constitution tests
├── code_graph cycle detection
└── phase_check.sh
    ├── caller_verify.sh
    ├── method_verify.sh
    ├── pytest tests/wiring/ (46 tests)
    └── validate_rules_paths.py (165 rules)

capability_verify.py (能力可执行性验证 — 手动/CI)
    声明 × 可达性 × 方法级调用
```

---

## 六、已知债务清单

| # | 项 | 严重度 | 说明 |
|:---:|------|:---:|------|
| 1 | `POST /api/core/permissions/grant` 不存在 | P1 | 平台调用但 core 无端点，静默失败 |
| 2 | `POST /api/core/plugins/{id}/disable` 不存在 | P1 | 同上 |
| 3 | 4 个 UI 按钮指向已迁移路径 | P2 | `change_control.py` 和 `gate_policies.py` |
| 4 | `caller_verify.sh` 报告 44 条 dead symbols | P3 | 约 15 条假阳性（dataclass/工厂模式） |
| 5 | `method_verify.sh` 计数膨胀 10-100x | P3 | 通用方法名匹配过多文件 |
| 6 | `UploadModal` ingest-directory + watch 无后端 | P3 | 前端占位，后端未实现 |
| 7 | `aiPlat-app/src` 路径不存在 | P3 | 架构守卫规则路径需更新 |
| 8 | Phase 9 DI 迁移完成但规则未清理 | P3 | §5.5 3 个文件排除规则未退役 |
