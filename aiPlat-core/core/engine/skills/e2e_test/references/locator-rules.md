# E2E 定位规则（locator-rules）

## 原则

1. **先侦察再写定位**：每次进入新页面先 `list_elements`（与 `click_index` / `type_index` 共用 `__aiplatCollectDom`）。
2. **语义定位优先**：生成 Playwright 用例只用 `getByRole` / `getByLabel` / `getByText` / `getByTestId`。
3. **禁止改绑**：不得在失败后静默换成 CSS class / xpath / 猜测选择器；新定位必须出现在当前 `list_elements` 快照中。
4. **定位变更回执**：若确需改定位，输出 `## 定位变更回执`，字段齐全：`旧` / `新` / `依据`（依据须引用本轮侦察）。

## 禁止

- `waitForTimeout` / xpath / `page.$('//...')` / class 选择器（`.foo`）
- 在 `.spec.ts` 中出现 `click_index` / `type_index`（索引仅用于 live recon）
- 无侦察证据的“自愈改绑”

## 自检

- [ ] 用例正文含 `list_elements` / 侦察 / `__e2e_recon__` 证据
- [ ] 若改过定位，已写 `## 定位变更回执`
