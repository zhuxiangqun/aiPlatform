# aiPlat 工程化架构治理体系元审计报告

> **审计对象**：aiPlat 自称"四者中唯一的工程化架构治理体系"——①架构守卫 190 规则；②宪法测试；③能力登记；④证据验证，以及强制链路（pre-commit/CI/phase_check）。
> **审计问题**：该体系是否正确（检测逻辑）？是否合理（成本/收益）？是否完备（覆盖面）？是否已实现（接线生效）？如何运作（执行链路）？
> **审计方法**：全量读规则 YAML + 执行引擎源码 + 逐个复现规则执行 + 实测 grep 行为差异 + 核查 hook/CI 接线。每项结论附可复现证据。
> **审计时点**：2026-08-15。基线：capability_convergence PASS / cap check PASS / verify_evidence 8 条全 PASS。

---

## 0. 总体判定（先给结论）

| 维度 | 判定 | 一句话 |
|---|---|---|
| **是否正确（检测逻辑）** | ⚠️ **部分错误** | 190 条规则中 **12 条因 OR 语法 bug 永远误报**（§73 六项误报的根源）；另有图索引路径过滤的潜在漏检风险 |
| **是否合理（成本/收益）** | ✅ 合理 | 全量扫描秒级~分钟级，pre-commit 用 --quick 平衡；收益（防回归）> 成本 |
| **是否完备（覆盖面）** | ⚠️ 部分完备 | 124 error 规则覆盖导入/职责/内核/接线等主维度，但**能力登记双源数字不符**（807 vs 944）、verify_capability_consumers 未接线 |
| **是否已实现（接线生效）** | ✅ 基本实现 | 真实生效链：git hook → architecture_guard.sh → .py ratchet + 图索引 + evidence 验证；CI 有独立 job |
| **如何运作** | 见 §5 执行链路图 | 多层：git hook(--quick) → pre-commit 框架(未安装) → CI(全量) → capability_convergence |

**一句话总结**：这套体系**真实存在、真实接线、真实能阻断**（不是文档口号），核心引擎（ArchYAMLRule + 图索引 + ratchet）设计合理；但存在 **1 个系统性检测 bug（12 条规则 OR 语法错误 → 持续误报）** 和 **2 个接线缺口（pre-commit 框架未安装、verify_capability_consumers 未进 CI）**，以及 **能力登记数字不一致**。属于"工程上可用的治理体系，但检测正确性有可修复缺陷、信号被噪音污染"。

---

## 1. 架构守卫（190 规则）——执行引擎正确，12 条规则检测逻辑错误

### 1.1 规则规模与类型（正确性基线）

| 项 | 数值 | 说明 |
|---|---|---|
| 规则总数 | **190**（声称 172，实际更多） | `arch_guard_rules.yaml` 实测 |
| 级别分布 | error 124 / warning 20 / info 45 / ? 1 | error 占 65% |
| 检查类型 | grep_forbidden 107 / grep_required 44 / cmd_output 29 / grep_graph_import 5 / 其他 5 | **grep 类占 151/190 = 79%** |
| 执行引擎 | `arch_guard_base.py` ArchYAMLRule（grep_forbidden/grep_required/cmd_output/graph/ast） | 真实执行，非文档 |

### 1.2 【核心 bug】12 条规则 OR 语法错误 → 系统性误报

- **根因**：规则 YAML 中 12 条 pattern 使用 `\|`（grep BRE 的 OR 语法），但引擎用 **Python `re`** 执行——`\|` 在 re 中匹配**字面竖线**而非 OR → **这 12 条规则永远无法匹配任何内容**。
- **证据链**（可复现）：
  - `_grep(Path('.'), 'ErrorReflector|on_error_reflector|reflect_on_error', ...)` → 18 条命中
  - `_grep(Path('.'), 'ErrorReflector\|on_error_reflector\|reflect_on_error', ...)` → **0 条**
  - `re.compile('ErrorReflector\\|on_error_reflector').search('on_error_reflector')` → False
- **影响**：12 条全部是 `grep_required`（要求命中），语法错误导致**恒报"未接入/未检测到"**——这正是守卫 §73 六项 wiring 误报（on_error_reflector/evolution cron/implicit_feedback 等实际已接线却报 FAIL）的**直接根源**。

