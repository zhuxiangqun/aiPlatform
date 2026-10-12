#!/usr/bin/env python3
"""Generate the aiPlat platform status whitepaper from AIPLAT_CAPABILITIES.md.

Authority model
---------------
- Capability inventory truth: AIPLAT_CAPABILITIES.md (+ capability_registry.yaml)
- This whitepaper is a *readable packaging* of that inventory plus architecture pointers.
- Do NOT hand-edit capability tables in the output — re-run this script.

Usage
-----
  python3 scripts/generate_platform_whitepaper.py
  python3 scripts/generate_platform_whitepaper.py --check   # exit 1 if stale
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAPS = REPO / "AIPLAT_CAPABILITIES.md"
OUT = REPO / "docs" / "whitepaper" / "aiplat-platform-status-whitepaper.md"
OVERVIEW = REPO / "docs" / "architecture" / "overview.md"
AUTONOMY = REPO / "docs" / "whitepaper" / "aiplat-l4-autonomy-assessment-v1.0.0.md"

MARKER_BEGIN = "<!-- BEGIN_GENERATED_FROM_AIPLAT_CAPABILITIES -->"
MARKER_END = "<!-- END_GENERATED_FROM_AIPLAT_CAPABILITIES -->"
STAMP_RE = re.compile(
    r"<!-- whitepaper_stamp source_sha256=([0-9a-f]+) total_capabilities=(\d+) -->"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    end = raw.find("\n---", 3)
    if end < 0:
        return {}, raw
    fm_text = raw[3:end].strip()
    body = raw[end + 4 :].lstrip("\n")
    meta: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line or line.startswith(" ") or line.startswith("-"):
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in ("total_capabilities", "version", "last_updated", "scan_hash"):
            meta[k] = v
    return meta, body


def _extract_stats_table(body: str) -> str:
    m = re.search(r"## 统计\s*\n+(.*?)(?:\n---|\n\*最后更新|\Z)", body, re.S)
    if not m:
        return "_(统计表未在 CAPABILITIES 中找到)_"
    block = m.group(1).strip()
    # Keep first markdown table under ## 统计 (AUTO-STATS)
    lines = []
    in_table = False
    for line in block.splitlines():
        if line.strip().startswith("|"):
            in_table = True
            lines.append(line)
        elif in_table:
            break
    return "\n".join(lines) if lines else block[:2000]


def _count_marks(body: str) -> tuple[int, int, int]:
    ok = len(re.findall(r"✅", body))
    warn = len(re.findall(r"⚠️", body))
    # table rows that look like capability rows (rough)
    rows = len(re.findall(r"^\| [^|]+ \| [^|]+ \| [✅⚠️]", body, re.M))
    return ok, warn, rows


def _section_index(body: str) -> list[tuple[str, str]]:
    """Return list of (anchorish title, heading line) for ## numbered sections."""
    out = []
    for m in re.finditer(r"^(## .+)$", body, re.M):
        title = m.group(1).strip()
        if title.startswith("## 更新规则") or title.startswith("## 系统架构"):
            continue
        out.append((title, title))
    return out


