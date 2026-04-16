# Round4 复审变更日志（持续交付｜历史记录）

> **历史报告**：本日志服务于 `reports/audit_findings_round4.json` 与对应 docx 复审报告，用于回溯当时修复项与验证命令；当前实现以最新代码与测试为准。

## 变更记录

### 2026-04-16
- 实施修复：
  - INFRA-DI-001：DI 容器启动时读取配置并执行 scan_packages 自动注册（@injectable），并按配置装配 interceptors（logging/timing/caching/metrics/error_handling）。
  - INFRA-OBS-001：observability 工厂接入 opentelemetry-sdk（provider=otel），支持 OTLP 导出（默认）与 in_memory 导出（测试），并补齐单测覆盖。
