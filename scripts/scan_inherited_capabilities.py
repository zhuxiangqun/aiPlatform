#!/usr/bin/env python3
"""
scan_inherited_capabilities.py — Auto-scan which platform capabilities
are unconditionally inherited by generated applications.

Three modes:
  python3 scripts/scan_inherited_capabilities.py           # output YAML candidates
  python3 scripts/scan_inherited_capabilities.py --verify  # diff vs frontmatter
  python3 scripts/scan_inherited_capabilities.py --merge   # auto-merge into frontmatter

Integrates with auto_sync_docs.sh: called on every commit to detect
drift between Schema/Code and the core_guarantees in frontmatter.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

WORKSPACE = Path(__file__).resolve().parent.parent

# ── Configuration ──────────────────────────────────────────────

# AUTO capability patterns: (id, description, glob_pattern, files_to_scan)
AUTO_PATTERNS = [
    # Circuits & Safety
    ("llm_circuit_breaker", "LLM 熔断器：5次连续失败→断路30s",
     r"_llm_cb\.allow_request|LLMCircuitBreaker\(|_llm_cb\.record_success|_llm_cb\.record_failure",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("pii_detection", "PII 脱敏：手机/身份证/邮箱/银行卡自动替换",
     r"pii\.mask|PIIDetector|_guard_messages.*pii",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("injection_guard", "提示词注入防护：6条正则+特殊token过滤+覆盖保护",
     r"_INJECTION_PATTERNS|_SPECIAL_TOKENS|_CONTROL_RE|injection_alerts",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("immune_memory", "ImmunMemory 攻击模式防御",
     r"ImmuneMemory\.(immunize|scan|SAFE_RESPONSE)",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("claude_md_injection", "CLAUDE.md 架构规约注入",
     r"_try_inject_claude_md",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("wiki_circuit_breaker", "Wiki 检索熔断器",
     r"WikiCircuitBreaker|_wiki_circuit_breaker",
     ["aiPlat-core/core/harness/syscalls/retrieval.py"]),
    ("rate_limiter", "模型调用限流：并发控制+cooldown",
     r"check_and_acquire|rate_limit_tracker|RateLimiter",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    # Context & Memory
    ("memory_build_context", "四层记忆注入（Working/Episodic/Semantic/TaskSkill）",
     r"_mgr\.build_context|MemoryManager.*build_context",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("memory_save_interaction", "交互记忆保存（Episodic）",
     r"_try_save_interaction|save_interaction",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("context_compression_5level", "5 级上下文压缩",
     r"ContextCompression|_maybe_compact|compact_messages",
     ["aiPlat-core/core/harness/memory/compression.py",
      "aiPlat-core/core/harness/memory/manager.py",
      "aiPlat-core/core/harness/execution/loop/inference.py"]),
    ("semantic_cache", "语义缓存 L1(MD5)+L2(Cosine≥0.95)",
     r"semantic_cache|try_cache_hit|write_cache_result",
     ["aiPlat-core/core/apps/agents/materials_chat.py",
      "aiPlat-core/core/harness/knowledge/semantic_cache_hook.py",
      "aiPlat-core/core/harness/syscalls/retrieval.py"]),
    # Quality & Safety
    ("hallucination_tracker", "幻觉检测：GraphIndex 事实验证",
     r"hallucination_tracker|get_hallucination_tracker|check_consistency",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    ("quality_recording", "质量评分记录（异步，fire-and-forget）",
     r"_record_quality|QualityValidator|quality_delta",
     ["aiPlat-core/core/harness/utils/model_injection.py"]),
    ("prompt_assembler", "Prompt 动态组装（工具/技能/记忆/budget）",
     r"PromptAssembler|MessageFormatter|assemble\(|prompt_assemble",
     ["aiPlat-core/core/harness/syscalls/llm.py"]),
    # Tool Safety
    ("policy_gate", "PolicyGate 权限检查（sys_tool_call入口）",
     r"PolicyGate|policy_gate.*check|policy_gate.*evaluate",
     ["aiPlat-core/core/harness/syscalls/tool.py"]),
    ("approval_gate", "ApprovalGate 危险操作审批",
     r"ApprovalGate|approval.*check|approval.*evaluate|ApprovalManager",
     ["aiPlat-core/core/harness/syscalls/tool.py",
      "aiPlat-core/core/harness/context/engine.py",
      "aiPlat-core/core/harness/infrastructure/gates/"]),
    ("tool_drift_detector", "工具漂移检测",
     r"drift_detector|get_drift_detector",
     ["aiPlat-core/core/harness/syscalls/tool.py"]),
    ("token_budget_management", "Token 预算管理",
     r"budget|token_limit|token_budget|_budget",
     ["aiPlat-core/core/harness/execution/loop/inference.py"]),
    # Self-Learning
    ("model_health_tracking", "模型健康自适应跟踪",
     r"_record_success|_record_failure|ModelHealthStore|_calculate_dynamic_boost",
     ["aiPlat-core/core/harness/utils/model_injection.py",
      "aiPlat-infra/infra/management/model/manager.py"]),
    ("experience_vector", "经验向量（Loop+Pipeline 存入）",
     r"ExperienceVector|_try_feed_learning|feed_learning",
     ["aiPlat-core/core/harness/execution/loop/_facade.py",
      "aiPlat-core/core/harness/execution/pipeline_engine.py"]),
    ("seci_knowledge_spiral", "SECI 知识螺旋（POST_LOOP→atom→convergence）",
     r"seci_engine|SECI|register_seci_hook|POST_LOOP",
     ["aiPlat-core/core/harness/knowledge/seci_engine.py"]),
    ("skill_crystalization", "Skill 晶体化（pipeline完成→TaskSkill→SkillRegistry）",
     r"_crystallize_skill|TaskSkill|save_task_skill",
     ["aiPlat-core/core/harness/execution/pipeline_engine.py"]),
    ("feedback_loops", "交互反馈回路",
     r"get_production_feedback|get_local_feedback|feedback.*record",
     ["aiPlat-core/core/harness/execution/loop/_facade.py"]),
]

# Files to scan for CONFIGURABLE capability field consumption
ENGINE_FILES = [
    "aiPlat-core/core/harness/execution/pipeline_engine.py",
]
SCHEMA_FILE = "aiPlat-core/core/schemas_builder.py"
CAPABILITIES_FILE = "AIPLAT_CAPABILITIES.md"

# Fields to EXCLUDE from configurable scan (not capability-related)
SCHEMA_EXCLUDE = {
    # Purely descriptive / metadata
    "id", "agent_id", "agent_name", "description", "category", "tags",
    "phase", "order", "model", "code_target", "language",
    "prompt_extra", "phase_description", "input_artifacts",
    "fallback_result_key", "retry_target_id",
    "sandbox_cpu_limit_seconds", "sandbox_memory_limit_mb",
    "sandbox_max_processes", "eval_model", "routing_mode",
    "routing_rules", "deviation_tolerance", "failure_mode_constraints",
    "scoring_weights", "propagation_rules", "merge_strategies",
    "coverage_trace_fields", "debate_participants",
    "debate_max_rounds", "debate_manager_agent", "moa_preset",
    "moa_reference_count", "node_config", "node_type",
    "render_upstream", "render_schema_fields", "knowledge_bases",
    "ontology_class", "ontology_relations", "ontology_action_verb",
    "ontology_preconditions", "ontology_target_state",
    "expected_outcomes", "rubric_path", "scene_id",
    "planning_stage_id", "rollback_on_reject", "rollback_target_id",
    "stage_timeout_seconds", "max_consecutive_llm_failures",
    "retry_llm_on_rate_limit", "context_isolation",
    "tdd_enforce", "execution_mode",
    "hitl_after_execute", "hitl_after_phase",
    # Depends_on and required_skills are project-specific, not platform defaults
    "depends_on", "required_skills",
}


# ── Scanner ────────────────────────────────────────────────────

def scan_auto_capabilities() -> List[Dict[str, Any]]:
    """Scan AUTO patterns — unconditionally inherited capabilities."""
    results = []
    for cap_id, desc, pattern, files in AUTO_PATTERNS:
        found = []
        for rel_path in files:
            fpath = WORKSPACE / rel_path
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text()
                for m in re.finditer(pattern, content, re.MULTILINE):
                    line_no = content[:m.start()].count("\n") + 1
                    snippet = content[max(0, m.start() - 20):m.end() + 30].replace("\n", " ").strip()[:120]
                    found.append({
                        "file": rel_path,
                        "line": line_no,
                        "snippet": snippet,
                    })
            except Exception:
                pass
        results.append({
            "id": cap_id,
            "description": desc,
            "found_at": found,
            "status": "active" if found else "missing",
        })
    return results


def scan_configurable_capabilities() -> Dict[str, List[Dict[str, Any]]]:
    """Scan PipelineStageConfig fields — which are consumed vs orphaned."""
    schema_path = WORKSPACE / SCHEMA_FILE
    if not schema_path.exists():
        return {"consumed": [], "orphan": []}

    # Parse PipelineStageConfig fields
    try:
        tree = ast.parse(schema_path.read_text())
    except Exception:
        return {"consumed": [], "orphan": []}

    fields = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PipelineStageConfig":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    name = item.target.id
                    if name.startswith("_"):
                        continue
                    default_val = None
                    is_factory = False
                    if item.value:
                        if isinstance(item.value, ast.Call):
                            # Field(default_factory=...) or Field(default=...)
                            is_factory = True
                            for kw in item.value.keywords:
                                if kw.arg == "default_factory":
                                    try:
                                        default_val = ast.literal_eval(kw.value) if isinstance(kw.value, (ast.Constant, ast.List, ast.Dict)) else repr(ast.dump(kw.value))[:80]
                                    except Exception:
                                        default_val = "<complex>"
                        elif isinstance(item.value, ast.Constant):
                            default_val = item.value.value
                        elif isinstance(item.value, ast.Name):
                            default_val = f"<{item.value.id}>"
                    fields[name] = {
                        "name": name,
                        "default": default_val,
                        "is_factory": is_factory,
                    }
            break

    # Extract inline comments from source for field descriptions
    source_text = schema_path.read_text()
    source_lines = source_text.split('\n')
    
    # Build line → field_name mapping from AST
    line_to_field = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PipelineStageConfig":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    line_to_field[item.lineno] = item.target.id
            break
    
    for line_no, name in line_to_field.items():
        if name not in fields:
            continue
        comment = ""
        if line_no <= len(source_lines):
            line_text = source_lines[line_no - 1]
            # Inline comment
            if '#' in line_text:
                comment = line_text.split('#', 1)[1].strip().strip(' "')
            # Next 1-2 lines triple-quoted docstring
            if not comment:
                for offset in range(1, 3):  # check next 2 lines
                    if line_no - 1 + offset < len(source_lines):
                        next_line = source_lines[line_no - 1 + offset].strip()
                        if next_line.startswith('"""'):
                            comment = next_line.strip('"').strip()
                            break
            if comment:
                fields[name]["description"] = comment

    # Check which fields are consumed by pipeline_engine
    consumed = []
    orphan = []
    for name, info in sorted(fields.items()):
        if name in SCHEMA_EXCLUDE:
            continue
        refs = _find_field_references(name, ENGINE_FILES)
        entry = {
            "field": name,
            "schema_default": info["default"],
            "description": info.get("description", ""),
            "consumed_at": refs,
            "engine_consumed": len(refs) > 0,
        }
        if refs:
            consumed.append(entry)
        else:
            entry["warning"] = f"Schema defines '{name}' but pipeline_engine never reads it"
            orphan.append(entry)

    return {"consumed": consumed, "orphan": orphan}


