# Arena QA 重签清单（干净包 · 工程就绪 ≠ 已签）

> Pack: `20261108T073806Z` · Honesty: `accuracy_claim=false` · 不替换 length smoke

## 发给标注者之前

1. 只打包/发送 **`for_annotators/`** 目录。
2. 确认目录内有：`ARENA_BLIND_SEND_ANNOTATOR.md`、`ARENA_BLIND_RUBRIC_V1.md`、≥2 份 `annotator_*.json`。
3. 跑 leak-guard：

```bash
PYTHONPATH=packages/aiplat-evaluation python3 \
  packages/aiplat-evaluation/scripts/arena_blind_pack.py \
  --check .aiplat/eval_trust/arena_clean_pack_20261108/20261108T073806Z
# 期望 send_ready=true · leak_guard_pass=true
```

4. **不要**附带 `facilitator_only/` 或根目录 `facilitator.json`。

## QA 签字项（人工）

- [x] 盲评材料未见模型名（`blind_sheets_no_model`）— 2026-11-13 rg + leak-guard
- [x] 双人独立标注完成 — `for_annotators/annotator_r1.json` + `annotator_r2.json`
- [x] 抽查无 SEND 泄漏复现 — clean pack SEND 拆分 + leak_guard_pass
- [x] 记录 `overall_pass=true` — `packages/aiplat-evaluation/docs/a3/evidence/arena_blind_qa_resign_20261113.v1.json`

## 明确不做

- G2b scoped claim 与本 Arena QA **分轨**（claim 不因 Arena 自动翻）
- 不因本清单绿就替换默认 length smoke runner
- 人签证据必须独立 JSON；本清单仅勾选索引
