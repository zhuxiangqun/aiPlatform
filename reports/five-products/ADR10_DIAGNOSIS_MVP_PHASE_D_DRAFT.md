# ADR-10 Phase D 草案 — 建议顺序第 2 步（改诊断生产默认）

- **状态**：**Proposed（草案）** · 2026-10-26 — **未批准；禁止据此改默认路径**  
- **上级**：`ADR09_DEFER_FULL_SPLIT_E4_PROD.md`（「继续」≠ 批准第 2–4 步）  
- **前置**：Phase C ✅（#426）；compose 复跑仍建议（本机 Docker 当前不可用）  
- **触发**：「继续」→ 仅落就绪清单，**不**升格授权

## 本草案若获批将授权什么（窄）

| 项 | 获批后 | 仍禁止 |
|----|:------:|--------|
| 诊断 MVP 允许在**显式** `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` 下离开纯沙箱试点（定义见下） | ✅ | — |
| 可选：compose **长驻**诊断 one-shot 以外的 profile（须可 `down -v`） | ✅ | — |
| 对外 E4 / ADR-09 Accepted / 五产品全拆 | — | ❌ |
| 拆控制面 / FDE / 本体 / 新诊断中台微服务 | — | ❌ |

## 「生产默认」操作性定义（草案）

今日代码里该 env **仅被试点脚本拒绝**，core/platform **尚无**读此开关的默认路径分叉（验证：仓内无 `DIAGNOSIS_PROD_DEFAULT` 的 `.py` 消费方）。  
故 Phase D **不是**「翻一个已有开关」，而须另 PR 实现二者之一（获批后选一）：

| 方案 | 含义 | 回滚 |
|------|------|------|
| **D1 共享 home 试点** | 允许 `ADR10_ALLOW_USER_HOME=1` + 指定 `AIPLAT_HOME=~/.aiplat` 跑 ingest/report（仍 opt-in env） | 清 flag；数据保留在用户 home |
| **D2 平台默认绑定** | 平台启动/路由在 flag=1 时默认走 slice diagnosis 路径（须设计入口与 feature 边界） | flag=0；保留沙箱脚本 |

**推荐默认（获批时）**：**D1**（爆破半径小；仍 opt-in；符合「单产品加深→再动默认」）。  
D2 须在批准句中**点名**，不得由 D1 默示。

## 获批前检查表（勾齐 + 书面批句）

| # | 项 | 现状 |
|---|------|------|
| 1 | 兼任 on-call 后果明示（仅诊断第 2 步） | ⬜ 批句内写明 |
| 2 | 范围仅 (c) 改诊断生产默认；**不含** (a)(b) E4/全拆 | ⬜ |
| 3 | 选定 D1 或 D2 | ⬜ |
| 4 | Phase C compose 复跑 PASS（有 daemon）或书面接受 SKIP 残差 | ✅ compose PASS（`ADR10_PHASE_C_COMPOSE_RERUN.txt` · `rep-07dcb770bbd6`） |
| 5 | 回滚演练步骤写入 ROLLBACK（含 flag=0） | ⬜ 随实现 PR |

## 批准句模板（复制即用）

> 批准 ADR-10 Phase D：**仅 D1**（共享 home opt-in）。接受兼任 on-call。**不含**对外 E4、**不含** ADR-09 Accepted / 全拆、**不含** D2 平台默认绑定。

或：

> 批准 ADR-10 Phase D：**D2**（平台默认绑定）+ 回滚 flag=0。接受兼任。不含 E4 / 全拆。

## 明确不在本草案效力内

未出现上列批准句之前：任何「继续」不得开始改 `AIPLAT_DIAGNOSIS_PROD_DEFAULT` 语义、不得长驻诊断服务、不得动平台默认路由。
