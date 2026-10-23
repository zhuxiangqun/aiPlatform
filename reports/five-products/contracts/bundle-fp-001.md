# 契约草案 bundle-fp-001

| 项 | 内容 |
|----|------|
| 状态 | 启用 · 草案 |
| 字段 | bundle_id, schema_version, source_asset_ids[], asset_versions[], runtime_compat_range, permission_claims[], model_requirements, build_info, integrity, rollback_hint |
| 生产者 | aiPlat `scripts/export_pi_bundle.py` / Builder export |
| 消费者 | Pi 安装加载 |
| 夹具 | `packages/aiplat-pi-runtime/fixtures/sample-app` |
| 错误 | 坏包/篡改/不兼容 → 安装前拒绝 |
| 验收 | permission_claims 不能单独授权；export 产出含 integrity/build 元数据 |
| 证据 | 2026-10-23 sample-app export PASS → `/tmp/aiplat-fp-wp0-sample` |
| owner | aiPlat 临时 R |
