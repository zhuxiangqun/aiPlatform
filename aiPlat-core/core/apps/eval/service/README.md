# eval/service — 读图（注释示范目录）

> 本目录是评测业务逻辑层（无 HTTP）。平台路由只应经 `CoreFacade` 调用这里的函数。  
> **注释规范示范**：以 `runs_eval_ops.py` 为样板（中文 docstring + Args/Returns/Raises）。

## 先读什么

| 顺序 | 文件 | 一句话 |
|:---:|------|--------|
| 1 | `runs_eval_ops.py` | **Run 闭环核心**：提交评测 → 自动摘要 → investigate → run_state / evidence / diff |
| 2 | `claims_gate.py` | L5 准确率/充分性门：默认 claim=false，须显式授权 |
| 3 | `g2b.py` | G2b 双人包状态与 scoped claim（读 attestation∧aggregate） |
| 4 | `subject_suite_profiles.py` | 对象套件 Profile（exam ≠ claim） |
| 5 | `*_capability_bank.py` | 各对象能力题库种子加载（模式高度同构） |

## 产物种类（LearningArtifactKind）

理解本目录时，先记住这些挂在 `run` 上的 artifact kind：

- `evaluation_report` — 人工/自动评测报告（可 gate）
- `investigate_report` — 汇总评测+证据+syscall 的诊断包
- `run_state` — 可合并、可锁定的运行状态快照
- `evidence_pack` / `evidence_diff` — 证据包及其对比

## 不要在这里找

- HTTP 路由 → `aiPlat-platform/apps/eval/api/`
- Object Contract / Plan 编译 → 同目录其他 `*_plan*` / facade
- 准确率认证宣称 → 默认 false；见 `claims_gate` / G2b attestation

## 补注释时遵守（强制底线）

> **全平台权威条文**：工作区根 `CLAUDE.md` 通用强制规则 **3a**。  
> **守卫**：`python3 scripts/check_python_docstring_guard.py --staged|--changed`（pre-commit + `architecture_guard.sh` §99）。

1. **语言**：程序注释 / docstring 默认**中文**（标识符、异常码、字段名保持英文）  
2. **公共模块**必须有模块 docstring（职责 + 非目标 + 关键入口）  
3. **对外 public 符号**必须有一句话说明，并写清参数：  
   - `Args:` 每个形参一行（含义 / 约束 / 可选默认）  
   - `Returns:` 返回结构要点  
   - `Raises:` 非显然失败（若有）  
4. **安全 / 诚实锁 / 绕过 / 非直观算法**必须有「为什么」行内注释  
5. **禁止**复述代码的废话注释（如 `# 自增 i`）  
6. 存量文件随改动补齐，不要求一次刷全目录  
 