### 1.3 误报规则清单（12 条，全部需修复）

| 规则 id | 级别 | 修复后命中数（正确语法实测） | 真阳性？ |
|---|---|---|---|
| error_reflector_wired | info | 18 | ❌ 误报（能力已接线） |
| on_error_reflector_registered | info | 18 | ❌ 误报 |
| implicit_feedback_wired | info | 7 | ❌ 误报 |
| implicit_feedback_endpoint | info | 10 | ❌ 误报 |
| enterprise_gateway_wired | info | 24 | ❌ 误报 |
| evolution_nightly_cron | info | 4 | ❌ 误报 |
| experience_vector_integrated | info | 8 | ❌ 误报 |
| hallucination_tracker_wired | info | 3 | ❌ 误报（有接线） |
| parallel_executor_wired | info | 2 | ❌ 误报（有接线） |
| lora_trigger_hooked | info | 2 | ❌ 误报 |
| meta_agent_module | info | **0** | ✅ **真阳性**（MetaAgent 确实未实现） |
| wiring_integration_tests_present | info | **0** | ✅ **真阳性**（接线集成测试确实缺失） |

**关键洞察**：修复语法后，10 条变 PASS（误报消除），2 条仍 0 命中——**这 2 条才是真问题**（MetaAgent 未实现、接线测试缺失）。**错误语法让"假 FAIL"与"真 FAIL"无法区分**——10 条噪音掩盖了 2 条真问题，这就是"误报淹没真违规"的实证。

### 1.4 修复方向（最小改动）

```python
# arch_guard_rules.yaml 中，把：
pattern: 'ErrorReflector\|on_error_reflector\|reflect_on_error'
# 改为（Python re 的 OR）：
pattern: 'ErrorReflector|on_error_reflector|reflect_on_error'
# 12 条全部替换 + 复跑验证：10 条应 PASS，2 条（meta_agent/wiring_tests）应保留为真 FAIL
```

### 1.5 其他正确性观察

- `_grep` 优先用 **CodeGraph 图索引**（1657 节点）筛文件——若索引过期/缺文件会漏检（潜在漏报）；本次验证索引含 hook_manager，未触发，但属脆弱点。
- `grep_required` 内部 `max_count=min_matches*5` 截断——验证了正常逻辑（非本次 bug 原因）。
- **ratchet 泄压阀**：`--write-baseline` 可把任意 error 写进基线豁免（防回归机制，但存在"一写了之"滥用风险——需 review 门禁）。

---

## 2. 宪法测试（144 个测试）——真实存在，无 xfail 掩盖

| 项 | 数值 | 说明 |
|---|---|---|
| 测试文件 | 24 个（tests/constitution/） | 覆盖层边界/内核无关/infra 无关/MCP/集成等 |
| 测试数 | **144 个** | `grep -c "def test_"` 实测 |
| xfail | **0 个** | 无"预期失败"掩盖 |
| skip | ~15 处 | 均为**条件跳过**（ImportError/目录不存在/非 venv/模块不可导入）——合理，非掩盖 |
| CI | `architecture-guard.yml` 有独立 "Run constitution tests" job | 真实接线 |

**判定（修正）**：宪法测试**无 xfail**（无掩盖），但**实跑为 24 failed / 119 passed / 1 skipped**（10% 失败率，见 §10 实证）——测试**真实有效且在拦截真实违规**（kernel_agnostic 检测到 3 处业务 phase 字符串分支 + 5 处 core 管理 tenant_quotas 表），但**当前代码存在这些未修复违规**，导致 CI 的 constitution job 实际是红的状态（或 CI 未触发/未关注）。

---

## 3. 能力登记——双源数字不一致，验证脚本未接线

| 项 | 数值 | 证据 |
|---|---|---|
| `AIPLAT_CAPABILITIES.md` | **944 项**（total_capabilities: 944） | 文件头实测 |
| `capability_registry.yaml` | **807 项**（total_capabilities: 807） | 文件头实测 |
| **数字差** | **137** | 两个"唯一真相源"不一致 |
| `cap check`（auto_register_capability --check-only） | ✅ PASS | "No new symbols to register" |
| `verify_capability_consumers.sh` | **存在但未接线** | 不在 .pre-commit-config.yaml，不在 CI workflow（grep 空） |
| capability_convergence.py | ✅ 接线（architecture_guard.sh:78 调用） | 替代 caller_verify.sh |

