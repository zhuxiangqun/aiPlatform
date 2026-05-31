# 统一架构合规矩阵 (Unified Architecture Compliance Matrix)

> 本文档编码所有已知的架构违规模式。每当一轮审计发现新型问题，在此登记，
> 并同步更新 `scripts/architecture_guard.sh` 和 `tests/constitution/`。

## 矩阵总览

| 维度 | 检查项 | 检测手段 | 节号 |
|------|--------|---------|------|
| **层边界** | app↛core, app↛infra, platform↛infra, infra↛内部层, core↛platform/app | grep | §1 |
| **门面模式** | platform 禁止直接 PipelineEngine(, 禁止深度 harness import | grep | §2, §20 |
| **内核无关** | artifact key/角色名/评分维度/SOP/中文业务名/渠道适配不在 core | grep | §3 |
| **去应用化** | infra 无应用名/GPU型号/路径/salt 默认值 | grep | §4 |
| **App层** | App 无 HTTP Server/DB 访问 | grep | §5 |
| **LangGraph** | 不绕过 Harness 直接调 syscall | grep | §5.5 |
| **Core路由** | Core 路由器不定义 platform 级路由 | grep | §6 |
| **Skill元数据** | SKILL.md 有 effects/frontmatter 字段 | grep | §7 |
| **交接协议** | AGENT.md 有 handoff section | grep | §8 |
| **目录职责** | core/apps/ 目录为通用运行时或 Internal Policy | grep | §9 |
| **AI模型归属** | Platform 不 import AI 模型库 (Whisper/Tesseract/Paddle) | grep | §10 |
| **文档解析** | Platform kb/intelligence 不实现 parser/classifier | grep | §11 |
| **检索算法** | Platform query 只编排不实现检索算法 | grep | §12 |
| **Agent发现** | Platform 不实现 agent catalog/discovery | grep | §13 |
| **Agent方法** | Agent 类实现 add_skill/add_tool | grep | §14 |
| **BOUNDARY** | 声明存在 + layer 匹配物理位置 | grep | §15 |
| **AST行为** | Platform 函数不执行 LLM inference/agent discovery | AST | §16 |
| **Builder测试** | 端到端测试通过 | pytest | §17 |
| **接线验证** | ≥1 生产 caller (非自身/非测试) | grep | §18 |
| **BOUNDARY覆盖** | 所有代码目录有 BOUNDARY.yaml | grep | §19 |
| **性能** | async 函数中无同步 subprocess.run/open | grep | §21 |
| **许可证** | 无 GPL/AGPL 依赖 | grep | §22 |
| **测试覆盖** | 关键模块有测试文件 | grep | §23 |
| **密钥扫描** | 源码中无硬编码 API key/密码 | grep | §24 |
| **错误处理** | 无 `except Exception: pass` (需 logging 或 # noqa) | grep | §25 |
| **安全配置** | YAML/JSON 无硬编码密码 | grep | §26 |
| **新文件覆盖** | 新 .py 文件有对应测试 | grep | §27 |
| **实现暴露** | __init__.py 不暴露具体实现类 | grep | §28 |
| **Vendor中立** | infra 不硬编码 Apple Silicon/NVIDIA 字符串 | grep | §29 |
| **代码质量** | 无 bare `except:` | grep | §30 |
| **代码质量** | datetime.now() 使用 timezone.utc | grep | §31 |
| | | | |
| **职责归属** | tenant管理不在core, marketplace路由不在core | Python | test_layer_ownership.py |
| **职责归属** | AI模型推理不在platform, 文档解析委托core | Python | test_layer_ownership.py |
| **职责归属** | Infra无业务角色名/应用名/GPU型号 | Python | test_layer_ownership.py |
| **职责归属** | Platform使用CoreFacade访问core | Python | test_layer_ownership.py |
| **职责归属** | App不import core/infra | Python | test_layer_ownership.py |

## 审计发现 → 检查登记流程

每当审计发现新型问题，执行：

1. **分类**：确定属于哪个维度（层边界/内核无关/去应用化/代码质量/安全/职责归属）
2. **编码**：
   - 如果可用 grep 检测 → 加入 `scripts/architecture_guard.sh`（新增§N）
   - 如果需要 Python 语义 → 加入 `tests/constitution/test_*.py`（新增测试方法）
3. **文档**：在此矩阵添加一行
4. **验证**：运行 `bash scripts/architecture_guard.sh && pytest tests/constitution/`，确认新检查生效

## CI 集成

```bash
# PR 门禁执行顺序
bash scripts/architecture_guard.sh    # §1-§31 grep 级扫描
pytest tests/constitution/ -v         # Python 级语义检查 + 职责归属
```

失败 = 禁止合并。豁免需在对应文件中添加 `# noqa: allowed — <审批理由>`。

## 覆盖盲区（当前无法自动化）

| 盲区 | 原因 | 缓解措施 |
|------|------|---------|
| "这个模块应该在哪层"的语义判断 | 需要理解代码意图 | 人工 code review + BOUNDARY.yaml 声明 |
| 性能回归 | 需要 profiling | 独立性能测试套件 |
| 安全漏洞（注入/越权） | 需要安全专家审查 | 独立安全审计 |
| 设计文档 vs 代码一致性 | 需要人工对照 | 代码优先原则 (CLAUDE.md §1.1) |
