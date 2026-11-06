# Arena 盲评 Pilot closeout（2026-11-05）

> **双标**：✅ 朱莹 × 朱鸿林（n=30）  
> **仲裁**：✅ 朱向群（3 条，全部 gold=B · 与朱鸿林一致）  
> **结果 schema**：✅ `arena.blind.v1` → `evidence/arena_blind_result.v1.json`  
> **QA**：✅ 已签 · **`overall_pass=false`**（发卷 SEND 泄漏模型名 → 盲评部分破坏）  
> **length smoke**：❌ **未替换**（`replaces_length_smoke=false` · `gate_eligible=false`）  
> **`accuracy_claim`**：false

## 数字

| 指标 | 值 |
|---|---|
| n | 30 |
| agreement | 0.90 |
| κ | 0.8459 |
| 分歧 | 3（arena-16/18/24） |
| 朱莹 vs gold | 0.90 |
| 朱鸿林 vs gold | 1.00 |
| gold winner（解盲后） | qwen2.5-coder:7b **14** · qwen2.5:3b **8** · Tie **8** |

## 证据

- `packages/aiplat-evaluation/docs/a3/evidence/arena_blind_aggregate.v1.json`
- `…/arena_blind_adjudication.v1.json`
- `…/arena_blind_adjudicated_gold.v1.json`
- `…/arena_blind_result.v1.json`
- `…/arena_blind_qa_process.v1.json`

## QA 发现（保留）

发给评审的 `ARENA_BLIND_SEND_CN.md` 写了 `qwen2.5-coder:7b vs qwen2.5:3b`。  
CSV/JSON 标签表本身无模型字段；泄漏来自同目录说明文件。  
抽查 5/5 同意 gold；`overall_pass=false` · `blind_integrity=partial_compromise`。  
后续发卷改用：`ARENA_BLIND_SEND_ANNOTATOR.md`（无模型名）+ 协调人版分开发。

## 诚实锁

盲评结果 ≠ accuracy · ≠ 替换 length smoke · ≠ 质量 gate · 本 pilot 盲评完整性仅部分成立