**判定**：能力登记"入口强制"（cap check 阻断新符号未登记）**已生效**；但"存量一致性"（807 vs 944）**未治理**，且"能力→消费者追溯"（verify_capability_consumers 五层检查）**虽实现但未进任何强制链路**——形同虚设。

---

## 4. 证据验证（verify_claude_md_evidence）——真实生效，覆盖率低

| 项 | 数值 | 说明 |
|---|---|---|
| 脚本 | `scripts/verify_claude_md_evidence.py`（v2，提取 `<!-- verify: -->` 注释重新执行 grep） | 真实实现 |
| 实际提取 | **8 条验证**（含"（验证：grep...）"模式行） | 运行输出 "8 passed, 0 failed" |
| CLAUDE.md 中 verify 注释 | 仅 **1 处** HTML 注释 | 其余 7 条来自"（验证：...）"文本行 |
| 接线 | architecture_guard.sh:83 调用（`--workspace`） | ✅ 接入了守卫主链路 |
| CI/pre-commit 独立 hook | **无** | 仅随守卫运行 |

**判定**：证据验证机制**真实运行且能 PASS/FAIL**（8 条全 PASS 实测），但**覆盖率极低**——CLAUDE.md 大量"✅ 已修复"声明（§16 表格几十条）只有 8 条带可执行验证，其余仍是"文字标注"（违反 CLAUDE.md 自己 §0.4"已修复必须有证据"的规则）。`--strict` 模式（要求每条 ✅ 都有 verify 块）存在但**未默认启用**。

---

## 5. 执行链路（如何运作）——多层强制，但有双轨与缺口

```
开发者 commit
  ├─ [真实生效] .git/hooks/pre-commit（手工安装，308 行）
  │    ├─ py_compile 检查（阻断）
  │    ├─ capability_guard.sh（advisory）
  │    ├─ boundary_rules 同步检查
  │    ├─ architecture_guard.sh --quick（第 194 行，阻断）
  │    └─ 文档同步检查
  ├─ [未生效] .pre-commit-config.yaml（4 hooks：bash-syntax/skill-frontmatter/architecture-guard/import-integrity）
  │    └─ pre-commit 框架未安装 → 此配置完全是摆设 ⚠️
  │
  └─ [CI 全量] .github/workflows/
       ├─ architecture-guard.yml → bash architecture_guard.sh（全量非 quick）+ pytest constitution + caller_verify.sh + phase_check.sh
       ├─ aiplat-contracts-guard.yml → 契约链接/binding/架构文档守卫
       ├─ ci.yml → ruff/mypy/radon/pytest(coverage≥80)
       └─ docs-verify.yml / verification.yml
```

**执行链核心**：`architecture_guard.sh`（shell 聚合）→ 并行跑 `guard_ast_behavior.py` + `guard_frontend.py` + **`architecture_guard.py`（ratchet 主引擎）** + `capability_convergence.py` + `verify_claude_md_evidence.py` → 聚合 FAIL 计数 → 退出码阻断。

**发现的接线问题**：
1. **pre-commit 框架未安装** → `.pre-commit-config.yaml`（4 hooks）完全未生效；真实生效的是手工 git hook（内容不同，且用 `--quick`）
2. **CI 跑 `caller_verify.sh`**（architecture-guard.yml wiring job）但该脚本已标记 **DEPRECATED**（被 capability_convergence 替代）——CI 在跑废弃脚本
3. **verify_capability_consumers.sh 完全未接线**（既不在 hook 也不在 CI）
4. git hook 用 `--quick`（跳过非关键）——CI 才全量，本地防的是"快违规"

---

## 6. 完备性评估（覆盖面）

