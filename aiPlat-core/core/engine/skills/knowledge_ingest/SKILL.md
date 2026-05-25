---
name: knowledge_ingest
display_name: 知识库入库（文档）
description: 多模态知识库入库：PDF/扫描件→渲染→OCR→预算表结构化→写入多租户 SQLite（MVP）。
category: knowledge
version: 0.1.0
status: enabled
execution_mode: prompt
permissions:
  - kb:write
effects:
  - type: read
    resources: ["filesystem:~/.aiplat"]
    idempotent: true
    rollback_available: false
triggers:
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
    chunk_strategy:
      type: string
      description: 分块策略 — paragraph（按段落）、fixed_size（固定长度）、semantic（语义边界）。默认 paragraph。
    chunk_size:
      type: integer
      description: 每块最大字符数（默认 500，仅 fixed_size/semantic 生效）
    chunk_overlap:
      type: integer
      description: 相邻块重叠字符数（默认 50，保留上下文衔接）
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

## SOP
1. 确认文件路径、租户ID、集合ID、分块参数（chunk_strategy/chunk_size/chunk_overlap）
2. 文件预处理检查：
   - 扫描件检测：若为图像型 PDF（无内嵌文字），调用 OCR（参数见 input_schema.ocr_*）
   - 表格检测：若含表格，转 Markdown 表格格式后再索引
   - 时效检查：若文档修改时间超过 365 天，标记 metadata.age = "archived"
   - 版本检测：若文件名含日期或版本号，优先取最新版本
3. 文档分块：
   - paragraph 策略：按自然段落切分，保持语义完整
   - fixed_size 策略：按 chunk_size 字符硬切，chunk_overlap 保留上下文
   - semantic 策略：优先在句号/换行处分界，其次是 chunk_size 硬切
4. 调用 `kb_ingest` Tool 执行入库
5. 返回 doc_id、页数、预算表行数、分块数

## Tool
- `kb_ingest`: KBIngestTool (core/apps/tools/kb_tools.py)

