# ADR-09 前置 #5 · E4 干净环境验收（草案脚手架）

- **状态**：**草案** · 2026-10-25 — 脚本可跑且本机已记 PASS；**≠** E4 对外批准；**≠** ADR-09 Accepted  
- **脚本**：`scripts/adr09_e4_clean_env_check.sh` → 日志默认 `/tmp/aiplat-adr09-e4-clean-env/run-*.txt`  
- **内容**：宿主 ADR-10 烟测 + Gate3 phase=a；compose 有 daemon 才跑  

```bash
bash scripts/adr09_e4_clean_env_check.sh
```

## 本机归档（草案证据 · 非宣传）

| 字段 | 值 |
|------|-----|
| 时间（UTC） | `20261025T152952Z` |
| 归档 | [`RUNLOG/adr09-e4-clean-env-20261025T152952Z.txt`](./RUNLOG/adr09-e4-clean-env-20261025T152952Z.txt) |
| 宿主 ADR-10 | PASS · `report_id=rep-0bf667587df6` |
| Gate3 phase=a | PASS · aiplat-http smoke |
| compose one-shot | PASS · `report_id=rep-d4b5ffd5d359` · 随后 `down -v` |
| 生产默认 | 拒绝 `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` / `AIPLAT_ENTERPRISE=1` |

联签前须：产品/架构书面确认「可作 E4 证据」——本页与 RUNLOG **不**代替。
