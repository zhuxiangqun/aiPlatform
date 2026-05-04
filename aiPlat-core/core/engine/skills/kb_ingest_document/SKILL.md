---
name: kb_ingest_document
display_name: 知识库入库（文档）
description: 多模态知识库入库：PDF/扫描件→渲染→OCR→预算表结构化→写入多租户 SQLite（MVP）。
category: knowledge
version: 0.1.0
skill_kind: executable
permissions:
  - kb:write
auto_trigger_allowed: false
requires_approval: true
trigger_conditions:
  - 入库文档
  - 上传到知识库
  - 解析PDF并索引
  - 扫描件OCR入库
input_schema:
  type: object
  properties:
    tenant_id:
      type: string
      description: 租户ID（多租户隔离）
    collection_id:
      type: string
      description: 知识库集合ID（默认 default）
    collection_name:
      type: string
      description: 可选：集合展示名
    file_path:
      type: string
      description: 待入库文件绝对路径（PDF 优先）
    kind:
      type: string
      description: 文件类型（默认 pdf）
    ocr_lang:
      type: string
      description: OCR 语言（默认 zh）
    ocr_engine:
      type: string
      description: paddleocr|tesseract|auto（默认 auto）
    dpi:
      type: integer
      description: PDF 渲染 DPI（默认 240）
    max_pages:
      type: integer
      description: 最多处理页数（默认 60）
  required: [file_path]
output_schema:
  type: object
  properties:
    tenant_id: {type: string}
    collection_id: {type: string}
    doc_id: {type: string}
    pages: {type: integer}
    budget_rows: {type: integer}
    budget_pages:
      type: array
      items: {type: integer}
    assets_dir: {type: string}
---

# 知识库入库（文档）

## 说明
这是 A 阶段 MVP：先支持 PDF/扫描件 OCR 入库，并对“投资预算”类表格做结构化抽取写入 SQLite（多租户隔离）。

## 输出
返回 `doc_id`、页数、以及抽取到的预算表行数等信息。

