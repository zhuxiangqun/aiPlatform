# D26 升 E 人审卡（Wave2）

> 禁止只改 `security_quality_dimensions.yaml`。须先双签 + 本卡。

| 字段 | 值 |
|---|---|
| 日期 (UTC) | |
| pilot ledger 路径 | |
| crud pass 样本 IDs | （≥3，含 git_commit/build_id） |
| report pass 样本 IDs | （≥3） |
| `security_d26_promote_check.py --propose-e` | exit 0？ |
| security_owner 签 | |
| product_security 签 | |
| 变更单 / PR | |
| 结论 | 允许升 E / 拒绝 |

升 E 后：清空 D26 `gap`，`release_blocking` 按证据改为 false（仅当负向与 TM 齐备）。
