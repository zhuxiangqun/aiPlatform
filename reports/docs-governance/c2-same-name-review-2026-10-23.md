# C2 复核表 — 同名近重四对（2026-10-23）

> 批次批准：用户确认继续下一批（C2）。**未批准 C3–C4。**  
> 输入：`docs-cleanup-plan-2026-10.md` §8.5.2 / §3 C2。

## 裁决摘要

| # | 对 | 差异结论 | R6 | 动作 |
|---|-----|----------|-----|------|
| 1 | `guides/` ↔ `manuals/` `PR_ARCHITECTURE_CHECKLIST.md` | 正文不同；guides=CI `test -f` 契约；manuals=手册评审清单 | **保留双份 + 消歧** | 双方文首互指；不删 |
| 2 | `articles/` ↔ `architecture/` `private-control-plane.md` | 长文 vs 短 SoT 入口；非重复正文 | **保留双份 + 消歧** | 文首互指；修复 4 处失效相对链 |
| 3 | `architecture/comparison.md` ↔ `plans/comparison.md` | 现行六平台(2026-10) vs 过时四方案(2026-07)且自称「唯一入口」 | **迁 archive（删副本路径）** | `plans/comparison.md` → `archive/plans-comparison-four-platform-2026-07.md`；白皮书 yaml/卷改链 |
| 4 | `framework/` ↔ `whitepaper/` `verification-protocol.md` | 三框架验证 vs L5 验证；版本/用途不同 | **保留双份 + 消歧** | 双方文首互指；不合并 |

## R3 入链处置（摘）

| 引用 | 处置 |
|------|------|
| `.github/...` → `guides/PR_ARCHITECTURE…` | 确认无需改（CI SoT） |
| `manuals/README` → manuals 清单 | 确认无需改 |
| `overview` / `plans/*` → `articles/private-control-plane`（原相对路径失效） | **已改** 为 `../articles/…` 或 `../../articles/…` |
| `governance` / `eu-ai-act` → `architecture/private-control-plane` | 确认无需改（短 SoT） |
| 白皮书 suite/卷 → `plans/comparison` | **已改** → archive 文件名 |
| 研究/白皮书 → `architecture/comparison` | 确认无需改（现行 SoT） |
| framework/whitepaper 验证协议交叉引用 | 消歧条已写入；路径保留 |

## R5

无删除。迁 archive 1 份；外部留存副本 **未核实·待确认**。

## 批次验收

| 项 | 结果 |
|----|------|
| 删除 | **0** |
| 迁 archive | **1**（`plans/comparison.md`） |
| 消歧并存 | **3** 对 |
| 失效链修复 | overview + 2×plans + archive 旧稿内链 |
| C0 口径复测 | total **261**（+1 本复核表）· maint **196**（迁 archive −1 与本表 +1 相抵） |
| 仓库总数 | 迁档不减总数；+1 因本复核表 |
| C3–C4 | **未实施** |
