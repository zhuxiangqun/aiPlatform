"""agent_messages.py — 运行中 agent/任务消息总线（prime-agent agent_message.send 借鉴）。

运行中的 agent 或后台任务（daemon job）可以注册、点对点互发消息、查收件箱——
不经用户/主编排器中转。与 daemon_jobs 配合：后台任务间协作、主进程监控子任务。

能力：
  register    agent 上线（记录 pid 心跳，重复注册刷新）
  unregister  下线
  send        点对点消息（存收件箱，pending/read 状态）
  inbox       查收件箱（可选标记已读 / 只看未读）
  list_agents 在线 agent 列表（pid 存活刷新心跳）

存储：JSON（AIPLAT_AGENT_MESSAGES_FILE 配置，默认 $AIPLAT_HOME/agent_messages.json）。

用法（Python）:
    from governance.agent_messages import AgentMessageStore
    store = AgentMessageStore()
    store.register("job-1", pid=123)
    store.send("job-1", "job-2", "上游产物已就绪")

用法（CLI）:
    python3 aiPlat-platform/governance/agent_messages.py --register --agent <id> [--pid <n>]
    python3 .../agent_messages.py --unregister --agent <id>
    python3 .../agent_messages.py --send --from <id> --to <id> --message "<text>"
    python3 .../agent_messages.py --inbox --agent <id> [--unread] [--mark-read]
    python3 .../agent_messages.py --agents
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_path() -> str:
    env = os.environ.get("AIPLAT_AGENT_MESSAGES_FILE")
    if env:
        return env
    home = os.environ.get("AIPLAT_HOME") or os.path.expanduser("~/.aiplat")
    return os.path.join(home, "agent_messages.json")


def _pid_alive(pid: Optional[int]) -> bool:
    """进程存活（ps stat，僵尸视为退出；无 pid 则视为离线）。"""
    if not pid:
        return False
    try:
        r = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=5)
        stat = (r.stdout or "").strip()
        if not stat:
            return False
        return "Z" not in stat
    except Exception:
        return False


def _now_ms() -> str:
    base = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    return f"{base}.{int(time.time() % 1 * 1000):03d}Z"


class AgentMessageStore:
    """JSON 持久化的 agent 注册表 + 点对点收件箱。"""

    def __init__(self, path: Optional[str] = None):
        self.path = path or _default_path()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {"agents": {}, "messages": []}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {"agents": {}, "messages": []}
        except (json.JSONDecodeError, OSError):
            return {"agents": {}, "messages": []}

    def _save(self, data: Dict[str, Any]) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ── 注册 ──
    def register(self, agent_id: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = self._load()
        now = _now_ms()
        rec = data["agents"].get(agent_id) or {}
        rec.update({
            "agent_id": agent_id, "pid": (meta or {}).get("pid"),
            "kind": (meta or {}).get("kind", "agent"),
            "registered_at": rec.get("registered_at", now),
            "heartbeat_at": now,
        })
        data["agents"][agent_id] = rec
        self._save(data)
        return {"registered": True, "agent_id": agent_id, "heartbeat_at": now}

    def unregister(self, agent_id: str) -> Dict[str, Any]:
        data = self._load()
        if agent_id not in data["agents"]:
            return {"error": f"agent not found: {agent_id}"}
        del data["agents"][agent_id]
        self._save(data)
        return {"unregistered": True, "agent_id": agent_id}

    # ── 消息 ──
    def send(self, from_id: str, to_id: str, message: str) -> Dict[str, Any]:
        data = self._load()
        if to_id not in data["agents"]:
            return {"error": f"recipient not registered: {to_id}"}
        msg = {
            "id": f"msg-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}",
            "from": from_id, "to": to_id, "message": message,
            "status": "pending", "created_at": _now_ms(),
        }
        data["messages"].append(msg)
        # 收件箱只保留最近 500 条，防无限增长
        data["messages"] = data["messages"][-500:]
        self._save(data)
        return {"sent": True, "id": msg["id"]}

    def inbox(self, agent_id: str, unread_only: bool = False,
              mark_read: bool = False) -> Dict[str, Any]:
        data = self._load()
        msgs = [m for m in data["messages"] if m.get("to") == agent_id]
        if unread_only:
            msgs = [m for m in msgs if m.get("status") == "pending"]
        if mark_read:
            for m in data["messages"]:
                if m.get("to") == agent_id and m.get("status") == "pending":
                    m["status"] = "read"
            self._save(data)
        msgs.sort(key=lambda m: m.get("created_at", ""), reverse=True)
        return {"agent_id": agent_id, "count": len(msgs), "messages": msgs}

    def list_agents(self) -> List[Dict[str, Any]]:
        """在线 agent 列表：pid 存活刷新心跳，离线标记。"""
        data = self._load()
        agents = []
        for rec in data["agents"].values():
            alive = _pid_alive(rec.get("pid"))
            agents.append({
                "agent_id": rec.get("agent_id"), "kind": rec.get("kind"),
                "pid": rec.get("pid"), "online": alive,
                "heartbeat_at": rec.get("heartbeat_at"),
            })
        agents.sort(key=lambda a: a.get("heartbeat_at", ""), reverse=True)
        return agents


# ── CLI ──
def _cli(argv: List[str]) -> int:
    path = os.environ.get("AIPLAT_AGENT_MESSAGES_FILE")

    def arg(name: str, default: str = "") -> str:
        if name in argv:
            i = argv.index(name)
            return argv[i + 1] if i + 1 < len(argv) else default
        return default

    store = AgentMessageStore(path)
    if "--register" in argv:
        pid = arg("--pid")
        r = store.register(arg("--agent"), meta={"pid": int(pid) if pid else None,
                                                 "kind": arg("--kind", "agent")})
        print(json.dumps(r, ensure_ascii=False))
        return 0
    if "--unregister" in argv:
        print(json.dumps(store.unregister(arg("--agent")), ensure_ascii=False))
        return 0
    if "--send" in argv:
        r = store.send(arg("--from"), arg("--to"), arg("--message"))
        print(json.dumps(r, ensure_ascii=False))
        return 0 if "id" in r else 1
    if "--inbox" in argv:
        r = store.inbox(arg("--agent"), unread_only="--unread" in argv,
                        mark_read="--mark-read" in argv)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    if "--agents" in argv:
        print(json.dumps(store.list_agents(), ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(_cli(sys.argv[1:]))
