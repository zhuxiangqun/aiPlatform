# Arena 盲评 Pilot 运行手册（P1b）

> **状态**：脚手架就绪 · **pilot 完成仍依赖真人**（≥2 评审 × ≥30 对）  
> **日期**：2026-11-05  
> **Rubric**：[ARENA_BLIND_RUBRIC_V1](./ARENA_BLIND_RUBRIC_V1.md)（已冻结）  
> **设计**：[ARENA_BLIND_DESIGN](./ARENA_BLIND_DESIGN.md)  
> **Honesty**：`accuracy_claim=false` · length smoke 不替换 · 无双人/最小样本则本轮只交设计/阻塞记录

## 1. 产物

| 文件 | 用途 |
|---|---|
| `arena_blind_pairs.v0.json` | 配对源（含 model_*；仅 facilitator） |
| `scripts/arena_blind_pack.py` | 生成盲评 annotator 表 + facilitator 映射 |
| `human_pack/arena_blind/<stamp>/` | 一次 pilot 导出目录 |

## 2. 生成

```bash
cd packages/aiplat-evaluation
python3 scripts/arena_blind_pack.py \
  --pairs docs/a3/arena_blind_pairs.v0.json \
  --out docs/a3/human_pack/arena_blind \
  --annotators r1,r2
```

Annotator 表字段：`pair_id`、`prompt`、`left`、`right`、`label`（A|B|Tie|null）、`notes`。  
**不含** model 名、原文左右身份、length winner。

Facilitator 表保留 `left_is`（a|b）与 model 映射，**不得发给评审**。

## 3. Pilot 完成勾选

- [ ] Rubric 培训完成（两位评审签字）  
- [ ] 实装 ≥30 对真实回答（替换 fixture seed）  
- [ ] 每对 ≥2 独立盲标  
- [ ] 分歧仲裁记录  
- [ ] 结果写入 `arena.blind.v1` 单独 schema；不覆盖 length smoke  
- [ ] 独立 QA 抽查流程  

未勾满 → Arena 继续 `evidence_level=smoke`；本轮交付本手册 + 阻塞记录即可。

## 4. 阻塞记录（默认）

| 项 | 状态 |
|---|---|
| 双人评审排期 | pending |
| ≥30 真实 pair | pending（现仅 fixture×3 供 pack smoke） |
| QA 抽查 | pending |