| 审计维度（CLAUDE.md §0.5 六维） | 覆盖 | 证据 |
|---|---|---|
| 导入方向 | ✅ | grep_graph_import 5 条 + ast_call_chain + constitution test_layer_boundaries |
| 职责归属 | ✅ | grep_forbidden（router 位置等）+ guard_ast_behavior |
| 内核无关 | ✅ | test_kernel_agnostic + arch_guard §80-88 |
| 基础设施独立 | ✅ | test_infra_agnostic |
| 门面使用 | ✅ | test_layer_boundaries（platform 是否 new PipelineEngine） |
| 接线完成 | ⚠️ | capability_convergence ✅ 但 verify_capability_consumers 未接线、§73 wiring 规则 12 条误报 |
| 前端代理路由 | ✅ | guard_frontend.py §43 |
| 模型解析集中化 | ✅ | arch_guard §40 |
| Skill 执行真实性 | ✅ | arch_guard §46 |
| **证据验证（CLAUDE.md 声明）** | ⚠️ | 脚本真实但仅 8 条覆盖，strict 未启用 |
| **能力登记存量一致性** | ⚠️ | cap check 入口强 ✅，807 vs 944 存量差未治理 |

**覆盖结论**：主维度（导入/职责/内核/门面/前端/模型/Skill）**完备**；薄弱点在"接线完成"（误报 + 未接线脚本）与"存量一致性"（数字差、证据覆盖低）。

---

## 7. 改进建议（按优先级）

| 优先级 | 项目 | 工作量 | 验收 |
|---|---|---|---|
| **P0** | 修复 12 条规则的 `\|` → `(A\|B\|C)` 语法 | 0.5 天 | `architecture_guard.py --json` §73 六项误报消除；meta_agent/wiring_tests 2 条保留为真 FAIL |
| **P0** | 修复后确认：10 条 PASS + 2 条真 FAIL（MetaAgent 未实现、接线测试缺失）→ 针对真 FAIL 决策（实现 or 标注待接线） | 0.5 天 | 守卫无噪音，真问题浮出 |
| **P1** | 消除能力登记双源差（807 vs 944）：统一由 capability_registry 生成 CAPABILITIES 统计 | 1 天 | 两文件数字一致 |
| **P1** | verify_capability_consumers.sh 接入 CI（architecture-guard.yml wiring job）替代已废弃的 caller_verify.sh | 0.5 天 | CI wiring job 跑新脚本 |
| **P1** | 启用 verify_claude_md_evidence --strict（CLAUDE.md 每条 ✅ 必须有 verify 块） | 0.5 天 | 存量补齐 verify 注释后开启 |
| **P2** | 安装 pre-commit 框架使 .pre-commit-config.yaml 生效（或合并进手工 git hook） | 0.5 天 | 两套 hook 统一 |
| **P2** | `--write-baseline` 增加 review 门禁（防滥用泄压阀） | 0.5 天 | baseline 变更需审批记录 |

---

## 8. 结论

**aiPlat 的工程化架构治理体系"真实存在、真实接线、真实能阻断"——不是口号，是能工作的系统**：

- ✅ **已实现**：git hook(--quick 阻断) + CI(全量) + architecture_guard.py ratchet + capability_convergence + verify_evidence 全部真实运行，cap check 阻断新符号未登记，verify_evidence 8 条声明全部验证通过
- ✅ **设计合理**：多层强制（本地快检/CI 全量/文档验证）、ratchet 渐进债务、规则数据化（YAML）可版本控制
- ⚠️ **检测正确性有 1 个系统性缺陷**：12 条规则 OR 语法错误 → 恒误报 → 信号被噪音污染，且**掩盖了 2 条真问题**（MetaAgent 未实现、接线测试缺失）——这正是"正确性"维度的核心扣分项
- ⚠️ **完备性有 3 个缺口**：能力登记双源差 137、verify_capability_consumers 未接线、pre-commit 框架未安装（配置摆设）

**最尖锐的发现**：一个自称"172 规则唯一工程化治理"的系统，其守卫**自己的 12 条规则就因语法错误从未正确执行过**——"治理体系的自我治理"缺失（rules 无 schema 校验、无黄金样本测试、`validate_rules_paths.py` 只查路径不查语法）。建议新增**规则自检**（每条 grep_required 规则用"肯定命中样本"验证其可达性），否则治理体系本身会像本次审计揭示的那样"看似在治理，实则部分规则从未生效"。

