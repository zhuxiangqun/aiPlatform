u"""

Customer Profile Creator Handler (v2.7) — industry→domain pre-filter.



Pre-filters domain recommendations based on detected industry before

the full domain_assessor runs. Uses scenario_selector for data-driven matching.

"""

from __future__ import annotations



import logging

from typing import Any, Dict



logger = logging.getLogger("customer_profile_creator")





async def execute(params: Dict[str, Any]) -> Dict[str, Any]:

    u"""Pre-filter domains by industry detection.



    Input: { company_name, company_description, industry, pain_points }

    Output: { profile with pre_filtered_domains }

    """

    profile = params.copy()

    industry = profile.get("industry", "")



    pre_filtered = []

    try:

        from core.harness.knowledge.scenario_selector import recommend_order

        recommendations = recommend_order(industry=industry, pain_points=profile.get("pain_points", ""), limit=3)

        for r in recommendations:

            pre_filtered.append({

                "domain_id": r["domain_id"],

                "score": r.get("priority_score", 0),

                "priority": r.get("priority", "P1"),

                "reason": r.get("value_formula", ""),

            })

    except Exception as e:

        logger.debug("scenario_selector pre-filter skipped: %s", e)



    profile["pre_filtered_domains"] = pre_filtered

    profile["_v27"] = True



    if not industry and profile.get("company_description"):

        try:

            from core.harness.knowledge.domain_router import DomainRouter

            router = DomainRouter()

            classified = router.classify(profile["company_description"])

            if classified:

                profile["industry"] = classified.get("domain_id", "")

        except Exception:

            logging.getLogger(__name__).debug('execute failed', exc_info=True)


    # v2.7 N6: Check if customer has external ontology to import

    external_onto = profile.get("external_ontology", {})

    if external_onto:

        source = external_onto.get("url") or external_onto.get("path", "")

        target_domain = external_onto.get("domain_id", profile.get("industry", "imported"))

        fmt = external_onto.get("format", "auto")

        if source:

            try:

                from core.harness.knowledge.ontology_importer import import_ontology

                result = import_ontology(source=source, target_domain=target_domain, format=fmt)

                profile["imported_ontology"] = {

                    "domain_id": result.get("domain_id", ""),

                    "class_count": result.get("class_count", 0),

                    "readonly": result.get("readonly", True),

                    "path": result.get("path", ""),

                }

                logger.info("Imported external ontology: %s → %d classes", target_domain, result.get("class_count", 0))

            except Exception as e:

                logger.warning("External ontology import failed: %s", e)

                profile["imported_ontology"] = {"error": str(e)}



    return profile

