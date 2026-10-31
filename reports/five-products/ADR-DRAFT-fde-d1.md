# ADR-DRAFT — FDE → D1（进程/DB 独立）

> **状态**：Draft · **非 Accepted** · P0 W2  
> **当前允许**：D1c only

## 动机

交付/验收工作台与平台控制面解耦，便于按客户环境独立升级。

## 非目标

- 不拆 harness 内核进 FDE 仓
- 不在 D1c 阶段宣称「独立部署」

## D1c → D1 门槛

1. 项目/验收 API 契约冻结 + 契约测试  
2. 独立项目/验收 schema  
3. UI 与 API 可单 Chart 部署  
4. 依赖诊断/Pi 仅经版本化 API（N-1）  
5. 联签 Accepted  

## 回滚

共置 `platform/apps/fde`；停独立 Chart。
