# 成果物威胁模型（PR2+PR3）

> 模板：`security/templates/artifact_threat_model.v1.yaml`  
> 实现：`aiPlat-platform/builder/artifact_security_manifest.py`  
> **≠** `security_certification`

---

## 硬规则

1. 文件：`THREAT_MODEL.yaml` 在成果物根目录。  
2. Hash：canonical JSON → SHA-256 → `threat_model_hash`（进 manifest 签名）。  
3. `approved=true`：`reviewer_role ∈ {security_owner, product_security, independent_qa}` 且 `reviewed_by ≠ owner`。  
4. `top_threats` / `mitigations` / `out_of_scope` 非空。  
5. **`crud` / `report`（P0-3b pilot）必须 `threat_model.status=pass`**，`na` 不算 pass。  
6. Legacy 非 pilot：`na` 须 `na_reason` + `expires_at`（ISO-8601 UTC，默认 30 天）；过期阻断。  
7. `AIPLAT_REQUIRE_THREAT_MODEL=0` **仅 development** 放行；staging/prod 仍强制。  
8. 路径逃逸/软链出根 / `fail` → 即使用户未开 require 也阻断。

---

## Pilot 退出（与 authz 对齐）

```text
范围：crud / report 各 ≥3 样本
通过：threat_model.pass + authz_smoke.pass + hash 匹配
退出：security_owner + product_security 双签
```

```bash
python3 scripts/security_authz_pilot_cli.py --approve \
  --owner "Security Owner" --role security_owner --note "exit"
python3 scripts/security_authz_pilot_cli.py --approve \
  --owner "Product Security" --role product_security --note "exit"
```

---

## 发布门与覆盖矩阵

```bash
# 成果物发布前（发布门）
python3 scripts/security_dimensions_report.py --strict-gaps
```

默认 CI 工程收口只要求 `schema_ok`；**`--strict-gaps` 必须进发布 checklist**。

---

## 诚实锁

有模板 ≠ 有威胁模型；schema 绿 ≠ coverage 绿 ≠ 认证。
