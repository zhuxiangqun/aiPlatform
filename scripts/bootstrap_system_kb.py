#!/usr/bin/env python3
"""
aiPlat 系统知识库 Bootstrap 脚本

一次性导入 ~150 个系统规约/架构/能力文档到知识库，
生成 Wiki 页面，启动持续同步。

用法:
    python bootstrap_system_kb.py
    python bootstrap_system_kb.py --skip-wiki     # 跳过 Wiki 生成
    python bootstrap_system_kb.py --skip-ontology # 跳过本体构建
"""

import sys, os, asyncio, time, argparse
from pathlib import Path

# ── Config ──────────────────────────────────────────────
TENANT_ID = "default"
COLLECTION_ID = "system_docs"
COLLECTION_NAME = "aiPlat 系统文档"
DOC_ROOT = os.path.expanduser("~/workdata/person/zy/aiPlatform")

# Directories to scan for .md files
SCAN_DIRS = [
    DOC_ROOT,                                         # 根目录 CLAUDE.md, CAPABILITIES.md 等
    os.path.join(DOC_ROOT, "aiPlat-core"),
    os.path.join(DOC_ROOT, "aiPlat-platform"),
    os.path.join(DOC_ROOT, "aiPlat-infra"),
    os.path.join(DOC_ROOT, "aiPlat-management"),
    os.path.join(DOC_ROOT, "aiPlat-app"),
    os.path.join(DOC_ROOT, "docs"),
]

# Exclude patterns
EXCLUDE_DIRS = {
    "__pycache__", ".venv", "venv", "node_modules",
    ".git", "dist", "build", "data", "logs",
    "tests", "test", "_archive",
}

# ── Main ────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-wiki", action="store_true")
    parser.add_argument("--skip-ontology", action="store_true")
    parser.add_argument("--skip-watch", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="仅列出文件，不导入")
    args = parser.parse_args()

    print("=" * 60)
    print("  aiPlat 系统知识库 Bootstrap")
    print("=" * 60)

    # ── Phase 1: Import documents ──
    print(f"\n📥 Phase 1: 导入系统文档 → collection '{COLLECTION_ID}'")
    sys.path.insert(0, os.path.join(DOC_ROOT, "aiPlat-platform"))
    from kb.service import enqueue_directory_ingest, enqueue_ingest

    all_doc_ids = []
    all_file_paths = []

    for scan_dir in SCAN_DIRS:
        if not os.path.isdir(scan_dir):
            continue
        print(f"  扫描: {scan_dir}")
        if args.dry_run:
            md_files = sorted(Path(scan_dir).rglob("*.md"))
            for f in md_files:
                if any(exc in str(f) for exc in EXCLUDE_DIRS):
                    continue
                print(f"    [dry] {f.relative_to(DOC_ROOT)}")
            continue

        try:
            result = enqueue_directory_ingest(
                tenant_id=TENANT_ID,
                collection_id=COLLECTION_ID,
                directory=scan_dir,
                recursive=True,
                pattern="*.md",
                kind="markdown",
                name=COLLECTION_NAME,
            )
            all_doc_ids.extend(result.get("doc_ids", []))
            print(f"    ✅ {result.get('total', 0)} 个文档入队"
                  f"（跳 {result.get('skipped', 0)}，清 {result.get('cleaned', 0)}）")
            # Collect file paths for wiki update
            for fpath in sorted(Path(scan_dir).rglob("*.md")):
                if any(exc in str(fpath) for exc in EXCLUDE_DIRS):
                    continue
                all_file_paths.append(str(fpath))
        except Exception as e:
            print(f"    ⚠️ 扫描失败: {e}")

    if args.dry_run:
        print(f"\n   共 {len(all_doc_ids)} 个文件（--dry-run 模式，未实际导入）")
        return

    print(f"\n   ✅ 共 {len(all_doc_ids)} 个文档入队，等待处理...")

    # Wait for jobs to complete (poll until KB has matching doc count)
    from kb.db import KBSqlite
    from kb.storage import get_tenant_storage
    st = get_tenant_storage(TENANT_ID)
    db = KBSqlite(st.db_path)
    db.ensure_schema()

    for i in range(60):
        time.sleep(1)
        try:
            with db.connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE tenant_id=? AND collection_id=? AND status='ready'",
                    (TENANT_ID, COLLECTION_ID),
                ).fetchone()[0]
        except Exception:
            count = 0
        if count >= len(all_doc_ids) * 0.8:
            print(f"   ✅ {count}/{len(all_doc_ids)} 文档处理完成")
            break
        if i % 5 == 0:
            print(f"   ... {count}/{len(all_doc_ids)} 就绪")
    else:
        print(f"   ⚠️ 超时: {count}/{len(all_doc_ids)}（继续执行后续步骤）")

    # ── Phase 2: Wiki auto-generation ──
    wiki_count = 0
    if not args.skip_wiki and all_file_paths:
        print(f"\n📝 Phase 2: 生成 Wiki 页面（{len(all_file_paths)} 个文档）")
        from core.api.core_facade import wiki_auto_update

        wiki_count = 0
        for i, fpath in enumerate(all_file_paths[:50]):  # Batch first 50 for speed
            try:
                doc_id = _stable_doc_id(fpath)
                await wiki_auto_update(
                    doc_id=doc_id,
                    file_path=fpath,
                    collection_id=COLLECTION_ID,
                )
                wiki_count += 1
                if wiki_count % 10 == 0:
                    print(f"   ... {wiki_count} 个 Wiki 页面生成完成")
            except Exception as e:
                if wiki_count == 0:
                    print(f"   ⚠️ Wiki 生成: {e}（可能 Core 未启动，跳过）")
                break
        print(f"   ✅ {wiki_count} 个 Wiki 页面生成完成")

    # ── Phase 3: Ontology engine ──
    if not args.skip_ontology:
        print(f"\n🧬 Phase 3: 本体引擎处理 'aiplat-system' 域")
        try:
            from core.harness.knowledge.ontology_loader import load_ontology_from_yaml
            domain = load_ontology_from_yaml(
                os.path.expanduser("~/.aiplat/ontologies/aiplat-system.yaml"))
            print(f"   ✅ 域定义加载成功（{len(domain.classes)} 类，{len(domain.object_properties)} 关系）")
        except Exception as e:
            print(f"   ⚠️ 域加载: {e}（Core 未启动则跳过）")

    # ── Phase 4: Start watch directory ──
    if not args.skip_watch:
        print(f"\n👁️ Phase 4: 启动持续同步监控")
        try:
            from kb.service import watch_directory
            watch_directory(
                tenant_id=TENANT_ID,
                watch_id=COLLECTION_ID,
                directory=DOC_ROOT,
                collection_id=COLLECTION_ID,
                recursive=True,
                pattern="*.md",
                kind="markdown",
                poll_interval=60.0,
            )
            print(f"   ✅ 后台监控已启动（每 60s 扫描 {DOC_ROOT}）")
        except Exception as e:
            print(f"   ⚠️ 监控启动: {e}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ aiPlat 系统知识库 Bootstrap 完成")
    print(f"     导入: {len(all_doc_ids)} 个文档")
    print(f"     Wiki: {wiki_count} 个页面")
    print(f"     Collection: '{COLLECTION_ID}'")
    print(f"     监控: {'✅ 运行中' if not args.skip_watch else '已跳过'}")
    print(f"{'=' * 60}")


def _stable_doc_id(file_path: str) -> str:
    import hashlib
    sha = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()[:12]
    return f"doc_{sha}"


if __name__ == "__main__":
    asyncio.run(main())
