# Pi D3 — Bundle 完整性（骨架）

> 本地演练级；生产策略由运维在 live 后签字升 ✅。

1. 安装/升级前校验 `agent_manifest.json` 存在与必填字段。  
2. 可选：对 Bundle 目录计算 checksum 清单（离线可关）。  
3. 失败：拒绝切换 `bundles/current`；保留上一版本。  

本地演练：`d3_local_rehearsal.sh`（manifest 存在性 + checksum 文件 roundtrip）。
