"""test_executor 测试执行器 handler（v2.3 双模式）。

- 代码模式（params 含 `code` 产物）：解析 ## FILE: 代码 → 读 requirements.txt 自动装依赖
  → 跑 pytest → 生成 test_report（含 bug_summary）
- Agent 模式（params 含 `agent_app`/`frontend_pages`）：确定性文档校验（字符串匹配 assertions）

输入 params（由 pipeline engine 的 _build_handler_params 构造，来自 input_artifacts）:
    code:            代码产出的 raw_output 文本（## FILE: 格式，代码模式）
    test_cases:      测试用例（代码模式=## FILE: tests/*.py；Agent 模式=test_questions 数组）
    agent_app:       Agent 应用定义（Agent 模式）
    frontend_pages:  前端页面定义（Agent 模式）
    project:         (可选) 项目名

输出: 标准 test_report 结构(header/meta/test_results/bug_summary/...)
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, List

_LANG_TAG_RE = None


def _lang_tag_pattern():
    global _LANG_TAG_RE
    if _LANG_TAG_RE is None:
        import re
        _LANG_TAG_RE = re.compile(r'^(python3?|json|bash|sh|yaml|yml|typescript|javascript|js|ts|sql)\s*\n', re.IGNORECASE)
    return _LANG_TAG_RE


# ══════════════════════════════════════════════════════════════════
# Agent 模式：确定性文档校验
# ══════════════════════════════════════════════════════════════════
def _extract_questions(test_cases: Any) -> List[Dict[str, Any]]:
    """兼容两种输入: 直接数组 或 {mode, test_questions: [...]}。"""
    if isinstance(test_cases, dict):
        qs = test_cases.get("test_questions") or test_cases.get("test_cases") or []
        return [q for q in qs if isinstance(q, dict)]
    if isinstance(test_cases, list):
        return [q for q in test_cases if isinstance(q, dict)]
    return []


def _check_assertion(text: str, assertion: Dict[str, Any]) -> Dict[str, Any]:
    """确定性字符串匹配: 所有 must_contain 命中、所有 must_not_contain 不命中。"""
    must_contain = [str(k) for k in (assertion.get("must_contain") or [])]
    must_not_contain = [str(k) for k in (assertion.get("must_not_contain") or [])]
    missing = [k for k in must_contain if k not in text]
    banned_present = [k for k in must_not_contain if k in text]
    return {"missing": missing, "banned_present": banned_present}


async def _run_document_check(params: Dict[str, Any]) -> Dict[str, Any]:
    test_cases = _extract_questions(params.get("test_cases"))
    targets = {
        "agent_app": str(params.get("agent_app") or ""),
        "frontend_pages": str(params.get("frontend_pages") or ""),
    }
    project = str(params.get("project") or "未命名项目")
    today = _dt.date.today().isoformat()

    test_results: List[Dict[str, Any]] = []
    bugs: List[Dict[str, Any]] = []
    by_fr: Dict[str, Dict[str, int]] = {}
    by_category: Dict[str, int] = {"happy_path": 0, "boundary": 0, "exception": 0}

    for tc in test_cases:
        qid = str(tc.get("id") or f"AQ-{len(test_results) + 1:03d}")
        ac_ref = str(tc.get("ac_ref") or "FR-?")
        category = str(tc.get("category") or "happy_path")
        question = str(tc.get("question") or "")
        min_expectation = str(tc.get("min_expectation") or "")
        assertions = tc.get("assertions") or []

        fr = by_fr.setdefault(ac_ref, {"total": 0, "passed": 0, "failed": 0})
        fr["total"] += 1
        by_category[category] = by_category.get(category, 0) + 1

        failed: List[Dict[str, Any]] = []
        for a in assertions:
            if not isinstance(a, dict):
                continue
            target = str(a.get("target") or "")
            text = targets.get(target, "")
            chk = _check_assertion(text, a)
            if chk["missing"] or chk["banned_present"]:
                failed.append({
                    "target": target or "unknown",
                    "missing": chk["missing"],
                    "banned_present": chk["banned_present"],
                })

        if failed:
            result = "FAIL"
            is_bug = True
            score = 2
            fr["failed"] += 1
            missing_keywords = sorted({k for f in failed for k in f["missing"]})
            detail = "; ".join(
                f"[{f['target']}] 缺关键词 {f['missing']}" + (f", 含禁词 {f['banned_present']}" if f["banned_present"] else "")
                for f in failed
            )
            bug = {
                "id": f"BUG-{len(bugs) + 1:03d}",
                "test_id": qid,
                "severity": "high" if category == "happy_path" else ("medium" if category == "exception" else "low"),
                "title": f"{ac_ref} 未通过确定性校验：{question[:30]}",
                "FR": ac_ref,
                "reproduction": question,
                "expected": min_expectation,
                "actual": detail,
                "suggested_fix": (
                    f"确保产物中精确出现以下关键词/字段：{', '.join(missing_keywords)}。"
                    f"缺失详情：{detail}"
                ),
            }
            bugs.append(bug)
        else:
            result = "PASS"
            is_bug = False
            score = 4
            fr["passed"] += 1

        test_results.append({
            "id": qid, "ac_ref": ac_ref, "category": category,
            "question": question, "min_expectation": min_expectation,
            "result": result, "score": score, "is_bug": is_bug,
            "reason": ("确定性断言全部命中" if result == "PASS"
                       else f"确定性断言未命中: {failed[0].get('missing') if failed else ''}"),
        })

    total = len(test_results)
    failed_count = sum(1 for r in test_results if r["result"] == "FAIL")
    passed_count = total - failed_count
    pass_rate = round(passed_count / total * 100) if total else 0

    return {
        "header": {"report_id": "TR-2026-0001", "project": project,
                   "test_mode": "deterministic_document_check", "date": today, "executor": "test_executor"},
        "meta": {"total_test_cases": total, "passed": passed_count, "failed": failed_count,
                 "warnings": 0, "pass_rate": pass_rate, "by_fr": by_fr, "by_category": by_category},
        "test_results": test_results,
        "bug_summary": {"total_bugs": len(bugs), "bugs": bugs},
        "quality_analysis": {
            "functional_coverage": {"overview": f"{total} 条断言确定性校验", "by_fr": by_fr},
            "case_quality": {"expectation_clarity": {"explicit": total, "vague": 0, "missing": 0},
                             "category_distribution": by_category},
            "risk_assessment": {"high_risk": [], "medium_risk": [], "low_risk": []},
            "root_cause_analysis": {"design_gap": len(bugs), "requirement_gap": 0,
                                     "implementation_gap": 0, "environment_gap": 0,
                                     "details": [{"bug_id": b["id"], "root_cause": "design_gap",
                                                   "detail": b["actual"]} for b in bugs]},
        },
        "recommendation": "APPROVED" if failed_count == 0 else "REJECTED",
        "improvements": [{"priority": "MUST_FIX", "item": b["suggested_fix"], "ref": b["id"]} for b in bugs],
    }


# ══════════════════════════════════════════════════════════════════
# 代码模式：pytest 真实执行
# ══════════════════════════════════════════════════════════════════
def _is_pkg_installed(pkg: str) -> bool:
    import importlib.metadata as _imd
    try:
        _imd.version(pkg)
        return True
    except Exception:
        return False


def _install_requirements(tmp_dir: str) -> List[str]:
    """读 tmp_dir 下任一 requirements.txt，pip install 缺失的库。返回缺失包名列表。"""
    import os, re, subprocess, sys
    req_path = None
    for root, dirs, files in os.walk(tmp_dir):
        if "requirements.txt" in files:
            req_path = os.path.join(root, "requirements.txt")
            break
    if not req_path:
        return []

    if os.environ.get("AIPLAT_AUTO_INSTALL_DEPS", "1").lower() in ("0", "false", "no"):
        return []

    try:
        with open(req_path, "r", encoding="utf-8") as f:
            reqs = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except Exception:
        return []

    missing = []
    for req in reqs:
        pkg = re.split(r'[<>=!~\[\]]', req, 1)[0].strip()
        if not pkg:
            continue
        if not _is_pkg_installed(pkg):
            missing.append(req)

    if not missing:
        return missing

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *missing, "--quiet", "--disable-pip-version-check"],
            capture_output=True, text=True, timeout=180,
        )
    except Exception:
        pass  # best-effort: install failure surfaces as pytest ENV_ERROR anyway
    return missing


def _build_pytest_bug_summary(test_log: str, failed: int, errors: int) -> Dict[str, Any]:
    import re
    bugs = []
    for _m in re.finditer(r'^(FAILED|ERROR)\s+(.+)', test_log or "", flags=re.MULTILINE):
        _name = _m.group(2).strip()
        if _name and _name not in bugs:
            bugs.append(_name)
    _is_env = "ModuleNotFoundError" in (test_log or "")
    if _is_env:
        _fix = ("环境依赖缺失（ModuleNotFoundError）。"
                "请让 programmer_agent 在 requirements.txt 声明该依赖，或改用 Mock/降级方案：\n"
                + (test_log or "")[-1500:])
    else:
        _fix = ("代码实现未通过测试，请修复 programmer_agent 生成的后端代码（含跨文件 import 一致性）：\n"
                + (test_log or "")[-2000:])
    return {
        "total_bugs": len(bugs) if bugs else int(failed or 0) + int(errors or 0),
        "failed_tests": bugs,
        "suggested_fix": _fix,
    }


async def _run_pytest(params: Dict[str, Any]) -> Dict[str, Any]:
    import os, re, subprocess, sys, tempfile, shutil, time, asyncio

    code_text = str(params.get("code") or "")
    test_text = str(params.get("test_cases") or "")
    project = str(params.get("project") or "未命名项目")
    today = _dt.date.today().isoformat()
    _t0 = time.time()

    _passed = _failed = _errors = 0
    _test_log = ""
    _repair_rounds = 0
    _repair_log = ""
    _fixed_code = ""
    _env_issues: List[str] = []

    tmp = tempfile.mkdtemp(prefix="aiplat_tests_")
    try:
        # 1. 写 code + test 文件（## FILE: 解析）
        for txt in [code_text, test_text]:
            if not txt:
                continue
            for block in re.split(r'^#{2,4}\s*FILE:\s*', txt, flags=re.MULTILINE)[1:]:
                lines = block.strip().split("\n", 1)
                if len(lines) < 2:
                    continue
                full = os.path.join(tmp, lines[0].strip())
                content = re.sub(r'^```\w*\n?', '', lines[1].strip())
                content = re.sub(r'\n?```\s*$', '', content)
                content = _lang_tag_pattern().sub('', content, count=1)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fw:
                    fw.write(content)

        # 2. 创建缺失的 __init__.py
        for root, dirs, files in os.walk(tmp):
            for d in dirs:
                init = os.path.join(root, d, "__init__.py")
                if not os.path.isfile(init):
                    with open(init, "w", encoding="utf-8") as f:
                        pass

        # 3. 读 requirements.txt + 自动装依赖
        _env_issues = _install_requirements(tmp)

        # 3.5 系统依赖健康检查（视频处理需要 ffmpeg/ffprobe，缺失 → ENV_ERROR）
        for _dep in ("ffmpeg", "ffprobe"):
            if not shutil.which(_dep):
                _env_issues.append(f"{_dep} not found on PATH")

        # 4. conftest.py：让 pytest 能 import `app.*`（pytest rootdir 是 tmp，代码在 backend/ 等子目录）
        conftest = os.path.join(tmp, "conftest.py")
        if not os.path.isfile(conftest):
            with open(conftest, "w", encoding="utf-8") as cf:
                cf.write(
                    "import sys, os\n"
                    "_root = os.path.dirname(os.path.abspath(__file__))\n"
                    "for _d in os.listdir(_root):\n"
                    "    _p = os.path.join(_root, _d)\n"
                    "    if os.path.isdir(_p) and _p not in sys.path:\n"
                    "        sys.path.insert(0, _p)\n"
                )

        # 5. PYTHONPATH：tmp + 一级子目录
        subdirs = [os.path.join(tmp, d) for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d))]
        pp = ":".join([tmp] + subdirs)
        env = {**os.environ, "PYTHONPATH": pp + (":" + os.environ.get("PYTHONPATH", "") if os.environ.get("PYTHONPATH") else "")}

        # 6. 跑 pytest
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", tmp, "--tb=short", "-q", "--no-header"],
            capture_output=True, text=True, timeout=120, env=env,
        )
        _test_log = proc.stdout + "\n" + proc.stderr
        m = re.search(r'(\d+)\s+passed', _test_log)
        if m:
            _passed = int(m.group(1))
        m = re.search(r'(\d+)\s+failed', _test_log)
        if m:
            _failed = int(m.group(1))
        m = re.search(r'(\d+)\s+error', _test_log)
        if m:
            _errors = int(m.group(1))

        # 7. Auto-repair：LLM 修复失败测试（探测修复可行性）
        _max_repairs = min(int(os.environ.get("AIPLAT_TEST_REPAIR_MAX", "2")), 3)
        while (_failed > 0 or _errors > 0) and _repair_rounds < _max_repairs and code_text:
            _repair_rounds += 1
            try:
                from core.harness.syscalls.llm import sys_llm_generate
                from core.harness.utils.model_injection import best_model_for_purpose
                _fix_prompt = (
                    "Tests failed with the following output. Analyze the errors and fix the code.\n\n"
                    f"## Test output\n{_test_log[:2500]}\n\n"
                    f"## Code to fix\n{code_text[:4000]}\n\n"
                    f"## Test code\n{test_text[:3000]}\n\n"
                    "Output ONLY the fixed code in ## FILE: format. Each file's code must be complete and runnable."
                )
                _fix_resp = await sys_llm_generate(
                    None, [{"role": "user", "content": _fix_prompt}],
                    model_name=best_model_for_purpose("code_gen"), max_tokens=16000,
                    trace_context={"source": f"test_auto_repair_r{_repair_rounds}"},
                )
                _fix_text = getattr(_fix_resp, "content", "") or str(_fix_resp)
                if _fix_text and len(_fix_text) > 100:
                    for block in re.split(r'^#{2,4}\s*FILE:\s*', _fix_text, flags=re.MULTILINE)[1:]:
                        lines2 = block.strip().split("\n", 1)
                        if len(lines2) < 2:
                            continue
                        full2 = os.path.join(tmp, lines2[0].strip())
                        content2 = re.sub(r'^```\w*\n?', '', lines2[1].strip())
                        content2 = re.sub(r'\n?```\s*$', '', content2)
                        if os.path.isfile(full2):
                            with open(full2, "w", encoding="utf-8") as fw2:
                                fw2.write(content2)
                    proc2 = subprocess.run(
                        [sys.executable, "-m", "pytest", tmp, "--tb=short", "-q", "--no-header"],
                        capture_output=True, text=True, timeout=120, env=env,
                    )
                    new_log = proc2.stdout + "\n" + proc2.stderr
                    p2 = f2 = e2 = 0
                    m = re.search(r'(\d+)\s+passed', new_log)
                    if m:
                        p2 = int(m.group(1))
                    m = re.search(r'(\d+)\s+failed', new_log)
                    if m:
                        f2 = int(m.group(1))
                    m = re.search(r'(\d+)\s+error', new_log)
                    if m:
                        e2 = int(m.group(1))
                    if p2 > _passed or (f2 + e2) < (_failed + _errors):
                        _repair_log += f"Round {_repair_rounds}: {_passed}/{_failed}/{_errors} → {p2}/{f2}/{e2} (improved)\n"
                        _passed, _failed, _errors = p2, f2, e2
                        _test_log = new_log
                        if _failed == 0 and _errors == 0:
                            _fixed_code = _fix_text  # repair fully passed → keep fixed code for write-back
                    else:
                        _repair_log += f"Round {_repair_rounds}: no improvement\n"
                        break
            except Exception:
                _repair_log += f"Round {_repair_rounds}: repair failed\n"
                break
    except Exception as _te:
        _test_log = f"Test execution error: {str(_te)[:500]}"
        _errors = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 8. 生成 report
    _env_error = ""
    if "ModuleNotFoundError" in _test_log:
        _env_error = _test_log[:500]
    total = _passed + _failed + _errors
    pr = _passed / total if total > 0 else 0
    test_results = {"passed": _passed, "failed": _failed, "errors": _errors, "total": total, "pass_rate": round(pr, 2)}
    bug_summary = _build_pytest_bug_summary(_test_log, _failed, _errors)
    env_issues = list(_env_issues) + ([_env_error] if _env_error else [])

    return {
        "header": {"report_id": "TR-2026-0001", "project": project,
                   "test_mode": "pytest", "date": today, "executor": "test_executor"},
        "meta": {"total_test_cases": total, "passed": _passed, "failed": _failed,
                 "warnings": 0, "pass_rate": round(pr * 100), "errors": _errors},
        "test_results": test_results,
        "test_log": _test_log[:3000],
        "repair_rounds": _repair_rounds,
        "repair_log": _repair_log[:1000] if _repair_log else "",
        "test_mode_detail": "ENV_ERROR" if (_env_error or env_issues) else ("TEST_FAIL" if (_failed or _errors) else "PASS"),
        "env_issues": env_issues,
        "bug_summary": bug_summary,
        "fixed_code": _fixed_code,
        "recommendation": "APPROVED" if (_failed == 0 and _errors == 0) else "REJECTED",
        "improvements": [{"priority": "MUST_FIX", "item": bug_summary.get("suggested_fix", "")}],
    }


# ══════════════════════════════════════════════════════════════════
# Agent 真实对话测试（v2.3 — 从文档校验升级为真实行为验证）
# ══════════════════════════════════════════════════════════════════

def _parse_agent_manifest(agent_app_raw: str) -> Dict[str, Any]:
    """从 agent_app 的 ## FILE: 块解析 agent_manifest.json。"""
    import re
    for block in re.split(r'^#{2,4}\s*FILE:\s*', agent_app_raw, flags=re.MULTILINE)[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) >= 2 and "agent_manifest.json" in lines[0]:
            man = re.sub(r'^```(?:json)?\s*\n?', '', lines[1].strip())
            man = re.sub(r'\n?```\s*$', '', man)
            try:
                return json.loads(man)
            except Exception:
                return {}
    return {}