def build(raw_caps: str) -> str:
    meta, body = _parse_frontmatter(raw_caps)
    total = str(meta.get("total_capabilities") or "")
    version = str(meta.get("version") or "")
    last_updated = str(meta.get("last_updated") or "")
    source_sha = _sha256(raw_caps)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok_n, warn_n, row_n = _count_marks(body)
    stats = _extract_stats_table(body)
    sections = _section_index(body)

    toc_lines = []
    for i, (title, _) in enumerate(sections, 1):
        # strip leading ##
        label = title[3:].strip() if title.startswith("## ") else title
        toc_lines.append(f"{i}. {label}")

    overview_note = (
        f"见 [`docs/architecture/overview.md`](../architecture/overview.md)"
        if OVERVIEW.is_file()
        else "（架构全景文档缺失）"
    )
    autonomy_note = (
        f"见 [`aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md)"
        if AUTONOMY.is_file()
        else "（自主性评估文档缺失）"
    )

    narrative = f"""---
title: "aiPlat 平台现状白皮书"
type: platform-status-whitepaper
authority: derived-from-capabilities
status: generated
generated_at: "{generated_at}"
source: AIPLAT_CAPABILITIES.md
source_sha256: "{source_sha}"
total_capabilities: {total or "unknown"}
capabilities_version: "{version}"
capabilities_last_updated: "{last_updated}"
language: zh-CN
---

<!-- whitepaper_stamp source_sha256={source_sha} total_capabilities={total or 0} -->

# aiPlat 平台现状白皮书

> **本文是可再生成的平台现状说明书，不是第二真相源。**  
> 能力清单唯一权威：仓库根目录 [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md)  
> 机器登记：[`aiPlat-core/core/capability_registry.yaml`](../../aiPlat-core/core/capability_registry.yaml)  
> 重新生成：`python3 scripts/generate_platform_whitepaper.py`  
> 新鲜度校验：`python3 scripts/generate_platform_whitepaper.py --check`

## 0. 阅读约定与权威模型

| 问题 | 以谁为准 |
|------|----------|
| 平台有哪些能力、是否已接线 | **AIPLAT_CAPABILITIES.md**（本文第 3 章为其完整收录） |
| 架构分层与依赖方向 | `docs/architecture/overview.md` + 各仓 `CLAUDE.md` |
| 自主性定级（L5 等） | `docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md`（评估，非整库能力表） |
| 设计目标 vs 现状 | 代码与 CAPABILITIES；设计文档冲突时以代码为准 |

**生成元数据**

| 字段 | 值 |
|------|-----|
| 生成时间 (UTC) | `{generated_at}` |
| 源文件 SHA-256 | `{source_sha}` |
| CAPABILITIES version | `{version or "—"}` |
| CAPABILITIES last_updated | `{last_updated or "—"}` |
| frontmatter total_capabilities | `{total or "—"}` |
| 文中 ✅ 计数 | {ok_n} |
| 文中 ⚠️ 计数 | {warn_n} |
| 能力表行（估） | {row_n} |

## 1. 平台定位（现状摘要）

aiPlat 是企业级 AI **操作系统式平台**：以 Harness 为执行内核，叠加记忆、本体/知识、编排、治理与可观测，而不是「又一个 Agent 框架」。

**仓库分层（依赖单向：app → platform → core → infra）**

| 层 | 仓库 | 职责 |
|----|------|------|
| L3 应用接入 | `aiPlat-management` / `aiPlat-app` | 管理端 UI、应用接入 |
| L2 平台服务 | `aiPlat-platform` | 网关、鉴权、Builder、业务应用 API |
| L1 AI 核心 | `aiPlat-core` | Pipeline / ReAct / Memory / Knowledge / Syscalls |
| L0 基础设施 | `aiPlat-infra` | 模型目录、LLM/Embedding 客户端、存储网络 |

架构全景：{overview_note}  
自主性评估（L 级定级，**不等于**能力全表）：{autonomy_note}

**交付与运行时边界（摘录）**

- 工厂内：完整治理（PolicyGate / Memory / SECI / 知识 syscall 等）在 aiPlat。
- 厂外薄 Runtime（Pi Package）：SOP + skills + handler 快照，**不**等同平台 Agent 全能力；厚度不足须厚运行时或混合回连。详见 `docs/architecture/plans/pi-thin-runtime.md`。

## 2. 能力统计总表

以下表格从 `AIPLAT_CAPABILITIES.md`「统计」节抽取（生成时原文复制）：

{stats}

## 3. 完整能力清单（由 CAPABILITIES 生成收录）

下列章节为源文件正文能力表的**完整收录**（自「系统架构」或「一、Harness」起至文末统计之前的主体；含全部子系统表）。  
**请勿手工改本章**——改能力请改 `AIPLAT_CAPABILITIES.md` 后重新运行生成器。

### 3.1 子系统目录

"""
    narrative += "\n".join(toc_lines) + "\n\n"
    narrative += MARKER_BEGIN + "\n\n"
    # Include body starting from first major content heading
    start = body.find("## 系统架构")
    if start < 0:
        start = body.find("## 一、")
    if start < 0:
        start = 0
    narrative += body[start:].rstrip() + "\n\n"
    narrative += MARKER_END + "\n\n"

    narrative += """## 4. 如何验证本文未过期

```bash
# 与当前 CAPABILITIES 比对（不一致则 exit 1）
python3 scripts/generate_platform_whitepaper.py --check

# 重新生成
python3 scripts/generate_platform_whitepaper.py

# 能力登记一致性（既有门禁）
# bash scripts/architecture_guard.sh   # 含 doc-sync 等
```

## 5. 相关文档索引

| 文档 | 用途 |
|------|------|
| [`AIPLAT_CAPABILITIES.md`](../../AIPLAT_CAPABILITIES.md) | 唯一能力清单（编辑入口） |
| [`capability_registry.yaml`](../../aiPlat-core/core/capability_registry.yaml) | 机器可读 provides |
| [`docs/architecture/overview.md`](../architecture/overview.md) | 架构全景 |
| [`docs/matrix/capability-impact-matrix.md`](../matrix/capability-impact-matrix.md) | 变更影响矩阵 |
| [`docs/DOCUMENT_SYSTEM.md`](../DOCUMENT_SYSTEM.md) | 文档治理宪法 |
| [`docs/whitepaper/aiplat-l4-autonomy-assessment-v1.0.0.md`](./aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性定级评估 |
| [`docs/archive/AIPLAT_WHITEPAPER.md`](../archive/AIPLAT_WHITEPAPER.md) | 旧叙事稿（归档，非现状权威） |

---

*生成器：`scripts/generate_platform_whitepaper.py`*
"""
    return narrative


def check_fresh(raw_caps: str, existing: str) -> bool:
    source_sha = _sha256(raw_caps)
    m = STAMP_RE.search(existing)
    if not m:
        return False
    return m.group(1) == source_sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit 0 if whitepaper stamp matches CAPABILITIES; else 1",
    )
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    if not CAPS.is_file():
        print(f"FAIL: missing {CAPS}", file=sys.stderr)
        return 2

    raw = CAPS.read_text(encoding="utf-8")
    out_path: Path = args.out

    if args.check:
        if not out_path.is_file():
            print(f"FAIL: whitepaper missing: {out_path}", file=sys.stderr)
            return 1
        ok = check_fresh(raw, out_path.read_text(encoding="utf-8"))
        if ok:
            print(f"PASS: whitepaper fresh vs {CAPS.name}")
            return 0
        print(
            f"FAIL: whitepaper stale — run: python3 scripts/generate_platform_whitepaper.py",
            file=sys.stderr,
        )
        return 1

    text = build(raw)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    meta, _ = _parse_frontmatter(raw)
    print(
        f"PASS: wrote {out_path.relative_to(REPO)} "
        f"(total_capabilities={meta.get('total_capabilities', '?')} "
        f"sha256={_sha256(raw)[:12]}…)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
