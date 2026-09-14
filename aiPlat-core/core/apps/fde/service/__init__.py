"""FDE service layer — business logic with no HTTP dependencies."""
from .agent import run_fde_agent_one_shot
from .report_generator import auto_fill_weekly_report, auto_fill_monthly_report
# FDEBuilderOrchestrator archived Phase 0 D1 → service/_archive/builder.py