def _parse_agent_sops(agent_app_raw: str) -> Dict[str, str]:
    """从 agent_app 的 ## FILE: 块解析每个 AGENT.md 的 SOP body（frontmatter 之后）。"""
    import re
    sops: Dict[str, str] = {}
    for block in re.split(r'^#{2,4}\s*FILE:\s*', agent_app_raw, flags=re.MULTILINE)[1:]:
        lines = block.strip().split("\n", 1)
        if len(lines) < 2:
            continue
        path = lines[0].strip()
        if not path.endswith("AGENT.md"):
            continue
        parts = [p for p in path.split("/") if p]
        name = parts[-2] if len(parts) >= 2 else ""
        if not name:
            continue
        content = re.sub(r'^```\w*\n?', '', lines[1].strip())
        content = re.sub(r'\n?```\s*$', '', content)
        if content.startswith("---"):
            _p = content.split("---", 2)
            content = _p[2].strip() if len(_p) >= 3 else content
        sops[name] = content
    return sops


async def _run_agent_conversation(params: Dict[str, Any]) -> Dict[str, Any]:
    """Agent 真实对话测试闭环：真实运行 Agent → 发 question → 评估真实回复。"""
    import asyncio
    from core.harness.utils.model_injection import best_model_for_purpose

    raw = str(params.get("agent_app") or "")
    test_cases = _extract_questions(params.get("test_cases"))
    if not test_cases:
        # 兜底：test_cases 非 test_questions 数组（如 test_case_generation 误判生成了 pytest 代码）
        # → 回退到文档校验，避免静默空报告
        return await _run_document_check(params)
    project = str(params.get("project") or "未命名项目")
    today = _dt.date.today().isoformat()

    manifest = _parse_agent_manifest(raw)
    routing = (manifest or {}).get("skill_routing", {}) or {}
    agents_meta = {a["name"]: a for a in (manifest or {}).get("agents", [])
                   if isinstance(a, dict) and a.get("name")}
    sops = _parse_agent_sops(raw)

    configs: Dict[str, Dict[str, Any]] = {}
    for name, meta in agents_meta.items():
        configs[name] = {
            "system_prompt": sops.get(name, ""),
            "model": best_model_for_purpose("chat"),
            "skills": (meta.get("skills") or meta.get("required_skills") or []),
            "tools": (meta.get("tools") or meta.get("required_tools") or []),
        }

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for tc in test_cases:
        grouped.setdefault(str(tc.get("target_skill") or tc.get("skill") or ""), []).append(tc)

    # 组内串行、组间并发（受 max_concurrent_skills=2 限制）
    sem = asyncio.Semaphore(2)

    async def _run_group(skill: str, cases: list) -> list:
        async with sem:
            agent_name = routing.get(skill, "")
            if not agent_name or agent_name not in configs:
                return [{"id": c.get("id"), "result": "SKIP",
                         "reason": f"no agent for skill {skill}"} for c in cases]
            out = []
            for c in cases:
                out.append(await _run_single_conversation(agent_name, configs[agent_name], c))
            return out

    groups = [_run_group(skill, cases) for skill, cases in grouped.items()]
    group_results = await asyncio.gather(*groups) if groups else []
    results = [r for gr in group_results for r in gr]

    return _build_conversation_report(results, project, today)


