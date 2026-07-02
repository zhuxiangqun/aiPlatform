---
execution_type: prompt
name: e2e_test
display_name: E2E 测试自动生成
description: 输入任意URL，自动探索站点、生成Playwright测试套件、运行测试、修复失败、补充覆盖。涉及代码生成和测试审查。 涉及测试用例相关操作。
  主要进行生成。
version: 1.0.0
category: execution
status: enabled
triggers:
  - 端到端测试
  - e2e test
  - 全链路测试
effects:
- type: both
  resources:
  - browser:page
  - filesystem:write
  idempotent: false
  rollback_available: true
output_schema:
  result:
    type: string
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - E2E测试
  - 端到端测试
  - 自动化测试用例
  - 集成测试生成
  - 站点遍历测试
  - 站点测试
  - 全链路测试
  - 自动化遍历
  keywords:
    objects:
    - 测试用例
    - Playwright
    - 自动化
    actions:
    - 生成
    - 运行
    - 修复
    - 补充
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 自动发现站点功能并生成 E2E 测试套件
sop_flow:
  - E2E Test 自动生成
  - 对任何 Web 应用自动生成完整的 Playwright E2E 测试套件
  - 使用 browser 进行浏览器自动化
  - 使用 file_operations 保存测试代码
  - 使用 code_execution 运行 Playwright 测试
  - 生成 goto / wait / list_elements / click_index / type_index / screenshot 操作序列
input_schema:
  url:
    type: string
    required: true
    description: 测试站点URL
protected: true
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个可执行的验证步骤
  2. 测试覆盖 happy path + 至少一个边界 case
  3. red-capable command 已确认能稳定复现目标行为
keywords:
  objects:
  - 测试用例
  - E2E
  - 端到端
  - 页面
  actions:
  - 测试
  - 验证
  - 检查
  constraints:
  - 浏览器
  - 页面路径
trigger_conditions:
- when: 用户要求端到端测试
  query: E2E测试/端到端/浏览器测试
- when: 不应用场景
  description: 跳过条件：用户仅讨论测试策略而非实际执行测试时不触发。
skip_when: 跳过条件：用户仅讨论测试策略而非实际执行测试时不触发。
---



# E2E Test 自动生成

## 目标
对任何 Web 应用自动生成完整的 Playwright E2E 测试套件。

## 可用工具
- `browser` — 浏览器自动化（goto / list_elements / click_index / type_index / screenshot / extract / get_text 等）
- `file_operations` — 读写文件（保存测试代码）
- `code_execution` — 执行命令（运行 Playwright）

## 工作流程（SOP）

### 阶段 1：探索站点
1. `{"tool":"browser","args":{"action":"goto","url":"目标URL"}}` — 打开目标页面
2. `{"tool":"browser","args":{"action":"wait","ms":2000}}` — 等待加载
3. `{"tool":"browser","args":{"action":"list_elements","max_items":30}}` — 发现页面元素
4. `{"tool":"browser","args":{"action":"screenshot"}}` — 截图记录页面状态
5. 如果页面有导航链接，依次探索子页面，重复步骤 1-4

### 阶段 2：生成测试
为每个关键页面/流程生成 Playwright `.spec.ts` 测试代码。测试代码必须包含：
```typescript
import { test, expect } from '@playwright/test';

test('页面核心流程', async ({ page }) => {
  await page.goto('URL');
  // 交互步骤（根据 list_elements 结果编写）
  // await page.fill(selector, value);
  // await page.click(selector);
  // await page.waitForTimeout(2000);
  await expect(page).toHaveURL(/expected/);  // 或 screenshot 验证
});
```

### 阶段 3：写入文件
1. 使用 `file_operations` 创建目录 `tests/`（如果在工作区）
2. 将测试代码写入 `tests/{page_name}.spec.ts`
3. 创建或追加 `playwright.config.ts`（基本配置）

### 阶段 4：运行测试
1. `{"tool":"code_execution","args":{"code":"npx playwright test --reporter=list","language":"bash"}}`
2. 收集输出：通过/失败数量、失败详情

### 阶段 5：修复失败
如果有测试失败：
1. 分析错误信息（超时、选择器不存在、断言不匹配等）
2. 使用 `file_operations` 读取失败的测试文件
3. 根据错误修正测试代码：
   - 选择器不对 → 用 list_elements 重新确认索引
   - 超时 → 增加 wait 或 waitForSelector
   - 断言不对 → 修正 expect 条件
4. 重新运行测试（阶段 4）

### 阶段 6：补充覆盖
- 检查步骤 1 探索到的页面，哪些还没有测试
- 为未覆盖的页面生成新测试
- 重复阶段 3→4→5→6

## 停止条件
- ✅ 全部测试通过
- 达到最大迭代次数（默认 10）
- 连续 3 轮无进展（失败数不降）

## 输出格式
完成后输出：
```
E2E Test Suite 生成完成
- 测试文件: tests/login.spec.ts, tests/dashboard.spec.ts
- 测试用例: 5 个
- 通过: 5/5
- 失败: 0
- 迭代: 3 轮
```

## 反模式
- ❌ 不要跳过 list_elements 直接猜测选择器
- ❌ 不要盲目加 wait（尽量用 waitForSelector）
- ❌ 不要为纯静态页面生成过多测试
- ❌ 修复失败时不要重写整个测试文件，只改出错部分

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注