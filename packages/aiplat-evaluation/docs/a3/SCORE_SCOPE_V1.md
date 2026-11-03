# EVAL 首版满分范围（Score Scope v1）

> Parent: [`README.md`](./README.md) · 记分卡: [`SCORECARD_V1.md`](./SCORECARD_V1.md) / [`scorecard_v1.json`](./scorecard_v1.json)  
> Honesty: **功能覆盖 ≠ 准确性** · **本地独立 ≠ 生产授权** · `accuracy_claim=false` · `process_split_authorized=false`

## 满分定义（强制）

**5/5 = 在本文声明的范围内，无已知缺口，且有可复现测试/证据。**  
不是「通用评测全能」，不是「生产可拆分」，不是 G2b 准确率认证。

改范围必须升版本（`v2`）并同步记分卡；禁止用扩大范围的方式「冲满」旧分。

---

## 一、功能覆盖（Feature coverage）

### In-scope（首版）

| 维度 | 证据锚点 | 5/5 条件 |
|------|----------|----------|
| Agent / Skill / Prompt / KB / Arena / code_review | P1 runners + gates | schema + 测试 + 报告字段 |
| 多轮 session v0+v1 | `SESSION_V0.md` / `SESSION_V1.md` | v1 在 closeout 内 |
| 人评 / 偏好 | `PREFERENCE_V0.md` + **真人 A/B** | 双人 worksheet + κ/agreement 证据；fixture solo ≠ 满分 |
| G2b 双人盲标（prep→closeout） | `G2B_PREP.md` | 两人独立 ≥30 + κ JSON；κ≠accuracy |
| 合规 / PII（最小集） | *待建* `COMPLIANCE_PII_V0.md` | schema + 规则/报告 + 测试 |
| S1 live_llm 安全指标 | `S1_LIVE.md` | ASR/leak/false_refusal；`llm_ok_n≥1`；≠ SOC 认证 |
| 效率（延迟/成本） | `P1_DIMENSIONS.md` + prod_live | p50/p95 + cost；`accuracy_claim=false` |
| 维度矩阵 + 覆盖度报告 | *待建* 由 `scorecard_v1.json` 起步 | 每维：schema / 规则或 gold / 测试 / 报告字段 |

### Out-of-scope（首版显式排除 → 不因缺失扣「首版 5」）

- HTTP / CLI **外部程序**端到端评测  
- 完整红队 / live skill tools / microVM 工具执行  
- 企业级数据驻留跨境策略全量  
- RLHF 生产训练闭环  

### 诚实边界

**功能 5/5 ≠ 准确 5/5。** 准确性另表（G2b/κ）；未完成真人双标前，功能覆盖最高记 **工程完备但人评未闭环**（见记分卡）。

---

## 二、工程架构（Engineering architecture）

### In-scope（首版 5/5）

| 条件 | 说明 |
|------|------|
| 单一 canonical API | `/api/platform/apps/eval`；legacy 仅 shim 或冻结删除 |
| 单一 contracts SSOT | `packages/aiplat-evaluation` contracts |
| 产品根 | package 拥有 API/domain/store/worker/sandbox/tests（+ chart） |
| 平台薄适配 | platform 只转发，不写 eval 业务 |
| core 通用化 | eval 专属逻辑不在 core 业务层残留 |
| 独立 build/test/release | package 可单测/单构；CODEOWNERS + 版本 |
| 依赖无环 | 无私有跨库直读 eval 内部 |

**拆仓不是 5/5 必要条件**（monorepo + 产品根即可）。

### Out-of-scope

- 当日无条件进程拆分 / `process_split_authorized=true`  
- 多区域多活评测拓扑  

### 架构 5 判定（v1.4）

In-scope 收口完成：单挂 + 308、薄路由、contracts SSOT、CODEOWNERS、产品根声明（[`PRODUCT_ROOT_V1.md`](./PRODUCT_ROOT_V1.md)）。  
Central `legacy_7dim` **保留为历史 report-only**（`deprecated_for_engineering=true`），**不**静默重加权——此为诚实终态，非未完成项。见 [`P1_CANONICAL.md`](./P1_CANONICAL.md)。

---

## 三、本地独立运行（Local independence）

### In-scope（首版 · **不含 microVM**）

| 条件 | 说明 |
|------|------|
| B1–B3-L 收口 | 已有 closeout 证据 |
| local_track_closeout v2 | P1/S1/live_llm/session_v0+v1/preference fixture；authorize locked |
| 生产候选模型 live | ≥20 条；latency/cost/fail；`llm_ok_n≥1`（`PROD_LIVE.md`） |
| B4-S **本机**预演 | Docker PG backup/restore；`environment=local` ≠ staging |
| OIDC / 租户 | 本地最小可跑路径（非企业完整 realm） |
| 沙箱 | Docker `network=none` 级；**不**宣称隔离认证 |

### Out-of-scope（首版 · Mac 可声明排除）

- microVM / KVM / live skill tools 真隔离执行  
- 完整企业 OIDC realm + HA + 生产 SLO  
- staging / B4-S 主机授权 / B5 / B6  
- `process_split_authorized=true`（本地证据 **不得** 打开） |

### 含 microVM 的「本地独立」另表

若把 microVM 算进满分，**Darwin 笔记本不能打 5**；需 Linux/KVM 主机。该口径记为 `local_independence_with_microvm`，不与本文首版混用。

---

## 四、生产独立（单独轴 · 首版不打分冲 5）

生产独立 **不在** 上述三项首版满分内。前置：staging + B4-S/B5/B6 + SPLIT_CHECKLIST 全 ✅。

---

## 五、到 5 的执行顺序（可全部做，非二选一）

1. **锁定本文件**（本 PR）+ 记分卡诚实分  
2. **架构收口**（单 API / 契约 / 产品根）多 PR  
3. **功能补维**（合规/PII + 覆盖度矩阵）∥ **真人 G2b/preference**  
4. **本地独立**按「不含 microVM」冲首版 5；需要 microVM 再开 Linux 轨  
5. 生产轨最后  

---

## 六、变更规则

| 允许 | 禁止 |
|------|------|
| 升 `SCORE_SCOPE_v2` 扩大/缩小范围 | 范围外能力缺失却仍报首版 5/5 |
| 记分卡下调并附证据 | fixture / stub 冒充真人 κ 或 accuracy |
| 显式 out-of-scope | 本地演练写成 staging authorize |
