# Org L5 Live Unlock — 书面解锁意图（模板）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ORG-L5-LIVE-UNLOCK` |
| 版本 | **v0.1 模板** |
| 状态 | ☐ 未签 · UNLOCK_STATUS: unsigned |

> 将上一行改为 `UNLOCK_STATUS: signed` 并完成下表签字后，配合 `AIPLAT_ORG_IO_LIVE_UNLOCK=1` 表示意图确认。  
> 出站还须：`AIPLAT_ORG_IO_MODE=live`、`connector.live.enabled=true`、主机白名单、基址。缺任一则 `live_io_enabled=false`。  
> **仍不是 M4**：不开放任意 SQL；人工签收前不得称组织级 L5。

## 签字

| 角色 | 姓名 | 日期 | 同意「暂不接生产写、仅沙箱/只读图」 |
|------|------|------|--------------------------------------|
| 产品 | | | ☐ |
| 工程 | | | ☐ |
| 客户对接 | | | ☐ |

## 目标系统（规划，非已接线）

- 系统名：________________  
- 环境：sandbox / staging / prod（圈选）  
- 回滚负责人：________________  

## 关闭条件（未来 live adapter PR）

1. 专用 adapter 白名单（禁任意 SQL）  
2. PolicyGate + dry-run 默认  
3. 审计字段齐全  
4. 决策记录新开 D-live 并合入
