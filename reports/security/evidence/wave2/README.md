# Wave 2 — Authz pilot → D26

> 工程约束已接线；真人样本与双签仍是 Ops。≠ `security_certification`

## 硬条件

1. 每样本固定 `sample_id` + `git_commit` + `build_id`
2. `crud` / `report` 各 ≥3 独立 pass（负向阻断）
3. `security_owner` + `product_security` 双签后 `evaluate_pilot_exit.status=passed`
4. **仅此时**允许将 SoT D26 `I`→`E` 并清空 gap（禁止只改 YAML）

```bash
# 探针并记账（pass 必须带 pin）
python3 scripts/security_authz_pilot_cli.py --probe \
  --base-url https://staging.example/app \
  --app-type crud --sample-id crud-001 \
  --git-commit "$(git rev-parse HEAD)" --build-id build-001 \
  --record

# 双签
python3 scripts/security_authz_pilot_cli.py --approve --owner "…" --role security_owner
python3 scripts/security_authz_pilot_cli.py --approve --owner "…" --role product_security

# 升 D26 前闸（--propose-e 在未双签时 exit 1）
python3 scripts/security_d26_promote_check.py
python3 scripts/security_d26_promote_check.py --propose-e

python3 scripts/security_wave_ops.py --wave2
```

| 资产 | 说明 |
|---|---|
| [`pilot-sample-template.json`](./pilot-sample-template.json) | 样本记账字段模板 |
| [`d26-promote-card.md`](./d26-promote-card.md) | 升 E 人审卡（填完后才改 YAML） |
