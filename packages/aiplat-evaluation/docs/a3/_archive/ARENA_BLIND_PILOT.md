# Arena 盲评 Pilot 运行手册（P1b）

> **状态**：双标+仲裁+`arena.blind.v1` 已写入 · length smoke **未替换**（收口：EVAL_ARENA_PILOT_CLOSEOUT_2026-11-05.md（历史链接失效））
> **日期**：2026-11-05
> **Rubric**：[ARENA_BLIND_RUBRIC_V1](../ARENA_BLIND_RUBRIC_V1.md)（已冻结）
> **设计**：[ARENA_BLIND_DESIGN](./ARENA_BLIND_DESIGN.md)
> **Honesty**：`accuracy_claim=false` · length smoke 不替换 · 无双人标签则 pilot 未完成

## 1. 产物

| 文件 | 用途 |
|---|---|
| `arena_blind_pairs.v0.json` | 配对源（含 model_*；仅 facilitator） |
| `scripts/arena_blind_pack.py` | 生成盲评 annotator 表 + facilitator 映射 |
| `human_pack/arena_blind/<stamp>/` | 一次 pilot 导出目录（gitignore） |

## 2. 生成

```bash
cd packages/aiplat-evaluation
python3 scripts/arena_blind_pack.py \
  --pairs docs/a3/arena_blind_pairs.pilot_20261105.json \
  --out docs/a3/human_pack/arena_blind \
  --annotators 朱莹,朱鸿林
```

pack 目录：
- `for_annotators/` → **只发这个**（annotator JSON + [`ARENA_BLIND_SEND_ANNOTATOR.md`](../ARENA_BLIND_SEND_ANNOTATOR.md) + rubric）
- `facilitator_only/` → 协调人留存（[`ARENA_BLIND_SEND_FACILITATOR.md`](../ARENA_BLIND_SEND_FACILITATOR.md) + facilitator.json）

脚本会扫描 `for_annotators/`：若出现 `model_a`/`model_b` 字符串则 **退出码非 0**（防 2026-11-05 SEND 泄漏复现）。

最近一次 **真实 pair** pack：`human_pack/arena_blind/20261105T153116Z/`（n=30；QA 记 blind 部分破坏）。
pair 源：[`arena_blind_pairs.pilot_20261105.json`](../arena_blind_pairs.pilot_20261105.json)。

Annotator 表字段：`pair_id`、`prompt`、`left`、`right`、`label`（A|B|Tie|null）、`notes`。
**不含** model 名、原文左右身份、length winner。

## 3. Pilot 完成勾选

- [ ] Rubric 培训完成（两位评审签字）
- [x] 实装 ≥30 对真实回答（本地双模型；见 `arena_blind_pairs.pilot_20261105.json`）
- [x] 每对 ≥2 独立盲标（朱莹×朱鸿林 · agreement=0.90 · κ=0.8459）
- [x] 分歧仲裁记录（朱向群 · arena-16/18/24 全 gold=B）
- [x] 结果写入 `arena.blind.v1` 单独 schema；**不覆盖** length smoke
- [x] 独立 QA 抽查（朱向群 · `overall_pass=false` · SEND 泄漏模型名）

length smoke 仍为默认 `evidence_level`。本 pilot `blind_integrity=partial_compromise`。
发卷模板已拆：[`ARENA_BLIND_SEND_ANNOTATOR.md`](../ARENA_BLIND_SEND_ANNOTATOR.md) / [`ARENA_BLIND_SEND_FACILITATOR.md`](../ARENA_BLIND_SEND_FACILITATOR.md)。

## 4. 状态（2026-11-05）

| 项 | 状态 |
|---|---|
| 双人评审 | ✅ |
| ≥30 真实 pair | ✅ |
| 仲裁 | ✅ |
| `arena.blind.v1` 结果 | ✅ |
| length smoke | 保留（未替换） |
| QA 抽查 | ✅ fail 发现已入库 `evidence/arena_blind_qa_process.v1.json` |
