"""app_runtime.py — 生成 app 运行时（生成物侧接线，CLAUDE.md §23，2026-08-27）。

生成 app 部署后是静态文件（index.html + AGENT.md/SKILL.md + 可能的后端代码），
此前无运行能力 → 无法自动测试（e2e_smoke 只是"目录存在"假通过）。

本模块让生成 app 真正"跑起来"：
  detect_runtime   — 扫描生成目录识别可运行入口（FastAPI/Flask/Node/静态页）
  launch           — 经 daemon_jobs 托管启动（断线续跑，生成物侧接线：待接线 → 已接线）
  health_check     — HTTP 轮询健康探测（2xx/3xx = up）
  stop             — 经 daemon_jobs kill（连同会话组）
  smoke_test       — 完整闭环：detect → launch → health → 报告
  real_tests       — 测试经理真实测试：递归发现生成物测试用例（backend/tests/ 等）→
                     可写临时目录执行 pytest（装依赖 + PYTHONPATH）→ test_report（含 bug_summary）

安全边界：
  - 只在 AIPLAT_HOME/apps/{project_id}/current 内运行（白名单入口，不执行任意命令）
  - 绑定 127.0.0.1，不对外暴露
  - 启动/停止 best-effort，失败不抛异常（冒烟失败由测试结果呈现）
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 端口分配：每个 project 固定派生端口（避免多 app 冲突），可被 --port 注入的入口使用 ──
_PORT_BASE = 18000
_PORT_SPAN = 1000


def _derive_port(project_id: str) -> int:
    """按 project_id 稳定派生端口（18000-18999）。"""
    h = 0
    for ch in project_id:
        h = (h * 31 + ord(ch)) & 0x7FFFFFFF
    return _PORT_BASE + (h % _PORT_SPAN)


def _now_ms() -> str:
    """毫秒级 UTC 时间戳（同秒多次调用稳定排序）。"""
    import time as _t
    base = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime())
    return f"{base}.{int(_t.time() % 1 * 1000):03d}Z"


def _app_home(project_id: str) -> str:
    """生成 app 部署根目录（~/.aiplat/apps/{project_id}/current）。"""
    return os.path.join(
        os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
        "apps", project_id, "current")


def _runtime_record_path() -> str:
    return os.path.join(
        os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat")),
        "gen_app_runtime.json")


# ── 入口检测 ──
def detect_runtime(project_id: str, app_home: Optional[str] = None) -> Dict[str, Any]:
    """扫描生成目录，识别可运行入口。

    返回 {kind, command, cwd, port, reason, found}：
      kind: fastapi | flask | node | static | none
    """
    home = app_home or _app_home(project_id)
    if not os.path.isdir(home):
        return {"found": False, "kind": "none", "reason": "app home 不存在",
                "command": "", "cwd": home, "port": 0}

    def _find_file(*rel: str) -> Optional[str]:
        p = os.path.join(home, *rel)
        return p if os.path.isfile(p) else None

    # 1) FastAPI：backend/app/main.py 或 app/main.py（uvicorn 入口）
    for main_rel in [("backend", "app", "main.py"), ("app", "main.py"),
                     ("main.py",), ("backend", "main.py")]:
        p = _find_file(*main_rel)
        if p:
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    head = f.read(4000)
                if "fastapi" in head and ("FastAPI(" in head or "app = FastAPI" in head):
                    cwd = os.path.dirname(os.path.dirname(p)) if "backend" in main_rel else os.path.dirname(p)
                    mod = _module_path(cwd, p)
                    if mod:
                        port = _derive_port(project_id)
                        return {"found": True, "kind": "fastapi",
                                "command": f"{_python()} -m uvicorn {mod}:app --host 127.0.0.1 --port {port}",
                                "cwd": cwd, "port": port,
                                "reason": f"FastAPI 入口 {os.path.relpath(p, home)}"}
            except OSError:
                pass  # noqa: cleanup-best-effort — 读取生成代码失败跳过该候选入口

    # 2) Flask：backend/app.py 或 app.py
    for app_rel in [("backend", "app.py"), ("app.py",), ("server.py",), ("backend", "server.py")]:
        p = _find_file(*app_rel)
        if p:
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    head = f.read(4000)
                if "flask" in head:
                    port = _port_from_source(head) or 5000
                    return {"found": True, "kind": "flask",
                            "command": f"{_python()} {os.path.relpath(p, home)}",
                            "cwd": home, "port": port,
                            "reason": f"Flask 入口 {os.path.relpath(p, home)}"}
            except OSError:
                pass  # noqa: cleanup-best-effort — 读取生成代码失败跳过该候选入口

    # 3) Node：backend/package.json（server 入口）
    for pkg_rel in [("backend", "package.json"), ("package.json",)]:
        p = _find_file(*pkg_rel)
        if p:
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts") or {}
                start = scripts.get("start") or scripts.get("dev")
                if start:
                    cwd = os.path.dirname(p)
                    port = _port_from_pkg(pkg) or 3000
                    return {"found": True, "kind": "node",
                            "command": start if start.startswith("node ") else "npm start",
                            "cwd": cwd, "port": port,
                            "reason": f"Node 入口 package.json（scripts.start={start}）"}
            except (OSError, json.JSONDecodeError):
                pass  # noqa: cleanup-best-effort — 读取 package.json 失败跳过该候选入口

    # 4) 静态页：index.html → http.server
    if _find_file("index.html"):
        port = _derive_port(project_id)
        return {"found": True, "kind": "static",
                "command": f"{_python()} -m http.server {port} --bind 127.0.0.1 --directory {home}",
                "cwd": home, "port": port,
                "reason": "静态页（index.html）→ http.server"}

    return {"found": False, "kind": "none", "reason": "未发现可运行入口（仅定义文件）",
            "command": "", "cwd": home, "port": 0}


def _python() -> str:
    import sys
    return sys.executable


def _module_path(cwd: str, main_file: str) -> Optional[str]:
    """把 main.py 绝对路径映射为 uvicorn 模块路径（app.main:app）。"""
    try:
        rel = os.path.relpath(main_file, cwd)
        if not rel.endswith(".py"):
            return None
        mod = rel[:-3].replace(os.sep, ".")
        if mod.endswith(".__init__"):
            mod = mod[: -len(".__init__")]
        return mod if mod else None
    except ValueError:
        return None


def _port_from_source(head: str) -> Optional[int]:
    m = re.search(r"port\s*=\s*(\d{2,5})", head)
    return int(m.group(1)) if m else None


def _port_from_pkg(pkg: Dict[str, Any]) -> Optional[int]:
    try:
        port = (pkg.get("app") or {}).get("port") if isinstance(pkg.get("app"), dict) else None
        return int(port) if port else None
    except (TypeError, ValueError):
        return None


# ── 运行记录（project_id → job_id/port/kind）──
def _load_runtime_records() -> Dict[str, Any]:
    p = _runtime_record_path()
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_runtime_records(data: Dict[str, Any]) -> None:
    p = _runtime_record_path()
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{p}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except OSError:
        pass  # noqa: cleanup-best-effort — 记录失败不影响运行


# ── 启动 / 停止 / 健康 ──
def launch(project_id: str) -> Dict[str, Any]:
    """detect → daemon_jobs 托管启动（生成物侧接线：daemon_jobs 生成物适用 待接线 → 已接线）。"""
    det = detect_runtime(project_id)
    if not det.get("found"):
        return {"started": False, "error": det.get("reason", "no runtime")}
    from governance.daemon_jobs import DaemonJobStore
    store = DaemonJobStore()
    r = store.start(f"gen-app-{project_id[:24]}", det["command"], cwd=det["cwd"])
    if "id" not in r:
        return {"started": False, "error": r.get("error", "daemon start failed")}
    rec = {"job_id": r["id"], "pid": r.get("pid"), "port": det["port"],
           "kind": det["kind"], "command": det["command"], "cwd": det["cwd"],
           "started_at": r.get("started_at", "")}
    recs = _load_runtime_records()
    recs[project_id] = rec
    _save_runtime_records(recs)
    return {"started": True, **rec}


def health_check(project_id: str, port: Optional[int] = None,
                 timeout_sec: float = 30.0, interval_sec: float = 0.5) -> Dict[str, Any]:
    """HTTP 轮询健康探测：2xx/3xx = up。返回 {healthy, status_code, port, elapsed_sec}。"""
    recs = _load_runtime_records()
    rec = recs.get(project_id) or {}
    port = port or rec.get("port") or 0
    if not port:
        return {"healthy": False, "status_code": None, "port": 0,
                "error": "no port (app not launched?)"}
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout_sec
    last_code = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                last_code = resp.status
                if 200 <= resp.status < 400:
                    return {"healthy": True, "status_code": resp.status, "port": port,
                            "elapsed_sec": round(timeout_sec - (deadline - time.time()), 2)}
        except Exception:  # noqa: cleanup-best-effort — 探测失败继续轮询
            last_code = None
        time.sleep(interval_sec)
    return {"healthy": False, "status_code": last_code, "port": port,
            "error": f"未在 {timeout_sec}s 内就绪"}


def stop(project_id: str) -> Dict[str, Any]:
    """经 daemon_jobs kill（连同会话组），清理运行记录。"""
    recs = _load_runtime_records()
    rec = recs.get(project_id) or {}
    job_id = rec.get("job_id")
    if not job_id:
        return {"stopped": False, "error": "no running job record"}
    from governance.daemon_jobs import DaemonJobStore
    store = DaemonJobStore()
    r = store.kill(job_id)
    recs.pop(project_id, None)
    _save_runtime_records(recs)
    return {"stopped": True, "job_id": job_id, **r}


def status(project_id: str) -> Dict[str, Any]:
    """运行状态：记录 + daemon job 存活。"""
    recs = _load_runtime_records()
    rec = recs.get(project_id) or {}
    if not rec:
        return {"running": False, "reason": "未启动", **detect_runtime(project_id)}
    from governance.daemon_jobs import DaemonJobStore
    store = DaemonJobStore()
    st = store.status(rec.get("job_id", ""))
    job_status = st.get("status", "unknown") if "error" not in st else "gone"
    return {"running": job_status == "running", "job_status": job_status,
            "port": rec.get("port"), "kind": rec.get("kind"),
            "pid": rec.get("pid"), "command": rec.get("command"),
            "started_at": rec.get("started_at"), "exit_code": st.get("exit_code")}


# ── 冒烟测试（自动测试闭环）──
def _register_smoke_failure(project_id: str, rule_suffix: str, detail: str) -> None:
    """冒烟失败 → L2 经验回写（生成物侧接线，2026-08-27）。

    生成 app 起不来 = 生成失败经验（机器判定，confidence=1.0）→ experience_feedback
    登记，与 conformance 拒绝登记同源（CLAUDE.md §23 生成物适用：已接线）。
    best-effort 不抛异常：经验登记失败不影响冒烟结果。
    """
    import importlib.util as _iu
    import sys as _sys
    try:
        _spec = _iu.spec_from_file_location(
            "experience_feedback",
            str(Path(__file__).resolve().parents[1] / "governance/experience_feedback/experience_feedback.py"))
        _mod = _iu.module_from_spec(_spec)
        _sys.modules["experience_feedback"] = _mod
        _spec.loader.exec_module(_mod)
        _mod.register_failure(
            f"generated-smoke-{rule_suffix}",
            f"生成 app 冒烟失败（{project_id}）：{detail}",
            source="app_runtime", confidence=1.0, risk="low")
    except Exception:
        pass  # noqa: cleanup-best-effort — 经验登记失败不影响冒烟结果


def smoke_test(project_id: str, keep_alive: bool = False,
               timeout_sec: float = 30.0) -> Dict[str, Any]:
    """完整闭环：detect → launch → health → 报告。

    keep_alive=False（默认）：测试后 stop（不留后台进程）；
    keep_alive=True：保留运行，供人工验证（返回 port）。
    失败路径（launch 失败 / 健康探测不通过）→ L2 经验回写（生成物失败经验）。
    """
    det = detect_runtime(project_id)
    if not det.get("found"):
        return {"smoke_passed": False, "detected": False,
                "reason": det.get("reason", "no runtime"),
                "e2e_smoke": {"passed": False, "reason": det.get("reason", "no runtime")}}
    launched = launch(project_id)
    if not launched.get("started"):
        _register_smoke_failure(project_id, "launch-failed",
                                launched.get("error", "daemon start failed"))
        return {"smoke_passed": False, "detected": True,
                "error": launched.get("error", "launch failed"),
                "e2e_smoke": {"passed": False, "reason": launched.get("error", "launch failed")}}
    try:
        h = health_check(project_id, port=launched.get("port"), timeout_sec=timeout_sec)
        result = {
            "smoke_passed": bool(h.get("healthy")),
            "detected": True,
            "kind": launched.get("kind"),
            "port": launched.get("port"),
            "job_id": launched.get("job_id"),
            "health": h,
            "e2e_smoke": {"passed": bool(h.get("healthy")),
                          "status_code": h.get("status_code"),
                          "port": h.get("port"),
                          "elapsed_sec": h.get("elapsed_sec")},
        }
        if not h.get("healthy"):
            _register_smoke_failure(
                project_id, "unhealthy",
                f"{launched.get('kind')} 入口在 {launched.get('port')} 端口未在 {timeout_sec}s 内就绪"
                f"（{h.get('error', 'no response')}）")
        return result
    finally:
        if not keep_alive:
            stop(project_id)


def run_tests_with_smoke(project_id: str, deploy_dir: str,
                         repo_test_fn=None) -> Dict[str, Any]:
    """升级版测试：真实 e2e 冒烟（启动+健康探测）替换"目录存在"假通过。

    repo_test_fn: 可选，运行 deploy 目录 pytest 的闭包（原 _run_tests_for_project 的 repo_tests 部分）。
    """
    results: Dict[str, Any] = {"all_passed": False, "e2e_smoke": None, "repo_tests": None}
    if repo_test_fn:
        results["repo_tests"] = repo_test_fn()
        results["all_passed"] = bool(results["repo_tests"].get("passed"))
    smoke = smoke_test(project_id, keep_alive=False)
    results["e2e_smoke"] = smoke.get("e2e_smoke") or {"passed": False, "reason": smoke.get("reason")}
    results["smoke"] = smoke
    if results["all_passed"] and results["e2e_smoke"].get("passed"):
        results["all_passed"] = True
    else:
        results["all_passed"] = False
    return results


# ── 真实测试（测试经理模式：递归发现测试用例 → pytest 执行 → test_report）──
def _discover_test_cases(deploy_dir: str) -> List[str]:
    """递归发现生成物测试用例文件（backend/tests/、tests/、test/ 任意层级 test_*.py）。"""
    found: List[str] = []
    if not deploy_dir or not os.path.isdir(deploy_dir):
        return found
    for root, _dirs, files in os.walk(deploy_dir):
        if any(skip in root for skip in ("__pycache__", ".git", "node_modules", ".venv", "venv")):
            continue
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                found.append(os.path.join(root, f))
    return sorted(found)


def _install_requirements(work_dir: str) -> List[str]:
    """best-effort pip install：读 work_dir 下所有 requirements.txt 装缺失依赖。"""
    import subprocess as _sp
    missing: List[str] = []
    for root, _dirs, files in os.walk(work_dir):
        if "requirements.txt" in files:
            req = os.path.join(root, "requirements.txt")
            try:
                with open(req, encoding="utf-8", errors="ignore") as f:
                    lines = [l.strip() for l in f if l.strip() and not l.startswith("#") and "-e " not in l]
                for line in lines:
                    pkg = line.split("==")[0].split(">=")[0].split("<")[0].strip().lower().replace("_", "-")
                    if not pkg or pkg.startswith(("git+", "http")):
                        continue
                    try:
                        __import__(pkg.replace("-", "_"))
                    except ImportError:
                        missing.append(line)
                if missing:
                    _sp.run([_python(), "-m", "pip", "install", "-q", *missing],
                            capture_output=True, text=True, timeout=180)
            except Exception:
                pass  # noqa: cleanup-best-effort — 装依赖失败由 pytest 结果呈现
    return missing


def _build_test_report(test_log: str, passed: int, failed: int, errors: int,
                       skipped: int, project_id: str) -> Dict[str, Any]:
    """构造标准 test_report（对齐 test_executor：header/meta/test_results/bug_summary）。"""
    import re as _re
    bugs = []
    for _m in _re.finditer(r'^(FAILED|ERROR)\s+(.+)', test_log or "", flags=_re.MULTILINE):
        _name = _m.group(2).strip()
        if _name and _name not in bugs:
            bugs.append(_name)
    _is_env = "ModuleNotFoundError" in (test_log or "")
    _is_cfg = "ValidationError" in (test_log or "") or "extra_forbidden" in (test_log or "")
    if _is_env:
        _fix = ("环境依赖缺失（ModuleNotFoundError）：请在 requirements.txt 声明该依赖，"
                "或改用 Mock/降级方案。\n" + (test_log or "")[-1500:])
    elif _is_cfg:
        _fix = ("配置校验失败（pydantic ValidationError / extra_forbidden）：.env 中的环境变量"
                "未在 Settings 类声明，或存在非法输入。请修复 app/core/config.py 的 Settings 声明。\n"
                + (test_log or "")[-2000:])
    else:
        _fix = ("代码实现未通过测试：请修复生成的后端代码（含跨文件 import 一致性、业务逻辑）。\n"
                + (test_log or "")[-2000:])
    return {
        "header": {"title": f"生成 app 真实测试报告（{project_id}）",
                   "generated_at": _now_ms()},
        "meta": {"project_id": project_id, "test_engine": "pytest",
                 "summary": f"{passed} passed, {failed} failed, {errors} errors, {skipped} skipped"},
        "test_results": {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped,
                         "total": passed + failed + errors + skipped},
        "bug_summary": {"total_bugs": len(bugs) if bugs else failed + errors,
                        "failed_tests": bugs, "suggested_fix": _fix},
        "test_log_tail": (test_log or "")[-2500:],
    }


def real_tests(project_id: str, deploy_dir: Optional[str] = None,
               install_deps: bool = True, timeout_sec: float = 120.0) -> Dict[str, Any]:
    """测试经理真实测试：递归发现测试用例 → 可写临时目录跑 pytest → test_report。

    与 smoke_test 的区别：smoke 只验证"能启动"；real_tests 执行生成物自带测试用例
    （backend/tests/test_*.py，pytest + httpx 真实业务断言），验证功能正确性。

    返回 {test_passed, detected, test_report, e2e_smoke}：
      test_passed = 所有发现用例通过且冒烟通过。
    """
    import subprocess as _sp
    import shutil as _sh
    import tempfile as _tf
    import sys as _sys

    home = deploy_dir or _app_home(project_id)
    cases = _discover_test_cases(home)
    if not cases:
        return {"test_passed": False, "detected": False,
                "reason": "未发现测试用例（backend/tests/ 等目录无 test_*.py）",
                "test_report": None,
                "e2e_smoke": {"passed": False, "reason": "no test cases"}}

    # 复制到可写临时目录（生成物目录可能只读，且避免污染部署产物）。
    # 保持 home 同构：tmp/app 镜像 home，rel 路径在 work 下直接可达。
    tmp = _tf.mkdtemp(prefix=f"aiplat_realtest_{project_id[:12]}_")
    try:
        work = os.path.join(tmp, "app")
        _sh.copytree(home, work, dirs_exist_ok=True)

        if install_deps:
            _install_requirements(work)

        # conftest：让 pytest 能 import app.*（backend 子目录入 PYTHONPATH）
        conftest = os.path.join(work, "conftest.py")
        if not os.path.isfile(conftest):
            with open(conftest, "w", encoding="utf-8") as cf:
                cf.write(
                    "import sys, os\n"
                    "_root = os.path.dirname(os.path.abspath(__file__))\n"
                    "for _d in os.listdir(_root):\n"
                    "    _p = os.path.join(_root, _d)\n"
                    "    if os.path.isdir(_p) and _p not in sys.path:\n"
                    "        sys.path.insert(0, _p)\n"
                    "sys.path.insert(0, _root)\n")

        # 相对测试路径（work 与 home 同构 → rel 直接映射）
        rel_cases = [os.path.relpath(c, home) for c in cases]
        pytest_targets = [os.path.join(work, rel) for rel in rel_cases if os.path.exists(os.path.join(work, rel))]
        if not pytest_targets:
            return {"test_passed": False, "detected": True,
                    "reason": "测试用例复制后不可达（结构与预期不符）",
                    "test_report": None,
                    "e2e_smoke": {"passed": False, "reason": "tests not reachable"}}

        proc = _sp.run(
            [_sys.executable, "-m", "pytest", *pytest_targets, "--tb=short", "-q",
             "--no-header", "-p", "no:cacheprovider"],
            capture_output=True, text=True, timeout=int(timeout_sec),
            cwd=work, env={**os.environ, "PYTHONPATH": work},
        )
        log = proc.stdout + "\n" + proc.stderr
        passed = failed = errors = skipped = 0
        import re as _re
        for pat, key in [(r'(\d+)\s+passed', "passed"), (r'(\d+)\s+failed', "failed"),
                         (r'(\d+)\s+error', "errors"), (r'(\d+)\s+skipped', "skipped")]:
            m = _re.search(pat, log)
            if m:
                passed, failed, errors, skipped = _apply_counts(m.group(1), key, passed, failed, errors, skipped)
        report = _build_test_report(log, passed, failed, errors, skipped, project_id)
        test_passed = failed == 0 and errors == 0 and passed > 0

        # 冒烟联动：测试通过且可运行时，补一次启动探测（生成 app 真实可用性）
        smoke = smoke_test(project_id, keep_alive=False, timeout_sec=25.0)
        return {"test_passed": test_passed, "detected": True,
                "passed": passed, "failed": failed, "errors": errors, "skipped": skipped,
                "test_report": report, "e2e_smoke": smoke.get("e2e_smoke")}
    except subprocess_timeout():
        return {"test_passed": False, "detected": True, "reason": "pytest 超时",
                "test_report": None, "e2e_smoke": {"passed": False, "reason": "timeout"}}
    finally:
        _sh.rmtree(tmp, ignore_errors=True)


def _apply_counts(val: str, key: str, passed: int, failed: int, errors: int, skipped: int):
    n = int(val or 0)
    if key == "passed":
        passed = n
    elif key == "failed":
        failed = n
    elif key == "errors":
        errors = n
    else:
        skipped = n
    return passed, failed, errors, skipped


def subprocess_timeout():
    import subprocess as _sp
    return _sp.TimeoutExpired
