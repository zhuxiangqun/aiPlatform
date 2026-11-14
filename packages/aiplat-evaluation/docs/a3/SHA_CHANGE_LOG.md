---
doc_type: Reference
---

# Instruction / Evidence SHA 变更日志

> 计划 §4.3 · 每次更新 `evidence_manifest.instruction_versions` 或关键证据必须追加一条。  
> **禁止**无本日志的 hash 更新（hash-wash）。

---

## change_id: `EV-2026-11-14-001`

| 字段 | 值 |
|---|---|
| evidence_version | `ev-2026-11-14.1` |
| scorecard_version | `scorecard_v1`（未升 SCOPE 版本） |
| recorded_at | 2026-11-14 |
| judge | Cursor agent（Phase 0 执行） |
| reviewer | 待产品/评测 owner 复核 |
| bump_score_scope | **no** |
| rescore_required | **no**（计分轴与聚合数值未改；仅 instruction 哈希与 accuracy 字段名） |
| downstream_notified | pending（本 PR/提交说明） |
| rollback_ref | git：改前 `evidence_manifest.v1.json` + `g2b_accuracy_aggregate.v1.json` 可用 `git show HEAD:...` 恢复 |
| rollback_command | `git checkout HEAD -- packages/aiplat-evaluation/docs/a3/evidence/evidence_manifest.v1.json packages/aiplat-evaluation/docs/a3/evidence/g2b_accuracy_aggregate.v1.json`（若已提交则用本 change 前 commit） |

### 路径与判定

| path | old_sha256 | new_sha256 | change_class | diff_summary |
|---|---|---|---|---|
| `docs/a3/SCORE_SCOPE_V1.md` | `1ca81947ed9a…7ffd81` | `6be87c41f301…908742` | **editorial** | 仅增加 YAML `doc_type: Reference` frontmatter；正文/范围/门槛未改 |
| `docs/a3/PREFERENCE_V0.md` | `6b13594d5699…cc574d` | `427a686d910b…7b17b` | **editorial** | 仅增加 YAML `doc_type: Reference` frontmatter |
| `docs/a3/G2B_PREP.md` | `58fbff69d6b7…511b03` | `db46743ef587…efe071` | **semantic** | 正文降级为 index stub；SOP 迁至 `_archive/G2B_PREP.md`（sha `8fea59318aed…0e930a2`）。**不改变** SCORE_SCOPE 计分轴；κ/closeout 证据仍用既有 aggregate |

### 关联证据字段变更（同 change）

| path | 说明 |
|---|---|
| `docs/a3/evidence/g2b_accuracy_aggregate.v1.json` | 方案 A：产品级 `accuracy_claim=false`；新增 `scoped_accuracy_claim=true`；`not_accuracy_certification=true`；`claim_refuse_reason` 非空 |
| `docs/a3/evidence/evidence_manifest.v1.json` | 更新三份 instruction SHA；写入 `evidence_version` / `change_id`；method 注明 scoped 字段 |

### 结论

```text
允许更新 manifest SHA：是（有本记录）
升 SCORE_SCOPE 版本：否
重跑 scorecard 分值：否（仍须 scorecard_v1_check 转绿验证哈希）
```

---

## change_id: `EV-2026-11-14-002`

| 字段 | 值 |
|---|---|
| evidence_version | `ev-2026-11-14.2` |
| recorded_at | 2026-11-14 |
| change_class | editorial（路径诚实化） |
| bump_score_scope | no |
| rescore_required | no |
| rollback_ref | 上一版 local_worksheets 路径在 git 历史 / EV-2026-11-14-001 |

### 变更

| path | 说明 |
|---|---|
| `evidence_manifest.v1.json` `local_worksheets` | 路径从已删除的 `human_pack/20261103…` 改为 `_archive/human_pack/20261103…`；sha256 不变；标注 `archived=true`；正式 preference fixture 见 `fixtures/calibration/` |
| `scripts/accuracy_honesty_scan.py` | 方案 A 八消费方扫描（证据侧） |
| `scripts/phase0_ci_stable_subset.sh` | 接入 honesty scan |
| `.github/workflows/eval-phase0-stable.yml` | PR/push path filter 跑稳定子集 |
