---
name: doc_ingest
display_name: 资料导入与解析
description: 通用资料导入（本地文件/URL）并解析为统一内容元素（kb_elements），支持异步 job、资产落地与后续对话检索（MVP 先支持 PDF）。
category: document
version: 0.1.0
skill_kind: executable
permissions:
  - doc:write
auto_trigger_allowed: false
requires_approval: true
trigger_conditions:
  - 导入资料
  - 解析文档
  - 分析资料
input_schema:
  type: object
  properties:
    tenant_id: {type: string, description: 租户ID（默认 default）}
    collection_id: {type: string, description: 集合ID（默认 default）}
    file_path: {type: string, description: 本地文件绝对路径（优先 PDF）}
    url: {type: string, description: 远程 URL（下载后解析）}
    kind: {type: string, description: pdf|docx|xlsx|pptx|video（MVP 先支持 pdf/url->pdf）}
    ocr_lang: {type: string, description: OCR 语言（默认 zh）}
    ocr_engine: {type: string, description: tesseract|paddleocr|auto（默认 auto）}
    dpi: {type: integer, description: PDF 渲染 DPI（默认 240）}
    max_pages: {type: integer, description: 最多处理页数（默认 60）}
  required: []
output_schema:
  type: object
  properties:
    tenant_id: {type: string}
    collection_id: {type: string}
    doc_id: {type: string}
    job_id: {type: string}
---
