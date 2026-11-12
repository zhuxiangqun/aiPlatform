---
doc_type: Report
---

# 逐篇事实审核台账

## 审核维度

1. 实现事实：文档说已实现/已接线，代码与测试是否存在；
2. 路径/接口/命令：是否真实存在；
3. 数字：是否有可复现来源；
4. 状态/版本/日期：当前状态与生效时间；
5. 权威边界：canonical 与派生是否混用；
6. 商业/客户声明：是否有授权与证据。

## 结论枚举

```text
pass          未发现矛盾
fix           存在可修正的事实错误
needs-owner   需要 owner 提供外部证据
```

## 批次

- Batch 01：`docs/standards/` + `docs/contracts/` + `docs/architecture/`