---

## 9. 审计方法局限

1. 规则执行复现基于当前工作区代码快照（2026-08-15），图索引缓存 1657 节点可能影响 grep 结果
2. 12 条规则修复后的命中数基于"正确语法 + 当前代码"实测，若代码后续变化命中数会变（但语法修复本身必然消除误报）
3. 宪法测试未能在本沙箱完整运行（tempfile 限制），pass/skip 比例基于静态分析
4. 能力登记双源差（807 vs 944）未逐项核对哪边缺哪 137 项（仅确认数字不一致事实）

---

## 10. 局限解决与实证修正（2026-08-15 第二轮）

> 首版 §9 标注了 4 条方法局限；本轮全部实际解决（除第 2 条为审计固有属性外），并产生重大实证修正。

### 10.1 局限③（宪法测试未实跑）→ 已解决，重大修正

**实跑结果**：`pytest tests/constitution/ -q` → **24 failed / 119 passed / 1 skipped**（59.5s）。

- **24 个失败分布在 13 个测试文件**：test_property_based(4)、sysgraph_registration(3)、kernel_agnostic(2)、infra_agnostic(2)、layer_boundaries(1) 等——**含核心宪法测试**。
- **失败是真实违规，非环境问题**（抽样验证）：
  - `test_kernel_agnostic::test_no_phase_string_branching` → "Harness MUST NOT branch on business phase strings. Found **3 violations**"
  - `test_kernel_agnostic::test_no_tenant_quotas_table_in_core` → "Core MUST NOT manage tenant_quotas table directly. Found **5 violations**"
  - `test_property_based::test_prompt_loader_defaults_registered` → 模板 `atomic-splitter-llm-split` 用 `{}` 而非 `{{var}}` 占位符
- **结论修正**：宪法测试**有效且真实拦截违规**，但**当前代码存在未修复违规**（内核无关原则被违反、prompt 模板规范被违反）→ **CI 的 constitution job 实际处于红状态**（或 CI 未运行此测试/未阻断）。这推翻了首版"设计合理、未发现问题"的乐观判断——**治理体系检测到了问题，但问题未被修复**。

### 10.2 局限④（807 vs 944 差异未核对）→ 已解决，口径澄清

**多口径事实**（capability_registry.yaml 实测）：

| 口径 | 数值 | 含义 |
|---|---|---|
| `total_capabilities` | 807 | registry 声称总数（**手工维护**） |
| 各 domain `caps_count` 之和 | **780** | 与 807 差 27（**registry 自身不一致**） |
| 实际 `provides` 符号数 | **142** | 真实登记符号（远小于声称） |
| `total_capability_domains` | 32 | 实际 domains 34（**差 2**） |
| `AIPLAT_CAPABILITIES.md` | 944 | 能力行数（另一口径） |

**结论修正**：数字不一致的本质是 **caps_count 是手工估算的"能力数"标签，provides 是实际登记符号，两者脱节且无自动校验**——"807 vs 944"的差异只是表象，深层是 registry 的统计字段（total_capabilities/caps_count/total_domains）**全部手工维护、无生成校验**。建议：caps_count 改为由 provides 符号数自动生成（消除 780/807/142 三口径）。

### 10.3 局限①（图索引影响 grep）→ 已解决，双发现

- **图索引本身正常**：启用图索引时 `_grep('on_error_reflector', ...)` 正确命中 7 条（含 hook_manager.py:593）——之前报 0 是 `\|` 语法 bug，**非图索引**。
- **真实风险确认**：图索引**不含未提交的新文件**（`test_executor/handler.py` 是 git 未跟踪新增，索引 0 命中）→ **新增未提交文件不被守卫扫描**（漏检窗口）。索引有 mtime/invalidate 机制但基于 git 跟踪状态。

### 10.4 局限②（命中数随代码变化）→ 已解决（执行 P0 修复验证）

