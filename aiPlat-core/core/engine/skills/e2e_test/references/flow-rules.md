# E2E 业务流程规则（flow-rules）

## 何时用 flow

多步业务路径（goto → login → click/fill → expect_url）用 `action=flow`（或 auto 且能解析出 steps）。
单页冒烟用默认 recon scaffold。

## 步骤种类

| action | 含义 |
|--------|------|
| goto | 打开 URL，随后 `list_elements` |
| login | 同页快照取 username/password/submit，禁止臆造定位 |
| click / fill | 目标必须在本步 `action_elements`（pre-action snapshot）中 |
| expect_url | URL/path 片段断言 |
| recon | 仅侦察 |

## 硬约束

1. `parse_flow` / `scaffold_flow_spec` 驱动；定位来自每步侦察，禁止离线发明选择器。
2. 快照缺失时写入 `MISSING_SNAPSHOT_TARGET` 注释并失败（refuse inventing locator）。
3. 交付须带每步 `list_elements` 证据；seal 经 `validate_e2e_deliverable` 否决不合格交付。

## 调用示例

```json
{"action": "flow", "url": "https://example.com/login", "username": "u", "password": "p"}
```
