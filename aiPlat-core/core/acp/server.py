"""ACP (Agent Communication Protocol) server — FastAPI WebSocket edition.
Enables IDE integration (VS Code / JetBrains).

Entry: ws://localhost:8005/acp
Config: AIPLAT_ACP_PORT (default 8005)
"""
import json, os, sys, asyncio, subprocess, traceback, uuid
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

app = FastAPI(title="aiPlat ACP Server", version="1.0.0")

class ACPHandler:
    def __init__(self):
        self._adapter = None
        self._model_name = None

    async def _ensure_llm(self):
        if self._adapter is not None:
            return
        try:
            acp_dir = os.path.dirname(os.path.abspath(__file__))
            core_dir = os.path.dirname(acp_dir)
            repo_root = os.path.dirname(core_dir)
            core_path = os.path.join(repo_root, 'aiPlat-core')
            if core_path not in sys.path:
                sys.path.insert(0, core_path)
            from core.harness.utils.model_injection import best_model_for_purpose, create_selected_adapter
            self._model_name = os.environ.get("AIPLAT_ACP_MODEL", "")
            if not self._model_name:
                self._model_name = best_model_for_purpose("chat")
            self._adapter = create_selected_adapter(model_name=self._model_name)
        except Exception as e:
            print(f"  [!] ACP LLM init failed: {e}", file=sys.stderr)

    async def handle_chat(self, data: dict) -> str:
        content = data.get("content", "").strip()
        session_id = data.get("session_id", str(uuid.uuid4())[:8])
        if not content:
            return json.dumps({"type": "chat_response", "error": "empty content"})

        await self._ensure_llm()
        if not self._adapter:
            return json.dumps({
                "type": "chat_response",
                "content": "ACP LLM adapter not initialized. Set AIPLAT_LLM_API_KEY.",
                "session_id": session_id
            })

        try:
            from core.harness.syscalls.llm import sys_llm_generate
            response = await sys_llm_generate(
                self._adapter,
                prompt=[{"role": "user", "content": content}],
                model_name=self._model_name,
                temperature=0.7,
                max_tokens=4096,
            )
            return json.dumps({
                "type": "chat_response",
                "content": response.content,
                "session_id": session_id,
                "model": self._model_name,
            })
        except Exception as e:
            return json.dumps({"type": "chat_response", "error": str(e)[:500], "session_id": session_id})

    async def handle_diff(self, data: dict) -> str:
        code = data.get("content", "").strip()
        language = data.get("language", "python")
        if not code:
            return json.dumps({"type": "diff_response", "error": "empty diff content"})

        await self._ensure_llm()
        if not self._adapter:
            return json.dumps({"type": "diff_response", "analysis": "ACP LLM adapter not initialized.", "suggestions": []})

        try:
            from core.harness.syscalls.llm import sys_llm_generate
            prompt = f"""You are a senior code reviewer. Analyze the following {language} code diff.
Return JSON with: "summary", "issues", "suggestions", "risk".
Code: ```\n{code[:8000]}\n```"""

            response = await sys_llm_generate(
                self._adapter,
                prompt=[{"role": "user", "content": prompt}],
                model_name=self._model_name,
                temperature=0.1,
                max_tokens=2048,
            )
            return json.dumps({
                "type": "diff_response",
                "analysis": response.content,
                "model": self._model_name,
            })
        except Exception as e:
            return json.dumps({"type": "diff_response", "error": str(e)[:500]})

    async def handle_exec(self, data: dict) -> str:
        command = data.get("command", "").strip()
        cwd = data.get("cwd", os.getcwd())
        if not command:
            return json.dumps({"type": "exec_response", "error": "empty command"})

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            return json.dumps({
                "type": "exec_response",
                "stdout": stdout.decode(errors="ignore")[:10000],
                "stderr": stderr.decode(errors="ignore")[:10000],
                "exit_code": proc.returncode or 0,
            })
        except asyncio.TimeoutError:
            return json.dumps({"type": "exec_response", "error": "Command timed out (30s)", "exit_code": -1})
        except Exception as e:
            return json.dumps({"type": "exec_response", "error": str(e)[:500], "exit_code": -1})

    async def handle_status(self, data: dict) -> str:
        return json.dumps({
            "type": "status_response",
            "agent": "aiPlat ACP Server",
            "version": "1.0.0",
            "model": self._model_name or "not initialized",
            "protocol_version": "1.0",
            "capabilities": ["chat", "diff", "exec"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })

    async def dispatch(self, message: str) -> str:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return json.dumps({"type": "error", "content": "Invalid JSON"})

        msg_type = data.get("type", "")
        handler_map = {
            "chat": self.handle_chat,
            "diff": self.handle_diff,
            "exec": self.handle_exec,
            "status": self.handle_status,
        }
        handler = handler_map.get(msg_type)
        if not handler:
            return json.dumps({
                "type": "error",
                "content": f"Unknown message type: {msg_type}. Supported: chat, diff, exec, status"
            })
        try:
            return await handler(data)
        except Exception as e:
            return json.dumps({
                "type": "error",
                "content": f"Handler error for {msg_type}: {str(e)[:500]}",
                "traceback": traceback.format_exc()[:1000],
            })


@app.websocket("/acp")
async def acp_websocket(ws: WebSocket):
    await ws.accept()
    handler = ACPHandler()
    client = ws.client.host if ws.client else "unknown"
    print(f"  [ACP] Client connected: {client}")
    try:
        while True:
            raw = await ws.receive_text()
            resp = await handler.dispatch(raw)
            await ws.send_text(resp)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"  [ACP] Error: {e}", file=sys.stderr)
        try:
            await ws.send_text(json.dumps({"type": "error", "content": f"Server error: {str(e)[:500]}"}))
        except Exception:
            pass
    finally:
        print(f"  [ACP] Client disconnected: {client}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "acp", "version": "1.0.0"}


def start():
    port = int(os.environ.get("AIPLAT_ACP_PORT", 8005))
    host = os.environ.get("AIPLAT_ACP_HOST", "127.0.0.1")
    print(f"  [ACP] Starting ACP server on ws://{host}:{port}/acp")
    print(f"  [ACP] Supported: chat, diff, exec, status")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start()
