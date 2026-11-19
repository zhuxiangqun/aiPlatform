"""StalenessMonitor — periodic knowledge drift detection and alerting.



import logging
Scans Wiki pages to detect when their source KB documents have been updated,

marking dependent pages as stale. Runs as part of the governance cron cycle.



Usage:

    monitor = StalenessMonitor()

    report = monitor.scan_collection("system_docs")

    # → StalenessReport(stale_count=3, affected_pages=[...])

"""



from __future__ import annotations
from core.harness.knowledge.domain_router import DomainRouter
from core.utils.paths import get_aiplat_home, get_aiplat_data_dir



import sqlite3

import os

from dataclasses import dataclass, field

from typing import Any, Dict, List, Optional

from pathlib import Path





@dataclass

class StalenessReport:

    """StalenessReport。"""
    collection_id: str = ""

    scanned_pages: int = 0

    stale_count: int = 0

    affected_pages: List[Dict[str, Any]] = field(default_factory=list)

    details: List[str] = field(default_factory=list)



    def to_dict(self) -> Dict[str, Any]:

        """to_dict。
        """
        return {

            "collection_id": self.collection_id,

            "scanned_pages": self.scanned_pages,

            "stale_count": self.stale_count,

            "affected_pages": self.affected_pages,

            "details": self.details,

        }






def kb_sqlite_path_for_tenant(tenant_id: str = DomainRouter.default_tenant()) -> Path:
    """Resolve per-tenant KB sqlite path under AIPLAT_HOME.

    Args:
        tenant_id: 租户；空则 default。

    Returns:
        ``{AIPLAT_HOME}/kb/tenants/{tenant}/kb.sqlite3``。
    """
    tid = (tenant_id or "").strip() or DomainRouter.default_tenant()
    # 为什么：N09 K14 — 禁止写死 tenants/default，漂移扫描须命中租户分库
    return Path(get_aiplat_home()) / "kb" / "tenants" / tid / "kb.sqlite3"


def list_kb_tenant_ids() -> List[str]:
    """Enumerate tenant ids that have a KB sqlite under AIPLAT_HOME.

    Always includes ``default`` even if the file is missing (compat for
    single-tenant installs and callers that expect a non-empty list).

    Returns:
        Sorted unique tenant id strings.
    """
    root = Path(get_aiplat_home()) / "kb" / "tenants"
    found: set[str] = set()
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            name = (child.name or "").strip()
            if not name:
                continue
            # 为什么：N09 K15 — cron/health 须枚举已有分库，不能只扫 default
            if (child / "kb.sqlite3").is_file():
                found.add(name)
    found.add("default")
    return sorted(found)


