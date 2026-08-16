# diagnostics/checks — runtime health check submodules (v1.0)
#
# Each submodule is an independent async check, callable by the auto-diagnostic
# scheduler via run_with_timeout(). Refer to base.py for the CheckStatus contract.
#
# Submodules by priority:
#   P0: model_health.py, artifact_quality.py
#   P1: api_contract.py, human_feedback.py, rollback_monitor.py
#   P2: pipeline_latency.py, knowledge_gap.py
#   P3: memory_health.py
