u"""

Acceptance Checker Handler (v2.7) — scoring_engine + action_contract verification.



Replaces LLM-inferred KPI checking with computed quality scores and

formal action contract validation for signoff.

"""

from __future__ import annotations



import logging

from typing import Any, Dict, List



from core.harness.infrastructure.gateway.fde_notifier import _notify_safe



logger = logging.getLogger("acceptance_checker")





async def execute(params: Dict[str, Any]) -> Dict[str, Any]:

    u"""Run acceptance KPI verification + action contract validation.



    Input: { domain_id, session_id, acceptance_data: { golden_pass_rate, avg_response_time,

             coverage_rate, freshness_score, signoff_requested } }

    """

    domain_id = params.get("domain_id", "")

    session_id = params.get("session_id", "")

    data = params.get("acceptance_data", {})



    # ── Compute acceptance KPI scores ──

    kpi_results = []

    total_score = 0

    max_score = 10



    checks = [

        ("golden_pass_rate", data.get("golden_pass_rate", 0), ">=", 85, 3, "Golden 通过率"),

        ("avg_response_time", data.get("avg_response_time", 0), "<", 3.0, 2, "平均响应时间"),

        ("coverage_rate", data.get("coverage_rate", 0), ">=", 70, 3, "覆盖率"),

        ("freshness_score", data.get("freshness_score", 0), ">=", 60, 2, "新鲜度"),

    ]



    for name, value, op, threshold, weight, label in checks:

        value = float(value) if value else 0

        passed = (op == ">=" and value >= threshold) or (op == "<" and value < threshold)

        score = weight if passed else 0

        total_score += score

        kpi_results.append({

            "name": name, "label": label, "value": value,

            "threshold": threshold, "operator": op, "passed": passed,

            "weight": weight, "score": score,

        })



    kpi_pass = total_score >= max_score * 0.7  # 70% threshold for acceptance



    # ── Action contract: validate signoff preconditions ──

    contract_result = {"valid": True, "errors": []}

    if data.get("signoff_requested"):

        try:

            from core.harness.infrastructure.action_contract import get_action_registry

            reg = get_action_registry()

            validation = reg.validate_params("add_tag", {

                "tag": f"accepted-v{data.get('version', '1.0')}"

            })

            if not validation.get("valid"):

                contract_result = validation

        except Exception as e:

            logger.warning("Action contract validation failed: %s", e)

            contract_result = {"valid": False, "errors": [str(e)]}



    # ── v2.7 N3: SLA monitoring — record acceptance deadline state ──

    try:

        from core.harness.ontology_engine.state_history import record_transition

        import time

        record_transition(

            domain_id=domain_id,

            entity_name=f"acceptance-{session_id}",

            class_name="DiagnosisSession",

            from_state="pending_signoff",

            to_state="checking",

            trigger_type="property_condition",

            transition_desc="Acceptance check initiated (SLA: 72h from now)",

            doc_id=session_id,

            timestamp=time.time(),

        )

    except Exception:

        logging.getLogger(__name__).debug('execute failed', exc_info=True)


    # ── Assemble output ──

    accepted = kpi_pass and contract_result.get("valid", False)



    result = {

        "accepted": accepted,

        "kpi_pass": kpi_pass,

        "contract_valid": contract_result.get("valid", False),

        "total_score": total_score,

        "max_score": max_score,

        "pass_pct": round(total_score / max_score * 100, 1),

        "kpi_details": kpi_results,

        "contract_errors": contract_result.get("errors", []),

        "recommendation": (

            "验收通过 — 可签收" if accepted

            else "验收未通过 — " + (

                "KPI不达标" if not kpi_pass else "Action Contract 校验失败"

            )

        ),

    }



    logger.info("Acceptance check for %s/%s: %s (%.1f/%.0f)",

                 domain_id, session_id, "ACCEPTED" if accepted else "REJECTED",

                 total_score, max_score)



    _notify_safe("验收检查完成", domain_id, {"score": total_score, "max_score": max_score, "passed": accepted})



    return result