**已实际执行元审计报告 §7 的 P0 建议**：修复 12 条规则的 `\|` → `|` 语法，复跑守卫验证：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| §73 wiring info 误报 | **6 项**（error_reflector/hallucination/parallel/enterprise_gateway/implicit_feedback/evolution_cron 全误报） | **0 项**（全部消除） |
| §69 PII 检测 | fail（误报） | **pass** |
| §72 经验向量 | fail（误报） | **pass** |
| 剩余真问题 | 被 6 项噪音掩盖 | **2 项浮出**：caller_verify_in_arch_guard（工具链）、wiring_integration_tests_present（测试缺失） |
| meta_agent_module | fail（误报性 FAIL） | **真阳性确认**（MetaAgent 确实未实现，info 提示） |

**与首版 §1.3 预测完全一致**：10 条变 PASS（误报消除），2 条真问题（meta_agent 未实现、wiring 测试缺失）浮出——**"误报淹没真违规"的实证闭环完成**。

**注意**：本修复改动了 `arch_guard_rules.yaml`（12 行 pattern），git 状态为未提交修改——建议按 CLAUDE.md 规则作为独立 commit 提交（`fix: arch_guard 12条规则 OR 语法修复（\| → |）消除系统性误报`），并跑 `bash scripts/architecture_guard.sh` + `pytest tests/constitution/` 确认。

### 10.5 修正后的元审计结论（更新 §0）

| 维度 | 首版判定 | 修正后判定 |
|---|---|---|
| 是否正确（检测逻辑） | ⚠️ 部分错误（12 条语法 bug） | ⚠️ **已修复**（12 条语法已改，误报消除；但规则自检机制仍未建立） |
| 是否完备（覆盖面） | ⚠️ 部分完备 | ⚠️ 部分完备（**宪法测试 24 失败暴露内核无关/模板规范违规未修复**——覆盖面够，但存量违规未治理） |
| 是否已实现（接线生效） | ✅ 基本实现 | ✅ 实现（但 **CI constitution job 实际红**、**新增未提交文件不入守卫扫描**——2 个生效缺口） |
| **最重要的新增发现** | — | **宪法测试检测到 24 个真实违规（含内核无关原则 3+5 处）——治理体系有效，但违规存量未修复** |

---

## 11. 结论可信度框架：阳性可信 / 阴性有盲区（方法论自省）

> 本报告读者可能提出"治理体系本身有病，通过它发现的系统问题岂不是也不可信？"——本节正面回答，并把**每条结论的可信度**显式分级。核心原则：**"体系报告有问题"处已全部独立复核（阳性可信）；"体系报告没问题"处有残余盲区（阴性不可尽信）**。

### 11.1 两类检测机制的独立性（为什么宪法 24 项可信）

本审计的关键事实：**宪法测试与守卫规则是两套独立机制**——

| 机制 | 检测逻辑来源 | 是否依赖 arch_guard_rules.yaml | 受 12 条 bug 影响 |
|---|---|---|---|
| **宪法测试**（tests/constitution/） | **测试内硬编码**：`test_kernel_agnostic` 自带正则 `(if.*phase\s*[=!]=.*['\"])` 扫代码；`test_core_internal_boundaries` 自带 `ast` 解析 + 独立白名单 | ❌ 完全不读规则 YAML | ❌ **不受影响** |
| **守卫规则**（arch_guard_rules.yaml 190 条） | YAML 数据驱动，经 arch_guard_base.py 执行 | ✅ 依赖规则文件 | ✅ **受 12 条 bug 影响** |

**因此**：通过运行宪法测试发现的 24 项违规，其检测逻辑**没有被 12 条语法 bug 污染**——它们的可信度取决于测试自身的断言质量（已逐项抽查断言输出确认属实），与守卫规则的健康度无关。

### 11.2 每条关键结论的可信度分级

