---
name: poc_data_inject
version: 1.0.0
category: fde
execution_type: handler
description: POC 客户数据快速注入——支持 PDF/图片/CSV/Excel/TXT/Markdown, 自动路由到对应解析器 (FDE POC)
input_schema:
  type: object
  properties:
    file_paths:
      type: array
      items: {type: string}
      description: 待注入文件的绝对路径列表
    profile:
      type: string
      description: 目标 POC Profile 名称 (如 poc-manufacturing)
      default: poc-general
output_schema:
  type: object
  properties:
    status: {type: string, enum: [success, partial, error]}
    records: {type: integer, description: 成功注入的记录/页数}
    errors: {type: array, items: {type: string}}
effects:
  - type: write
    resources: ["filesystem:~/.aiplat/kb/poc"]
    idempotent: false
    rollback_available: true
  - type: read
    resources: ["filesystem:~/.aiplat/kb/poc"]
    idempotent: true
    rollback_available: false
---

# POC 数据注入

将客户现场提供的文件快速注入到 aiPlat 知识库中, 支持 6 种文件格式自动路由:

| 格式 | 解析器 | 说明 |
|:---|:---|:---|
| .pdf / .png / .jpg / .jpeg | InfraOCRAdapter (Tesseract/PaddleOCR) + PyMuPDF rendering | OCR 解析 (纯 core) |
| .csv | 内置 CSV 解析 | pandas.read_csv → 结构化文本 |
| .xlsx / .xls | 内置 Excel 解析 | pandas.read_excel → 结构化文本 |
| .txt / .md | 内置文本解析 | 直接读取 → 存储到 kb/poc |
