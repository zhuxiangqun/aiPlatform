# 五产品首切片落地收口（2026-10-24）

> 授权范围（L1 + Gate1 修订）内工作已合入 main；**Gate 2 仍未批**。

## 已合入（摘要）

| 项 | 证据 |
|----|------|
| 首切片 WP0–WP5 / E3 | PR [#381](https://github.com/zhuxiangqun/aiPlatform/pull/381) → `5bfdb86` |
| MB-02 models 模板 | [#382](https://github.com/zhuxiangqun/aiPlatform/pull/382) |
| MB-05 emit opt-in | [#383](https://github.com/zhuxiangqun/aiPlatform/pull/383) |
| MB-01 再核实 + MB-03 RFC + MB-04 清单 | [#384](https://github.com/zhuxiangqun/aiPlatform/pull/384) |
| inflation 豁免退役 | PR [#385](https://github.com/zhuxiangqun/aiPlatform/pull/385) → `a4c4e0c`：`exemptions: []` |

## 明确未做 / 未批

| 项 | 状态 |
|----|------|
| Gate 2 / D13 | 维持不进入（见 `GATE2_RECOMMENDATION.md`） |
| MB-01 core 解耦实施 | 须 Gate 2 |
| MB-03 存储迁移实现 | 须另签 RFC |
| MB-04 正式 R 签字 | 清单已备；临时 R 继续有效（见下） |
| Gate 3 / 拆部署 / 对外产品化 | 未授权 |

## 临时 R 延期（组织）

在 `MB04_OWNER_TRANSFER.md` §3 签字表填满之前，继续采用 `ROLES.md` / `L1_AUTHORIZATION.md` 的兼任与临时 R。  
**本延期 ≠ Gate 2 批准。**

## 运维备忘

- 本机 Pi 告警：`~/.pi/agent/models.json` 须含实际 `ollama list` id（模板见 `packages/aiplat-pi-runtime/models.json.example`）  
- 证据发射：`AIPLAT_SLICE_EVIDENCE=1`（默认关）  
