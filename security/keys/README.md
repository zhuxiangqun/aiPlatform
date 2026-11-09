# Artifact attest keys (P2-1)

| 文件 | 用途 |
|---|---|
| `mcp_plugin_allowlist.json` | MCP / 插件允许名单（发布门） |
| `artifact-manifest-ci.pub` | （可选）Ed25519 公钥；CI 验签 |

## 签名算法（写死）

1. **默认（已接线）**：HMAC-SHA256 over `sha256:<manifest_hash>`，密钥 `AIPLAT_ARTIFACT_MANIFEST_HMAC_SECRET`  
2. **可选升级**：Ed25519 over 同一字节串；私钥 `AIPLAT_ARTIFACT_MANIFEST_ED25519_SEED`（32-byte hex）或 key 文件；公钥本目录 `artifact-manifest-ci.pub` 或 `AIPLAT_ARTIFACT_MANIFEST_ED25519_PUB`

发布门：复算 hash → 验 signature → 缺 SBOM（prodish）或 allowlist 违规 → **拒绝发布**。
