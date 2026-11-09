# 成果物威胁模型（PR2 · 默认 off）

> 模板：`security/templates/artifact_threat_model.v1.yaml`  
> 实现：`aiPlat-platform/builder/artifact_security_manifest.py`  
> **≠** `security_certification`

---

## 规则（已钉死）

1. 文件名：`THREAT_MODEL.yaml`（或 `threat_model.yaml`）放在成果物根目录。  
2. Hash：文档 → **canonical JSON**（`sort_keys`、UTF-8、`separators=(",",":")`）→ SHA-256 → `threat_model_hash`（纳入 manifest 签名）。  
3. `approved=true` 必须：`reviewer_role ∈ {security_owner, product_security, independent_qa}` 且 `reviewed_by ≠ owner`（禁自批）。  
4. `top_threats` / `mitigations` / `out_of_scope` 非空；`approved=false` → fail。  
5. 默认 **不**强制：`AIPLAT_REQUIRE_THREAT_MODEL` 未设时 `na` 可发布；设为 `1` 时必须 `pass`（`na` 永不算 pass）。  
6. 损坏/逃逸路径/软链出根 → `fail`，即使用户未开 require 也阻断。

---

## 用法

```bash
cp security/templates/artifact_threat_model.v1.yaml /path/to/artifact/THREAT_MODEL.yaml
# 填写后由非 owner 的 security reviewer 批准
```

Pilot 强制与 legacy `na` 到期（30 天 ISO-8601）在 **PR3** 接线。

---

## 诚实锁

有模板 ≠ 有威胁模型；有 hash ≠ 认证；默认 off ≠ 生产已强制。