def _find_field_references(field_name: str, files: List[str]) -> List[Dict[str, Any]]:
    """Find all references to a field in the given files."""
    refs = []
    patterns = [
        rf"stage\.{field_name}\b",
        rf"stages\[\d+\]\.{field_name}\b",
        rf"getattr\(stage,\s*['\"]{field_name}['\"]\)",
        rf"getattr\(stages\[\d+\],\s*['\"]{field_name}['\"]",
        rf"stage\[['\"]{field_name}['\"]\]",
    ]
    for rel_path in files:
        fpath = WORKSPACE / rel_path
        if not fpath.exists():
            continue
        content = fpath.read_text()
        for pattern in patterns:
            for m in re.finditer(pattern, content):
                line_no = content[:m.start()].count("\n") + 1
                snippet = content[max(0, m.start() - 10):m.end() + 20].replace("\n", " ").strip()[:100]
                refs.append({"file": rel_path, "line": line_no, "snippet": snippet})
    return refs


# ── Output formatters ──────────────────────────────────────────

def output_yaml(auto: list, configurable: dict, file=None) -> None:
    """Output scan results as structured YAML."""
    out = file or sys.stdout
    now = __import__("time").strftime("%Y-%m-%d %H:%M")
    print(f"# Auto-generated by scan_inherited_capabilities.py", file=out)
    print(f"# Generated: {now}", file=out)
    print(f"# Merge into AIPLAT_CAPABILITIES.md frontmatter after review.", file=out)
    print(file=out)
    print("core_guarantees:", file=out)

    # AUTO
    active = [a for a in auto if a["status"] == "active"]
    missing = [a for a in auto if a["status"] == "missing"]
    print(f"  auto:  # {len(active)} active, {len(missing)} missing", file=out)
    for a in active:
        print(f"    - id: {a['id']}", file=out)
        print(f"      description: \"{a['description']}\"", file=out)
        print(f"      paths:", file=out)
        for f in a["found_at"]:
            print(f"        - {f['file']}::{f['line']}", file=out)
    if missing:
        print(f"  # ⚠️  MISSING — declared but no code found:", file=out)
        for a in missing:
            print(f"  #   - {a['id']}: {a['description']}", file=out)

    # CONFIGURABLE: consumed
    cc = configurable.get("consumed", [])
    print(f"\n  configurable:  # {len(cc)} consumed by engine", file=out)
    for c in cc:
        print(f"    - id: {c['field']}", file=out)
        print(f"      field: PipelineStageConfig.{c['field']}", file=out)
        if c.get("description"):
            print(f"      description: \"{c['description']}\"", file=out)
        print(f"      schema_default: {c['schema_default']}", file=out)
        print(f"      consumed_at:", file=out)
        for r in c["consumed_at"]:
            print(f"        - {r['file']}::{r['line']}", file=out)

    # CONFIGURABLE: orphan
    co = configurable.get("orphan", [])
    if co:
        print(f"\n  # ⚠️  ORPHAN — Schema fields never read by engine ({len(co)}):", file=out)
        for c in co:
            print(f"  #   - {c['field']}: default={c['schema_default']} — {c['warning']}", file=out)
        print(f"  #", file=out)
        print(f"  #   Action: either wire the engine to consume these fields,", file=out)
        print(f"  #   or remove them from core_guarantees.", file=out)


