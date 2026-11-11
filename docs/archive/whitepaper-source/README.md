---
doc_type: Index
---

# docs/whitepaper/ — 白皮书目录

> **Batch C3**：生成物已迁移到 `reports/whitepapers/`（历史链接失效）。本目录旧生成物标记为 deprecated，仅保留迁移期。

| 文件 | 角色 |
|------|------|
| [WHITEPAPER_SYSTEM.md](../../reference/explanatory/WHITEPAPER_SYSTEM.md) | **五维白皮书体系**与权威源映射 |
| [whitepaper-suite.yaml](../../reference/explanatory/whitepaper-suite.yaml) | 五卷 → 权威源机器清单 |
| archive/whitepaper-generated/（历史链接失效） | 旧生成物（只读归档） |
| cases/（历史链接失效） | 商业 ROI 案例附录（授权前可空） |
| reports/whitepapers/（历史链接失效） | **平台现状总白皮书 + 五维分卷（当前生成物）** |
| [aiplat-l4-autonomy-assessment-v1.0.0.md](../../decisions/architecture/aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性 L 级评估 ADR |
| verification-protocol.md（历史链接失效） | 白皮书/评估外部验证协议 |

```bash
python3 scripts/generate_platform_whitepaper.py
python3 scripts/generate_platform_whitepaper.py --check
python3 scripts/generate_whitepaper_volumes.py
python3 scripts/generate_whitepaper_volumes.py --check
```