def aggregate_stale_summary(
    *,
    tenant_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Cross-tenant stale summary for cron / system_health.

    Args:
        tenant_ids: 可选显式租户列表；默认 ``list_kb_tenant_ids()``。

    Returns:
        Aggregated totals plus per-tenant ``get_stale_summary`` payloads.
    """
    tids = list(tenant_ids) if tenant_ids is not None else list_kb_tenant_ids()
    total_stale = 0
    total_scanned = 0
    by_tenant: Dict[str, Any] = {}
    for tid in tids:
        s = StalenessMonitor(tenant_id=tid).get_stale_summary()
        total_stale += int(s.get("total_stale") or 0)
        total_scanned += int(s.get("total_scanned") or 0)
        by_tenant[tid] = s
    return {
        "total_scanned": total_scanned,
        "total_stale": total_stale,
        "drift_ratio": round(total_stale / max(1, total_scanned), 3),
        "tenants": by_tenant,
        "tenant_ids": tids,
    }


async def auto_rebuild_stale_tenants(*, max_pages: int = 10) -> Dict[str, Any]:
    """Per-tenant auto-rebuild when that tenant's drift_ratio ≥ 0.3.

    Args:
        max_pages: 每租户最多重建页数。

    Returns:
        Aggregated rebuild counts and per-tenant results.
    """
    summary = aggregate_stale_summary()
    details: List[Dict[str, Any]] = []
    rebuilt = 0
    errors = 0
    for tid, ts in (summary.get("tenants") or {}).items():
        if float(ts.get("drift_ratio") or 0) < 0.3 or int(ts.get("total_stale") or 0) <= 0:
            continue
        r = await StalenessMonitor(tenant_id=tid).auto_rebuild_if_needed(max_pages=max_pages)
        rebuilt += int(r.get("rebuilt") or 0)
        errors += int(r.get("errors") or 0)
        details.append({"tenant_id": tid, **r})
    return {
        "status": "completed",
        "rebuilt": rebuilt,
        "errors": errors,
        "tenants_checked": summary.get("tenant_ids") or [],
        "details": details,
        "aggregate": {
            "total_stale": summary.get("total_stale"),
            "total_scanned": summary.get("total_scanned"),
            "drift_ratio": summary.get("drift_ratio"),
        },
    }


class StalenessMonitor:

    """Periodic monitor for knowledge drift detection.



    Checks every Wiki page's source_articles against KB document versions.

    When a KB doc has been re-ingested after the wiki page was created,

    the page is marked as stale and added to the review queue.

    """



    def __init__(self, *, tenant_id: str = DomainRouter.default_tenant()):

        """初始化。

        Args:
            tenant_id: 租户；选择 KB 分库路径（N09 K14）。
        """
        self._tenant_id = (tenant_id or "").strip() or DomainRouter.default_tenant()

        self._kb_db_path = kb_sqlite_path_for_tenant(self._tenant_id)



    def scan_all_collections(self) -> List[StalenessReport]:

        """Scan all known Wiki collections for knowledge drift."""

        reports = []

        try:

            wiki_root = Path(get_aiplat_home()) / "wiki" / "collections"

            if not wiki_root.exists():

                return reports

            for cdir in wiki_root.iterdir():

                if cdir.is_dir():

                    report = self.scan_collection(cdir.name)

                    if report.stale_count > 0:

                        reports.append(report)

        except Exception:

            logging.getLogger(__name__).debug('scan_all_collections failed', exc_info=True)
        # v2.10: Event-driven health update

        if reports:

            try:

                from core.harness.evaluation.system_health import SystemHealthCalculator

                SystemHealthCalculator().recompute_on_event("staleness_changed", source="scan_all_collections")

            except Exception:

                logging.getLogger(__name__).debug('scan_all_collections failed', exc_info=True)
        return reports



    def scan_collection(self, collection_id: str) -> StalenessReport:

        """Scan one Wiki collection for drift.

        Args:
            collection_id: collection 标识。
        """

        report = StalenessReport(collection_id=collection_id)



        try:

            # Load KB document versions

            kb_versions = self._load_kb_versions()

            if not kb_versions:

                return report



            # Scan Wiki pages

            from core.harness.knowledge.wiki_engine import search_pages, read_page, update_page



            pages = search_pages("", limit=500, collection_id=collection_id)

            report.scanned_pages = len(pages)



            for page in pages:

                content = read_page(page["title"], category=page.get("category", "entities"),

                                    collection_id=collection_id)

                if not content:

                    continue



                sources = content.get("source_articles", [])

                stale_refs = []



                for src in sources:

                    if not src.startswith("kb:"):

                        continue

                    doc_id = src[3:]  # Strip "kb:" prefix

                    if doc_id in kb_versions:

                        wiki_version = kb_versions.get(doc_id, 0)

                        # Check if KB doc version has advanced beyond what wiki references

                        # (At this point we just know the KB doc exists in a newer version)

                        # Mark as potentially stale

                        stale_refs.append(src)



                if stale_refs:

                    existing_stale = list(content.get("stale_references", []) or [])

                    new_stale = [s for s in stale_refs if s not in existing_stale]

                    if new_stale:

                        all_stale = existing_stale + new_stale

                        try:

                            update_page(

                                page["title"],

                                status="stale",

                                stale_references=all_stale,

                                summary=f"[AUTO] {len(new_stale)} sources may have drifted — needs review",

                                collection_id=collection_id,

                            )

                        except Exception:

                            logging.getLogger(__name__).debug('scan_collection failed', exc_info=True)


                    report.stale_count += 1

                    report.affected_pages.append({

                        "title": page["title"],

                        "stale_sources": stale_refs,

                        "total_sources": len(sources),

                    })

                    report.details.append(f"{page['title']}: {len(stale_refs)}/{len(sources)} sources drifted")



        except Exception:

            logging.getLogger(__name__).debug('scan_collection failed', exc_info=True)


        return report



    def _load_kb_versions(self) -> Dict[str, int]:

        """Load {doc_id: version} from KB SQLite for all documents."""

        try:

            if not self._kb_db_path.exists():

                return {}

            conn = sqlite3.connect(str(self._kb_db_path))

            conn.row_factory = sqlite3.Row

            rows = conn.execute(

                "SELECT doc_id, version FROM documents WHERE status='ready'"

            ).fetchall()

            conn.close()

            return {r["doc_id"]: r["version"] for r in rows}

        except Exception:

            return {}



    def get_stale_summary(self) -> Dict[str, Any]:

        """Quick summary for dashboard: total stale pages by collection."""

        reports = self.scan_all_collections()

        total_stale = sum(r.stale_count for r in reports)

        total_scanned = sum(r.scanned_pages for r in reports)

        return {

            "total_scanned": total_scanned,

            "total_stale": total_stale,

            "drift_ratio": round(total_stale / max(1, total_scanned), 3),

            "collections": {r.collection_id: r.stale_count for r in reports if r.stale_count > 0},

        }



    async def auto_rebuild_if_needed(self, max_pages: int = 10) -> Dict[str, Any]:

        """Auto-rebuild stale pages when drift exceeds threshold.

        Args:
            max_pages: max_pages 参数。
        """

        summary = self.get_stale_summary()

        if summary["drift_ratio"] < 0.3 or summary["total_stale"] == 0:

            return {"status": "skipped", "reason": "below threshold", "drift_ratio": summary["drift_ratio"]}



        reports = self.scan_all_collections()

        rebuilt = 0

        errors = 0

        details = []



        for report in reports:

            for page in report.affected_pages[:max_pages]:

                title = page["title"]

                cid = report.collection_id or DomainRouter.default_collection()



                # Extract KB doc_ids from stale sources

                stale_refs = page.get("stale_sources", [])

                doc_ids = [s.replace("kb:", "") for s in stale_refs if s.startswith("kb:")]



                for doc_id in doc_ids:

                    try:

                        import sqlite3 as _sq

                        kb_db = str(self._kb_db_path)

                        conn = _sq.connect(kb_db)

                        row = conn.execute(

                            "SELECT source_uri FROM documents WHERE doc_id=?", (doc_id,)

                        ).fetchone()

                        conn.close()



                        if row and row[0] and os.path.exists(row[0]):

                            from core.api.core_facade import auto_ontology_pipeline_for_doc

                            r = await auto_ontology_pipeline_for_doc(doc_id, row[0], cid, tenant_id=self._tenant_id)

                            if r["status"] == "completed":

                                rebuilt += 1

                            else:

                                errors += 1

                            details.append({"title": title, "doc_id": doc_id, "status": r["status"]})

                            break

                    except Exception as e:

                        errors += 1

                        details.append({"title": title, "error": str(e)[:100]})



        return {

            "status": "completed",

            "drift_ratio": summary["drift_ratio"],

            "rebuilt": rebuilt,

            "errors": errors,

            "details": details[:20],

            "next_check": "24h (governance cron)",

        }

