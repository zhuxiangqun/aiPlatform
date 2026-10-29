# E2E 等待规则（waiting-rules）

## 原则

1. **优先状态等待**：`expect(...).toBeVisible()` / `toHaveURL` / `waitForSelector` 语义等待。
2. **禁止盲等**：生成用例中禁止 `waitForTimeout` / `page.waitForTimeout`。
3. **Live recon 例外**：handler 内短 `session.wait(ms)` 仅用于 DOM 稳定后再次 `list_elements`，不得写入 spec。

## 失败处理

- 超时 → 重新 `list_elements`，核对语义名是否仍在快照中
- 不得通过加长固定 sleep 掩盖定位错误
- 选择器失效走「定位变更回执」，禁止改绑到脆弱 CSS

## 自检

- [ ] `.spec.ts` 无 `waitForTimeout`
- [ ] 导航后有可见性或 URL 断言
