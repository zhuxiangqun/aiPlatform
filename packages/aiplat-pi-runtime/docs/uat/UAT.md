# Pi Thin — D3 local UAT

> 本地验收；**不是** `d3_production` 授权。详见 `d3_local_closeout.sh`。

| # | 步骤 | 本地命令 / 证据 |
|---|------|----------------|
| 1 | D2 admin | `d2_admin_check.sh` |
| 2 | Bundle / SOC / N-1 rehearse | `d3_local_rehearsal` · `d3_soc_local_rehearsal` · `d3_n1_local_rehearsal` |
| 3 | Prep | `d3_prep_check.sh` |
| 4 | Authorize REFUSE | `d3_authorize.sh authorize` |
| 5 | Closeout | [`PI_D3_LOCAL_CLOSEOUT.md`](../../../reports/five-products/ops/PI_D3_LOCAL_CLOSEOUT.md) |

一键：`bash packages/aiplat-pi-runtime/scripts/d3_local_acceptance.sh`
