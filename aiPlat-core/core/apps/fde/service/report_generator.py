u"""

FDE Report Generator (v2.7) — auto-fill weekly/monthly report templates.



Pulls data from domain_maturity, metric_engine, scoring_engine, and

state_history to auto-populate report placeholders.

"""

from __future__ import annotations



import logging

import os as _os

import time as _time

from typing import Any, Dict, List, Optional



logger = logging.getLogger("fde_report_generator")





def auto_fill_weekly_report(domain_id: str) -> Dict[str, Any]:

    u"""Auto-fill weekly report data fields."""

    data = {}



    # ── Domain maturity ──

    try:

        from core.harness.knowledge.domain_maturity import compute_domain_maturity

        maturity = compute_domain_maturity(domain_id)

        data["domain_maturity"] = maturity

        data["maturity_score"] = maturity["maturity_score"]

        data["maturity_level"] = maturity["level"]

    except Exception:

        data["maturity_score"] = 0

        data["maturity_level"] = "unknown"



    # ── Entity & Wiki stats ──

    dims = data.get("domain_maturity", {}).get("dimensions", {})

    data["entity_count"] = dims.get("entity_count", 0)

    data["wiki_pages"] = dims.get("wiki_pages", 0)



    # ── New entities this week ──

    data["new_entities_this_week"] = 0

    try:

        db_path = _os.path.expanduser("~/.aiplat/state_changes.db")

        if _os.path.exists(db_path):

            from core.harness.infrastructure.infra_bridge import create_infra_database_client

            conn = create_infra_database_client(db_path)

            week_ago = _time.time() - 7 * 86400

            row = conn.execute(

                "SELECT COUNT(DISTINCT entity_name) FROM state_changes WHERE domain_id = ? AND timestamp >= ?",

                (domain_id, week_ago),

            ).fetchone()

            if row:

                data["new_entities_this_week"] = row[0]

            conn.close()

    except Exception:

        logging.getLogger(__name__).debug('auto_fill_weekly_report failed', exc_info=True)


    # ── Scoring engine alerts ──

    data["high_alerts"] = 0

    data["medium_alerts"] = 0

    try:

        from core.harness.knowledge.scoring_engine import load_models, get_alerts

        import yaml

        base = _os.path.expanduser(_os.getenv("AIPLAT_ONTOLOGY_DIR", "~/.aiplat/ontologies"))

        yp = _os.path.join(base, f"{domain_id}.yaml")

        if _os.path.exists(yp):

            with open(yp) as f:

                raw = yaml.safe_load(f) or {}

            models = load_models(raw)

            for model in models:

                alerts = get_alerts(model, domain_id)

                highs = [a for a in alerts if a.level == "high"]

                meds = [a for a in alerts if a.level == "medium"]

                data["high_alerts"] += len(highs)

                data["medium_alerts"] += len(meds)

    except Exception:

        logging.getLogger(__name__).debug('auto_fill_weekly_report failed', exc_info=True)


    # ── Response time (from usage_metrics) ──

    data["avg_response_time_ms"] = 0

    data["p95_response_time_ms"] = 0



    # ── System health summary ──

    score = data.get("maturity_score", 0)

    data["health_status"] = "🟢 正常" if score >= 60 else "🟡 需关注" if score >= 30 else "🔴 告警"



    return data





def auto_fill_monthly_report(domain_id: str) -> Dict[str, Any]:

    u"""Auto-fill monthly report data fields (richer than weekly)."""

    data = auto_fill_weekly_report(domain_id)



    # Monthly additions: growth trends

    try:

        db_path = _os.path.expanduser("~/.aiplat/state_changes.db")

        if _os.path.exists(db_path):

            from core.harness.infrastructure.infra_bridge import create_infra_database_client

            conn = create_infra_database_client(db_path)

            month_ago = _time.time() - 30 * 86400

            two_month_ago = _time.time() - 60 * 86400



            this_month = conn.execute(

                "SELECT COUNT(DISTINCT entity_name) FROM state_changes WHERE domain_id = ? AND timestamp >= ?",

                (domain_id, month_ago),

            ).fetchone()

            last_month = conn.execute(

                "SELECT COUNT(DISTINCT entity_name) FROM state_changes WHERE domain_id = ? AND timestamp >= ? AND timestamp < ?",

                (domain_id, two_month_ago, month_ago),

            ).fetchone()



            data["monthly_growth_pct"] = 0

            if last_month and last_month[0] > 0 and this_month:

                growth = (this_month[0] - last_month[0]) / last_month[0] * 100

                data["monthly_growth_pct"] = round(growth, 1)

            conn.close()

    except Exception:

        data["monthly_growth_pct"] = 0



    return data

