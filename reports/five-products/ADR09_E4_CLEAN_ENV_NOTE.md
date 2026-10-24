# ADR-09 前置 #5 · E4 干净环境验收（草案脚手架）

- **状态**：**草案** · 2026-10-25 — 脚本可跑；**≠** E4 对外批准；**≠** ADR-09 Accepted  
- **脚本**：`scripts/adr09_e4_clean_env_check.sh` → 日志默认 `/tmp/aiplat-adr09-e4-clean-env/run-*.txt`  
- **内容**：宿主 ADR-10 烟测 + Gate3 phase=a；compose 有 daemon 才跑  

```bash
bash scripts/adr09_e4_clean_env_check.sh
```

联签前须：独立环境报告归档 + 产品/架构书面确认「可作 E4 证据」——本页不代替。
