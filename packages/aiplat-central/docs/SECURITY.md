# Central admin / security baseline (D2+)

> Thin checklist — not a full SOC2 pack.  
> Baseline: [`../security/baseline.yaml`](../security/baseline.yaml)

```bash
bash packages/aiplat-central/scripts/d2_security_check.sh
```

Covers: Core/Platform token middleware presence, admin MFA gate for API keys, Pi Thin enterprise-off default, FDE prep `production_field=false`, Central healthz product_id.
