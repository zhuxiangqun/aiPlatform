# docs/whitepaper/ — 白皮书目录

| 文件 | 角色 |
|------|------|
| [WHITEPAPER_SYSTEM.md](./WHITEPAPER_SYSTEM.md) | **五维白皮书体系**与权威源映射 |
| [whitepaper-suite.yaml](./whitepaper-suite.yaml) | 五卷 → 权威源机器清单 |
| [volumes/](./volumes/) | **五维分卷**（生成物：技术/产品/商业/生态/治理） |
| [cases/](./cases/) | 商业 ROI 案例附录（授权前可空） |
| [aiplat-platform-status-whitepaper.md](./aiplat-platform-status-whitepaper.md) | **平台现状总白皮书**（CAPABILITIES 全收录 + 对标/评级章） |
| [aiplat-l4-autonomy-assessment-v1.0.0.md](./aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性 L 级评估 ADR |
| [verification-protocol.md](./verification-protocol.md) | 白皮书/评估外部验证协议 |

```bash
python3 scripts/generate_platform_whitepaper.py
python3 scripts/generate_platform_whitepaper.py --check
python3 scripts/generate_whitepaper_volumes.py
python3 scripts/generate_whitepaper_volumes.py --check
```
