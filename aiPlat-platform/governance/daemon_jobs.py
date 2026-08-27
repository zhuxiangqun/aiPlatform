"""daemon_jobs.py — 后台任务托管（daemon job runner，prime-agent 断线续跑借鉴）。

长任务（pipeline 执行、批量处理、多轮实施）脱离发起终端运行：
  start  → subprocess 后台进程（新会话组：终端关闭不终止）+ 输出重定向文件 + JSON 注册表
  status → 按需查看进度（pid 存活 + 输出文件尾部退出码标记）
  attach → tail 输出
  kill   → 终止

存储：JSON（AIPLAT_DAEMON_JOBS_FILE 配置，默认 $AIPLAT_HOME/daemon_jobs.json；
输出日志同目录 jobs/{id}.log）。

用法（Python）:
    from governance.daemon_jobs import DaemonJobStore
    store = DaemonJobStore()
    job = store.start("pipeline-rebuild", "bash scripts/rebuild.sh", cwd="/repo")
    store.status(job["id"])

用法（CLI）:
    python3 aiPlat-platform/governance/daemon_jobs.py --start --name <n> --command "<cmd>" [--cwd <dir>]
    python3 .../daemon_jobs.py --status [<id>]
    python3 .../daemon_jobs.py --attach <id> [--lines 50]
    python3 .../daemon_jobs.py --kill <id>
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_EXIT_MARKER = "[daemon] exit="


def _now_ms() -> str:
    """毫秒级 UTC 时间戳（同秒多次 start 也能稳定排序）。"""
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return f"{base}.{int(time.time() % 1 * 1000):03d}Z"


def _pid_alive(pid: int) -> bool:
    """进程存活判断：ps stat 解析，僵尸（Z）视为已退出（跨 macOS/Linux）。"""
    try:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        stat = (r.stdout or "").strip()
        if not stat:
            return False
        return "Z" not in stat
    except Exception:
        return False


def _default_path() -> str:
    env = os.environ.get("AIPLAT_DAEMON_JOBS_FILE")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    return os.path.join(home, "daemon_jobs.json")


class DaemonJobStore:
    """JSON 持久化的后台任务注册表。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_path()
        self._jobs_dir = Path(self.path).parent / "jobs"

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"jobs": {}}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"jobs": {}}
        except (json.JSONDecodeError, OSError):
            return {"jobs": {}}

    def _save(self, data: Dict[str, Any]) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _log_file(self, job_id: str) -> Path:
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        return self._jobs_dir / f"{job_id}.log"

    # ── 状态机 ──
    def start(self, name: str, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """启动后台任务：新会话组 + 输出重定向文件 + 注册。"""
        if not command or not command.strip():
            return {"error": "command 不能为空"}
        job_id = f"job-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        log = self._log_file(job_id)
        wrapped = f"{command} 2>&1; echo {_EXIT_MARKER}$?"
        with open(log, "w", encoding="utf-8") as f:
            proc = subprocess.Popen(
                wrapped, shell=True, stdout=f, stderr=subprocess.STDOUT,
                start_new_session=True, cwd=cwd,
            )
        now = _now_ms()
        rec = {
            "id": job_id, "name": name or command[:60], "command": command,
            "cwd": cwd, "pid": proc.pid, "status": "running",
            "started_at": now, "updated_at": now, "exit_code": None,
            "log": str(log),
        }
        data = self._load()
        data["jobs"][job_id] = rec
        self._save(data)
        return {"id": job_id, "pid": proc.pid, "status": "running", "log": str(log)}

    def _refresh(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        """轮询 pid 存活（ps stat，僵尸视为已退出）+ 输出文件退出码标记，刷新状态。"""
        pid = rec.get("pid")
        alive = False
        if pid:
            alive = _pid_alive(pid)
        if alive:
            rec["status"] = "running"
            return rec
        # 进程已退出：从输出文件末尾解析退出码标记
        log = rec.get("log")
        code = None
        if log and os.path.exists(log):
            try:
                with open(log, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for line in reversed(lines[-5:]):
                    if _EXIT_MARKER in line:
                        code = line.split(_EXIT_MARKER, 1)[1].strip()
                        break
            except OSError:  # noqa: cleanup-best-effort（读日志失败不阻断）
                pass
        if code is not None:
            rec["status"] = "finished" if code == "0" else "failed"
            rec["exit_code"] = code
        else:
            rec["status"] = "killed"  # 无退出码标记（被 kill 或异常终止）
        rec["updated_at"] = _now_ms()
        return rec

    def _sync(self) -> Dict[str, Any]:
        data = self._load()
        for rec in data["jobs"].values():
            if rec.get("status") == "running":
                self._refresh(rec)
        self._save(data)
        return data

    def list(self) -> List[Dict[str, Any]]:
        data = self._sync()
        jobs = list(data["jobs"].values())
        jobs.sort(key=lambda j: j.get("started_at", ""), reverse=True)
        return jobs

    def status(self, job_id: str) -> Dict[str, Any]:
        data = self._sync()
        rec = data["jobs"].get(job_id)
        if not rec:
            return {"error": f"job not found: {job_id}"}
        return rec

    def attach(self, job_id: str, lines: int = 50) -> Dict[str, Any]:
        rec = self.status(job_id)
        if "error" in rec:
            return rec
        log = rec.get("log")
        content = ""
        if log and os.path.exists(log):
            try:
                with open(log, encoding="utf-8", errors="ignore") as f:
                    all_lines = f.readlines()
                content = "".join(all_lines[-lines:])
            except OSError:  # noqa: cleanup-best-effort（读输出失败不阻断）
                pass
        return {"id": job_id, "status": rec["status"], "output": content}

    def kill(self, job_id: str) -> Dict[str, Any]:
        data = self._load()
        rec = data["jobs"].get(job_id)
        if not rec:
            return {"error": f"job not found: {job_id}"}
        pid = rec.get("pid")
        if pid:
            # 杀整个会话组（start_new_session），连带 shell 派生的子进程
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:  # noqa: cleanup-best-effort（进程已消失则忽略）
                    pass
        rec["status"] = "killed"
        rec["updated_at"] = _now_ms()
        self._save(data)
        return {"id": job_id, "status": "killed", "pid": pid}


# ── CLI ──
def _cli(argv: List[str]) -> int:
    path = os.environ.get("AIPLAT_DAEMON_JOBS_FILE")

    def arg(name: str, default: str = "") -> str:
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    store = DaemonJobStore(path)
    if "--start" in argv:
        r = store.start(arg("--name", "unnamed"), arg("--command"),
                        cwd=arg("--cwd") or None)
        print(json.dumps(r, ensure_ascii=False))
        return 0 if "id" in r else 1
    if "--status" in argv:
        jid = arg("--status")
        r = store.status(jid) if jid else {"jobs": store.list()}
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if "--attach" in argv:
        r = store.attach(arg("--attach"), int(arg("--lines", "50")))
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if "--kill" in argv:
        r = store.kill(arg("--kill"))
        print(json.dumps(r, ensure_ascii=False))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(_cli(sys.argv[1:]))