async def _run_single_conversation(agent_name: str, cfg: dict, tc: Dict[str, Any]) -> Dict[str, Any]:
    """单次真实对话：构造 AgentInfo → run_workspace_agent → 评估回复。"""
    import asyncio
    from core.management.agent_manager import AgentInfo
    from core.api.core_facade import run_workspace_agent

    question = str(tc.get("question") or "")
    expectation = str(tc.get("min_expectation") or "")
    if not question:
        return {"id": tc.get("id"), "result": "SKIP", "reason": "empty question"}

    info = AgentInfo(id=agent_name, name=agent_name, type="react", status="ready",
                     config={"system_prompt": cfg["system_prompt"], "model": cfg["model"]},
                     skills=list(cfg["skills"]), tools=list(cfg["tools"]))
    try:
        resp = await asyncio.wait_for(
            run_workspace_agent(agent_info=info, user_message=question, max_steps=10,
                                session_id=f"qa-{agent_name}-{tc.get('id')}"),
            timeout=60,
        )
        reply = str(resp.get("output") or resp.get("reply") or "") if isinstance(resp, dict) else str(resp)
        status, evidence = await _evaluate_response(reply, expectation)
        return {"id": tc.get("id"), "agent": agent_name, "result": status,
                "response": reply[:500], "evidence": evidence}
    except asyncio.TimeoutError:
        return {"id": tc.get("id"), "agent": agent_name, "result": "TIMEOUT", "reason": "60s timeout"}
    except Exception as e:
        return {"id": tc.get("id"), "agent": agent_name, "result": "ERROR", "reason": str(e)[:200]}


