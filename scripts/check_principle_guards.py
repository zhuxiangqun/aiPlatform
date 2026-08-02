#!/usr/bin/env python3
"""Principle-based architecture guard checks (replaces known-list pattern matching).

Usage:
  python3 scripts/check_principle_guards.py cjk     # §78b: CJK text in engine
  python3 scripts/check_principle_guards.py domain   # §80b: domain strings in harness
  python3 scripts/check_principle_guards.py agent    # §85b: agent names in engine
  python3 scripts/check_principle_guards.py all      # all checks

Exit 0 = clean, Exit 1 = violations found (prints to stdout).
"""
import os, re, sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_cjk_in_engine():
    """§78b: Any CJK characters in engine code (excl docstrings, comments, config files)."""
    found = {}
    engine_dir = os.path.join(WORKSPACE, "aiPlat-core", "core", "harness", "execution")
    for root, dirs, files in os.walk(engine_dir):
        for fname in sorted(files):
            if not fname.endswith('.py'):
                continue
            if 'algorithm_node' in fname:
                continue
            fpath = os.path.join(root, fname)
            in_docstring = False
            text = open(fpath, errors='ignore').read()
            lines = text.split('\n')
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                # Track docstring state (check original line before comment stripping)
                if '"""' in stripped or "'''" in stripped:
                    count_3q = stripped.count('"""') + stripped.count("'''")
                    if count_3q >= 2:
                        continue
                    in_docstring = not in_docstring
                    continue
                if in_docstring:
                    continue
                # Strip inline comments for CJK check on code portion only
                hash_idx = stripped.find('#')
                if hash_idx > 0:
                    before = stripped[:hash_idx]
                    if before.count('\"') % 2 == 0 and before.count("'") % 2 == 0:
                        stripped = before.strip()
                        if not stripped:
                            continue
                if 'prompt_loader' in stripped or '_sync_resolve' in stripped:
                    continue
                if 'from ' in stripped and 'import ' in stripped:
                    continue
                has_cjk = any('\u4e00' <= ch <= '\u9fff' or '\u3040' <= ch <= '\u309f' for ch in stripped)
                if has_cjk:
                    rel = os.path.relpath(fpath, WORKSPACE)
                    found.setdefault(rel, []).append(i)
    return found


def check_domain_strings_in_harness():
    """§80b: Hardcoded domain IDs in harness code (targeted: domain_id context, not all hyphens)."""
    found = {}
    excl_files = {
        'domain_router.py', 'ontology_loader.py', 'prompt_loader.py',
        'ontology_validator.py', 'ontology_branch.py',
        'builtin_handlers.py', 'builtin_actions.py',
    }
    excl_dirs = {'tests', '__pycache__', 'reports', '.pytest_cache'}
    harness_dir = os.path.join(WORKSPACE, "aiPlat-core", "core", "harness")
    for root, dirs, files in os.walk(harness_dir):
        dirs[:] = [d for d in dirs if d not in excl_dirs]
        for fname in sorted(files):
            if not fname.endswith('.py') or fname in excl_files:
                continue
            fpath = os.path.join(root, fname)
            for i, line in enumerate(open(fpath, errors='ignore'), 1):
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                # Targeted: domain_id="xxx-yyy" or DomainRouter.load("xxx-yyy")
                # or hardcoded domain name strings used as identifiers
                for m in re.finditer(r"""(["'])([\w-]+)\1""", s):
                    val = m.group(2)
                    if '-' not in val or len(val) < 6:
                        continue
                    # Only flag if the line looks like it's using a domain ID semantically
                    is_domain_ctx = (
                        'domain' in s.lower() or
                        'load(' in s or
                        'register(' in s or
                        ('_DOMAIN' in s and 'DEFAULT' not in s and 'PROMPT' not in s)
                    )
                    if not is_domain_ctx:
                        continue
                    rel = os.path.relpath(fpath, WORKSPACE)
                    found.setdefault(rel, []).append((i, val))
    return found


def check_agent_strings_in_engine():
    """§85b: Business agent name strings in core/harness/execution/."""
    found = {}
    engine_dir = os.path.join(WORKSPACE, "aiPlat-core", "core", "harness", "execution")
    engine_generic = {
        'multi_agent', 'tri_agent', 'call_agent', 'assigned_agent',
        'execute_multi_agent', 'base_agent', 're_agent',
        'target_agent', 'debate_manager_agent', 'pipeline_agent',
        'fallback_agent', 'source_agent',
    }
    for root, dirs, files in os.walk(engine_dir):
        dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
        for fname in sorted(files):
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(root, fname)
            for i, line in enumerate(open(fpath, errors='ignore'), 1):
                s = line.strip()
                if not s or s.startswith('#'):
                    continue
                # Look for quoted strings matching *_agent (potential business agent name)
                for m in re.finditer(r"""["'](\w+_agent)["']""", s):
                    val = m.group(1)
                    # Skip engine-generic concepts
                    if val in engine_generic:
                        continue
                    # Skip getattr/field references
                    if 'getattr' in s or 'agent_type' in s or val == 'agent_id':
                        continue
                    # Only flag if it's a specific name (not a pattern/variable)
                    # Specific agent names are typically longer and unique
                    if len(val) < 10 or val.count('_') < 2:
                        continue  # skip short/generic names
                    rel = os.path.relpath(fpath, WORKSPACE)
                    found.setdefault(rel, []).append((i, val))
    return found


def format_results(found, label):
    """Print results. Return count of violations."""
    if not found:
        return 0
    total = sum(len(items) for items in found.values())
    count = 0
    for fpath, items in sorted(found.items()):
        for item in items:
            if isinstance(item, tuple):
                line, val = item
                print(f"  {fpath}:{line}  \"{val}\"")
            else:
                print(f"  {fpath}:{item}")
            count += 1
            if count >= 15:
                break
        if count >= 15:
            break
    if total > 15:
        print(f"  ... and {total - 15} more in {len(found)} files")
    return total


def main():
    checks = sys.argv[1:] if len(sys.argv) > 1 else ['all']
    if 'all' in checks or 'cjk' in checks:
        cjk = check_cjk_in_engine()
        cjk_count = format_results(cjk, "CJK")
        print(f"§78b CJK lines in engine: {cjk_count}")
        print()

    if 'all' in checks or 'domain' in checks:
        ds = check_domain_strings_in_harness()
        ds_count = format_results(ds, "Domain strings")
        print(f"§80b Domain strings in harness: {ds_count}")
        print()

    if 'all' in checks or 'agent' in checks:
        ag = check_agent_strings_in_engine()
        ag_count = format_results(ag, "Agent strings")
        print(f"§85b Agent name strings in engine: {ag_count}")
        print()

    total_violations = 0
    if 'all' in checks or 'cjk' in checks:
        total_violations += cjk_count if 'cjk' in locals() else 0
    if 'all' in checks or 'domain' in checks:
        total_violations += ds_count if 'ds' in locals() else 0
    if 'all' in checks or 'agent' in checks:
        total_violations += ag_count if 'ag' in locals() else 0

    if not total_violations:
        # Silently clean — no output (caller checks exit code)
        pass
    sys.exit(1 if total_violations else 0)


if __name__ == '__main__':
    main()