def verify_vs_frontmatter(auto: list, configurable: dict) -> int:
    """Compare scan results against AIPLAT_CAPABILITIES.md frontmatter. Returns exit code."""
    caps_path = WORKSPACE / CAPABILITIES_FILE
    if not caps_path.exists():
        print("ERROR: AIPLAT_CAPABILITIES.md not found")
        return 1

    content = caps_path.read_text()
    # Extract YAML frontmatter (everything between first two --- lines)
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        print("ERROR: No frontmatter found")
        return

    fm_lines = []
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            fm_end_idx = i
            break
        fm_lines.append(line)
    else:
        print("ERROR: Frontmatter not closed")
        return

    fm_content = "\n".join(fm_lines)
    body_content = "\n".join(lines[fm_end_idx + 1:])


def merge_into_frontmatter(auto: list, configurable: dict) -> None:
    """Auto-merge scan results into AIPLAT_CAPABILITIES.md frontmatter."""
    caps_path = WORKSPACE / CAPABILITIES_FILE
    if not caps_path.exists():
        print("ERROR: AIPLAT_CAPABILITIES.md not found")
        return

    content = caps_path.read_text()
    backup_path = str(caps_path) + ".bak"
    with open(backup_path, "w") as f:
        f.write(content)
    print(f"Backup: {backup_path}")

    # Extract frontmatter lines
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        print("ERROR: No frontmatter found")
        return

    fm_end = 0
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            fm_end = i
            break
    if fm_end == 0:
        print("ERROR: Frontmatter not closed")
        return

    # Generate YAML block for core_guarantees
    import io
    buf = io.StringIO()
    output_yaml(auto, configurable, file=buf)
    yaml_block = buf.getvalue().rstrip()

    fm_content = "\n".join(lines[1:fm_end])
    body = "\n".join(lines[fm_end + 1:])

    # Remove old core_guarantees if present
    fm_new = []
    skip = False
    for line in fm_content.split("\n"):
        if line.startswith("core_guarantees:"):
            skip = True
            continue
        if skip:
            if line and not line.startswith("  ") and not line.startswith("\t") and not line.startswith("#"):
                skip = False
                fm_new.append(line)
            continue
        fm_new.append(line)

    fm_new.append(yaml_block)
    new_content = "---\n" + "\n".join(fm_new) + "\n---\n" + body
    caps_path.write_text(new_content)
    print(f"Merged core_guarantees into {CAPABILITIES_FILE}")


# ── Main ───────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan inherited capabilities")
    parser.add_argument("--verify", action="store_true", help="Diff vs frontmatter")
    parser.add_argument("--merge", action="store_true", help="Auto-merge into frontmatter")
    parser.add_argument("--json", action="store_true", help="Output as JSON instead of YAML")
    args = parser.parse_args()

    auto = scan_auto_capabilities()
    configurable = scan_configurable_capabilities()

    if args.verify:
        sys.exit(verify_vs_frontmatter(auto, configurable))
    elif args.merge:
        merge_into_frontmatter(auto, configurable)
    elif args.json:
        import json as _json
        print(_json.dumps({"auto": auto, "configurable": configurable}, indent=2, ensure_ascii=False))
    else:
        output_yaml(auto, configurable)


if __name__ == "__main__":
    main()