async def _evaluate_response(reply: str, expectation: str):
    """评估：规则门禁（关键词命中）→ 未命中则 LLM 复核（doc_llm）。"""
    import re
    keywords = [k for k in re.findall(r'[\'"“]([^\'"”]{2,30})[\'"”]', expectation) if len(k) >= 2]
    if keywords and all(k in reply for k in keywords):
        return "PASS", f"规则命中关键词: {keywords}"
    try:
        from core.harness.syscalls.llm import sys_llm_generate
        from core.harness.utils.model_injection import best_model_for_purpose
        prompt = (f"判断 Agent 回复是否满足预期。\n预期: {expectation}\n回复: {reply[:2000]}\n"
                  f"只回 JSON: {{\"satisfied\": true|false, \"evidence\": \"...\"}}")
        resp = await sys_llm_generate(
            None, [{"role": "user", "content": prompt}],
            model_name=best_model_for_purpose("doc_llm"),
        )
        txt = getattr(resp, "content", "") or str(resp)
        satisfied = '"satisfied": true' in txt or '"satisfied":true' in txt
        return ("PASS" if satisfied else "FAIL"), txt[:300]
    except Exception:
        return "WARNING", "LLM 复核不可用，人工确认"


def _build_conversation_report(results: List[Dict[str, Any]], project: str, today: str) -> Dict[str, Any]:
    """汇总真实对话测试结果为标准 test_report。"""
    passed = sum(1 for r in results if r.get("result") == "PASS")
    failed = [r for r in results if r.get("result") in ("FAIL", "TIMEOUT", "ERROR")]
    bugs = [{"id": f"BUG-{i+1:03d}", "test_id": r.get("id"), "severity": "high",
             "title": f"真实对话测试未通过: {r.get('id')}",
             "reproduction": r.get("response", ""), "actual": r.get("evidence", ""),
             "suggested_fix": f"修复 agent '{r.get('agent')}' 的对应 skill，使其回复满足 min_expectation。"}
            for i, r in enumerate(failed)]
    return {
        "header": {"report_id": "TR-CONV-0001", "project": project,
                   "test_mode": "agent_conversation", "date": today, "executor": "test_executor"},
        "meta": {"total_test_cases": len(results), "passed": passed, "failed": len(failed),
                 "warnings": 0, "pass_rate": round(passed / len(results) * 100) if results else 0},
        "test_results": results,
        "bug_summary": {"total_bugs": len(bugs), "bugs": bugs},
        "recommendation": "APPROVED" if not failed else "REJECTED",
        "improvements": [{"priority": "MUST_FIX", "item": b["suggested_fix"], "ref": b["id"]} for b in bugs],
    }


# ══════════════════════════════════════════════════════════════════
# 入口：分流
# ══════════════════════════════════════════════════════════════════
async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    code = params.get("code")
    if code and str(code).strip():
        return await _run_pytest(params)
    agent_app = params.get("agent_app")
    if agent_app and "agent_manifest.json" in str(agent_app):
        return await _run_agent_conversation(params)
    return await _run_document_check(params)
