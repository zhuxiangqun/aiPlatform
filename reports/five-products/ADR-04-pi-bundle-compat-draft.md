# ADR-04 Pi 形态与 Bundle 兼容（草稿）

- **状态**：**Accepted（本切片）** · WP5 2026-10-23 · 含 export `*.mjs` 修复  
- **决策**：首切片 **Pi Thin**；Bundle 经 `export_pi_bundle`（`runtime-mode=thin`）；夹具 `fixtures/sample-app`。  
- **离线**：执行态见 `contracts/pi-thin-offline.md`；发布与诊断查 aiPlat **仍可依赖在线**。  
- **兼容**：`runtime_compat_range` + integrity；坏包安装前拒绝；`permission_claims` 不单独授权。  
- **回滚**：回滚 Bundle 版本优先于 Runtime。  
- **未采纳**：Enterprise 必经；厂内 Pi 主路径。  
- **重评**：改 Enterprise 子集；或夹具更换。
