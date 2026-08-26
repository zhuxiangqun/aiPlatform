#!/usr/bin/env python3
"""Find design docs with last_synced older than threshold (extracted from docs-verify.yml).

2026-08-26: 从 workflow 内嵌 Python 抽出（YAML literal block 内多行字符串缩进破坏解析——
"低自由度执行下沉脚本" 原则）。用法: python3 scripts/verify_doc_stale.py [DAYS]
"""
import os
import re
import sys
import time
from datetime import datetime

design_dir = 'docs/design'
if not os.path.isdir(design_dir):
    sys.exit(0)

days = int(sys.argv[1] if len(sys.argv) > 1 else os.getenv("AIPLAT_DOC_DESIGN_STALE_DAYS", "90"))
now = time.time()
stale = []
for f in os.listdir(design_dir):
    if not f.endswith('.md'):
        continue
    fp = os.path.join(design_dir, f)
    with open(fp, encoding="utf-8") as fh:
        c = fh.read()
    m = re.search(r'(?:last_synced|最后更新)[:：]\s*(\d{4}-\d{2}-\d{2})', c)
    if not m:
        continue
    dt = datetime.strptime(m.group(1), '%Y-%m-%d')
    age = (now - dt.timestamp()) / 86400
    if age > days:
        stale.append(f'{f} ({m.group(1)}, {age:.0f}d)')
if stale:
    print('\n'.join(stale))