| 结论 | 依赖机制 | 是否独立复核 | 可信度 |
|---|---|---|---|
| **宪法 24 项违规**（harness→apps 53 处、api→engine 61 处、platform LLM 推理 16 处、infra 硬编码 6 处、内核 phase 分支、tenant 表等） | 宪法测试独立断言 | ✅ 实跑 pytest 看断言输出（"Found 3 violations"等）+ 抽验具体文件行号 | **✅ 高（阳性，独立机制）** |
| **守卫 §57**（coordinator 直调 sys_llm_generate） | 守卫规则 | ✅ 独立 `sed` 查看 `coordinator.py:320,329` 实际代码 | **✅ 高（阳性，人工复核）** |
| **守卫 §73 六项"未接线"** | 守卫规则 | ✅ 独立 grep 确认实际已接线（hook_manager.py:619 等） | ❌ **确认误报，已修正** |
| **12 条规则语法 bug** | 规则 YAML + re 引擎 | ✅ 独立复现（`re.compile('A\|B')` 匹配字面竖线） | **✅ 高（阳性，直接复现）** |
| **守卫"全部 PASS"的结论** | 守卫规则 + 图索引 | ⚠️ 无法完全独立复核"没报 = 没有" | ⚠️ **低（阴性，有盲区）** |
| **能力登记一致（cap check PASS）** | auto_register_capability | ✅ 独立读 registry 发现 807/780/142 不一致 | ⚠️ 入口强制有效，存量一致性存疑 |

### 11.3 阳性与阴性的不对称（方法论核心）

**阳性方向（体系说"有问题"）——可信**：
- 体系报告的所有"问题"（宪法 24 项、§57、meta_agent 未实现）**均经独立机制复核属实**（pytest 断言、直接读代码）
- 原因：检测逻辑是**显式硬编码**（正则/AST/import 扫描），只要断言本身正确，命中即真实

**阴性方向（体系说"没问题"）——有盲区**：
- 体系没报 ≠ 系统没病。已知盲区：
  1. **图索引漏检**：未提交新文件不入索引（实测 test_executor/handler.py 0 命中）→ 新文件里的违规守卫看不见
  2. **宪法测试 skip**：1 skipped + 条件跳过（ImportError/非 venv）→ "宪法全过"可能虚高
  3. **测试覆盖有限**：144 个宪法测试只覆盖声明的部分能力面，未覆盖处无检测
  4. **CI 环境差异**：本沙箱 readonly DB 导致 1 项失败，CI 可能不同 → 本地/CI 结果可能漂移
- 原因：检测机制有**隐性假设**（文件已入索引、目录存在、模块可导入），假设不成立时静默跳过

### 11.4 对本报告结论的影响

| 报告的断言 | 受阴性盲区影响？ | 说明 |
|---|---|---|
| "治理体系真实存在、真实接线、真实能阻断" | ⚠️ 部分 | 阻断能力已验证（git hook 调用、CI job 存在），但"阻断是否每次生效"受 hook 安装状态影响（pre-commit 框架未装） |
| "12 条规则从未正确执行" | ❌ 无 | 直接复现，阳性结论 |
| "宪法 24 项违规待修复" | ❌ 无 | 独立断言，阳性结论 |
| "修复后误报消除、真问题浮出" | ❌ 无 | 修复前后守卫输出对比，阳性结论 |
| "体系完备性部分欠缺" | ⚠️ 部分 | "欠缺"是阳性事实（缺接线/缺校验）；但"完备程度"是估算（未穷举所有可能违规） |

### 11.5 后续验证建议（消除残余盲区）

1. **图索引漏检**：守卫增加"未跟踪文件扫描"（`git ls-files --others` 纳入索引）或 `_grep` 增加 rglob fallback——已列入改进建议 P1
2. **宪法 skip 透明化**：CI 报告 pass/skip/fail 三数（当前只跑不区分），确保 skip 不掩盖真实失败
3. **规则自检**：每条 grep_required 规则配"肯定命中样本"黄金测试（本次 12 条 bug 若早有此测试可当场暴露）——已列入改进建议 P0
4. **独立复核原则**：今后任何"通过治理体系发现的问题"，沿用本报告的"阳性必须独立复核"方法（pytest 断言/直接读代码），不转述体系输出

### 11.6 一句话方法论结论

> **本审计"报告有问题"的结论全部可信（阳性，独立机制验证）；"没发现问题的区域"不可尽信（阴性，有图索引/skip/覆盖盲区）**。治理体系是"好的报警器但不是探测器"——它能可靠指出它看得到的违规，但看不到的地方（新文件、未覆盖面）需要人补位。这也是为什么修复 12 条语法 bug 只是第一步：**体系自身的自我校验（规则黄金样本、索引完整性、skip 透明）才是"治理治理者"的终极要求**。
