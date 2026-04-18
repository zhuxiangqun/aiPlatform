"""
Agent Manager - Manages Agent instances

Provides CRUD operations for agents and skill/tool bindings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json
from datetime import datetime
import uuid
import os
from pathlib import Path

import yaml

from core.harness.state import AgentStateEnum


@dataclass
class AgentInfo:
    """Agent information"""
    id: str
    name: str
    type: str# ReAct, RAG, Plan, Conversational, Tool-Using, Multi-Agent
    # Canonical status values (see core.harness.state.AgentStateEnum)
    status: str
    config: Dict[str, Any]
    skills: List[str]
    tools: List[str]
    memory_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentStats:
    """Agent execution statistics"""
    total_executions: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: float =0.0
    success_rate: float = 0.0


@dataclass
class SkillBinding:
    """Skill binding to agent"""
    skill_id: str
    skill_name: str
    skill_type: str
    call_count: int = 0
    success_rate: float = 0.0
    last_called: Optional[datetime] = None


@dataclass
class ToolBinding:
    """Tool binding to agent"""
    tool_id: str
    tool_name: str
    tool_type: str
    call_count: int = 0
    success_rate: float = 0.0
    last_called: Optional[datetime] = None


@dataclass
class AgentVersion:
    """Agent version"""
    version: str
    status: str
    created_at: datetime
    changes: str


class AgentManager:
    """
    Agent Manager - Manages Agent instances
    
    Provides:
    - Agent CRUD operations
    - Agent skill/tool bindings
    - Agent execution history
    - Agent statistics
    """
    
    def __init__(
        self,
        seed: bool = True,
        *,
        scope: str = "engine",
        reserved_ids: Optional[set] = None,
    ):
        self._agents: Dict[str, AgentInfo] = {}
        self._stats: Dict[str, AgentStats] = {}
        self._skill_bindings: Dict[str, List[SkillBinding]] = {}
        self._tool_bindings: Dict[str, List[ToolBinding]] = {}
        self._execution_history: Dict[str, List[Dict]] = {}
        self._versions: Dict[str, List[AgentVersion]] = {}
        self._scope = scope  # "engine" | "workspace"
        self._reserved_ids = reserved_ids or set()
        if seed:
            self._seed_data()
        else:
            self._load_directory_agents()

    def _resolve_agents_paths(self) -> List[Path]:
        """Resolve all agents paths in increasing priority order (low -> high)."""
        repo_root = Path(__file__).resolve().parents[2]  # aiPlat-core/
        engine_default = repo_root / "core" / "engine" / "agents"
        workspace_default = Path.home() / ".aiplat" / "agents"

        scope = (self._scope or "engine").strip().lower()
        if scope not in {"engine", "workspace"}:
            scope = "engine"

        paths_env = os.environ.get(f"AIPLAT_{scope.upper()}_AGENTS_PATHS")
        if paths_env:
            parts = [p.strip() for p in paths_env.split(os.pathsep) if p.strip()]
            out = [Path(p).expanduser() for p in parts]
            return [p.resolve() for p in out]

        single = os.environ.get(f"AIPLAT_{scope.upper()}_AGENTS_PATH")
        if single:
            return [Path(single).expanduser().resolve()]

        return [engine_default.resolve()] if scope == "engine" else [workspace_default.resolve()]

    def _resolve_agents_base_path(self) -> Path:
        """Primary write target for directory-based agents (highest priority path)."""
        paths = self._resolve_agents_paths()
        return paths[-1] if paths else (Path(__file__).resolve().parents[2] / "agents")

    def _load_directory_agents(self) -> None:
        """Load directory-based agents from filesystem into management plane."""
        try:
            now = datetime.utcnow()
            # low -> high, high overrides
            for base_dir in self._resolve_agents_paths():
                if not base_dir.exists():
                    continue
                for item in base_dir.iterdir():
                    if not item.is_dir():
                        continue
                    if item.name.startswith(".") or item.name in ["__pycache__"]:
                        continue
                    agent_md = item / "AGENT.md"
                    if not agent_md.exists():
                        continue

                    raw = agent_md.read_text(encoding="utf-8")
                    fm = None
                    if raw.startswith("---"):
                        # naive split
                        parts = raw.split("---", 2)
                        if len(parts) > 1:
                            try:
                                fm = yaml.safe_load(parts[1]) or {}
                            except Exception:
                                fm = {}
                    if not isinstance(fm, dict):
                        fm = {}

                    agent_id = str(fm.get("name") or item.name)
                    display_name = str(fm.get("display_name") or agent_id)
                    description = str(fm.get("description") or "")
                    agent_type = str(fm.get("agent_type") or "react")
                    version = str(fm.get("version") or "1.0.0")
                    status = str(fm.get("status") or AgentStateEnum.READY.value)
                    status = self._normalize_status(status)

                    required_skills = fm.get("required_skills") or []
                    required_tools = fm.get("required_tools") or []
                    if not isinstance(required_skills, list):
                        required_skills = []
                    if not isinstance(required_tools, list):
                        required_tools = []

                    config = fm.get("config") or {}
                    if not isinstance(config, dict):
                        config = {}

                    metadata = dict(fm)
                    metadata.setdefault("filesystem", {})
                    if isinstance(metadata["filesystem"], dict):
                        metadata["filesystem"]["agent_dir"] = str(item)
                        metadata["filesystem"]["agent_md"] = str(agent_md)
                        metadata["filesystem"]["source"] = str(base_dir)

                    self._agents[agent_id] = AgentInfo(
                        id=agent_id,
                        name=display_name,
                        type=agent_type,
                        status=status,
                        config=config,
                        skills=list(required_skills),
                        tools=list(required_tools),
                        memory_config=metadata.get("memory_config") or {"type": "short_term", "recall_count": 5},
                        created_at=now,
                        updated_at=now,
                        version=version,
                        metadata=metadata,
                    )
                    self._stats.setdefault(agent_id, AgentStats())
                    self._skill_bindings.setdefault(agent_id, [])
                    self._tool_bindings.setdefault(agent_id, [])
                    self._execution_history.setdefault(agent_id, [])
                    self._versions.setdefault(agent_id, [AgentVersion(version=version, status="current", created_at=now, changes="Loaded from filesystem")])

            for agent_id, agent_info in self._agents.items():
                self._bridge_to_registry(agent_info)
        except Exception:
            return

    def _normalize_status(self, status: str) -> str:
        """Normalize legacy status strings to canonical AgentStateEnum values."""
        s = (status or "").strip().lower()
        mapping = {
            "pending": AgentStateEnum.INITIALIZING.value,
            "initializing": AgentStateEnum.INITIALIZING.value,
            "ready": AgentStateEnum.READY.value,
            "idle": AgentStateEnum.READY.value,
            "running": AgentStateEnum.RUNNING.value,
            "paused": AgentStateEnum.PAUSED.value,
            "stopped": AgentStateEnum.STOPPED.value,
            "error": AgentStateEnum.ERROR.value,
            "terminated": AgentStateEnum.TERMINATED.value,
        }
        return mapping.get(s, AgentStateEnum.READY.value)
    
    def _seed_data(self):
        now = datetime.utcnow()
        demo_agents = [
            ("react_agent", "ReAct助手", "react", AgentStateEnum.RUNNING.value, {"model": "gpt-4", "temperature": 0.7}, ["task_planning", "information_search"], ["search"]),
            ("rag_agent", "RAG问答引擎", "rag", AgentStateEnum.RUNNING.value, {"model": "gpt-4", "temperature": 0.3}, ["knowledge_retrieval", "summarization"], ["search"]),
            ("plan_agent", "任务规划器", "plan", AgentStateEnum.INITIALIZING.value, {"model": "gpt-4", "temperature": 0.5}, ["task_planning", "task_decomposition"], []),
            ("tool_agent", "工具调用器", "tool", AgentStateEnum.RUNNING.value, {"model": "gpt-3.5-turbo", "temperature": 0.2}, ["api_calling"], ["search", "calculator"]),
            ("conversational_agent", "对话代理", "conversational", AgentStateEnum.STOPPED.value, {"model": "gpt-3.5-turbo", "temperature": 0.8}, ["chitchat"], []),
        ]
        for agent_id, name, agent_type, status, config, skills, tools in demo_agents:
            self._agents[agent_id] = AgentInfo(
                id=agent_id, name=name, type=agent_type, status=self._normalize_status(status),
                config=config, skills=skills, tools=tools,
                memory_config={"type": "short_term", "recall_count": 5},
                created_at=now, updated_at=now, metadata={"version": "1.0.0"}
            )
            self._stats[agent_id] = AgentStats(
                total_executions=0, success_count=0, failed_count=0, avg_duration_ms=0.0, success_rate=0.0
            )
            self._skill_bindings[agent_id] = []
            self._tool_bindings[agent_id] = []
            self._execution_history[agent_id] = []
            self._versions[agent_id] = [AgentVersion(version="v1.0.0", status="current", created_at=now, changes="Initial version")]
        
        for agent_id, agent_info in self._agents.items():
            self._bridge_to_registry(agent_info)
    
    async def create_agent(
        self,
        name: str,
        agent_type: str,
        config: Dict[str, Any],
        skills: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        memory_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentInfo:
        """Create a new agent"""
        agent_id = name.lower().replace(" ", "_").replace("-", "_")
        if self._reserved_ids and agent_id in self._reserved_ids:
            raise ValueError(f"Agent id '{agent_id}' is reserved by engine scope and cannot be created in workspace.")
        now = datetime.utcnow()
        
        agent = AgentInfo(
            id=agent_id,
            name=name,
            type=agent_type,
            status=AgentStateEnum.INITIALIZING.value,
            config=config,
            skills=skills or [],
            tools=tools or [],
            memory_config=memory_config or {"type": "short_term", "recall_count": 5},
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        self._agents[agent_id] = agent
        self._stats[agent_id] = AgentStats()
        self._skill_bindings[agent_id] = []
        self._tool_bindings[agent_id] = []
        self._execution_history[agent_id] = []
        self._versions[agent_id] = [
            AgentVersion(version="v1.0.0", status="current", created_at=now, changes="Initial version")
        ]
        
        self._bridge_to_registry(agent)

        # Materialize directory-based agent on filesystem (AGENT.md + skeleton).
        try:
            base_dir = self._resolve_agents_base_path()
            agent_dir = base_dir / agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            agent_md_path = agent_dir / "AGENT.md"
            if not agent_md_path.exists():
                manifest = {
                    "name": agent_id,
                    "display_name": name,
                    "description": metadata.get("description") if isinstance(metadata, dict) else "",
                    "agent_type": agent_type,
                    "version": "1.0.0",
                    "status": agent.status,
                    "required_skills": skills or [],
                    "required_tools": tools or [],
                    "config": config or {},
                }
                header = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).strip()
                body = f"""

# {name}

## 目标
说明该 Agent 的职责边界与适用场景。

## 工作流程（SOP）
1. 第一步……
2. 第二步……
3. 第三步……

## 权限与工具
- required_tools：{tools or []}
- required_skills：{skills or []}
"""
                agent_md_path.write_text(f"---\n{header}\n---\n{body.lstrip()}", encoding="utf-8")

            if isinstance(agent.metadata, dict):
                agent.metadata.setdefault("filesystem", {})
                if isinstance(agent.metadata["filesystem"], dict):
                    agent.metadata["filesystem"]["agent_dir"] = str(agent_dir)
                    agent.metadata["filesystem"]["agent_md"] = str(agent_md_path)
        except Exception:
            pass
        
        return agent
    
    def _bridge_to_registry(self, agent_info: AgentInfo) -> None:
        """Bridge: register agent in execution-layer AgentRegistry."""
        try:
            from core.apps.agents import get_agent_registry, create_agent
            from core.harness.interfaces import AgentConfig
            
            registry = get_agent_registry()
            agent_id = agent_info.id
            agent_type = agent_info.type
            
            agent_config = AgentConfig(
                name=agent_info.name,
                model=agent_info.config.get("model", "gpt-4"),
                temperature=agent_info.config.get("temperature", 0.7),
                max_tokens=agent_info.config.get("max_tokens", 4096),
                timeout=agent_info.config.get("timeout", 30),
                max_retries=agent_info.config.get("max_retries", 3),
                metadata=agent_info.config
            )
            
            agent_instance = create_agent(
                agent_type=agent_type,
                config=agent_config
            )
            
            registry.register(agent_id, agent_instance, config=agent_info.config, metadata=agent_info.metadata)
        except Exception:
            pass
    
    async def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent by ID"""
        return self._agents.get(agent_id)
    
    async def list_agents(
        self,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AgentInfo]:
        """List agents with filters"""
        agents = list(self._agents.values())
        
        if agent_type:
            agents = [a for a in agents if a.type == agent_type]
        if status:
            agents = [a for a in agents if a.status == status]
        
        return agents[offset:offset + limit]

    def get_agent_ids(self) -> List[str]:
        """Get all agent ids currently loaded."""
        return list(self._agents.keys())
    
    async def update_agent(
        self,
        agent_id: str,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        skills: Optional[List[str]] = None,
        tools: Optional[List[str]] = None,
        memory_config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[AgentInfo]:
        """Update agent configuration"""
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        # Engine agents marked as protected are core capabilities and should not be edited via API.
        if (self._scope or "engine").strip().lower() == "engine":
            if isinstance(getattr(agent, "metadata", None), dict) and agent.metadata.get("protected") is True:
                raise PermissionError("Protected engine agent cannot be edited")
        
        if name:
            agent.name = name
        if config:
            agent.config.update(config)
        if skills is not None:
            agent.skills = skills
        if tools is not None:
            agent.tools = tools
        if memory_config:
            agent.memory_config.update(memory_config)
        if metadata:
            agent.metadata.update(metadata)
        
        agent.updated_at = datetime.utcnow()

        # Best-effort: persist updates back to directory-based AGENT.md (keep body unchanged).
        try:
            base_dir = self._resolve_agents_base_path()
            agent_dir = base_dir / agent.id
            agent_dir.mkdir(parents=True, exist_ok=True)
            agent_md_path = agent_dir / "AGENT.md"
            if agent_md_path.exists():
                raw = agent_md_path.read_text(encoding="utf-8")
                fm = None
                body = raw
                if raw.startswith("---"):
                    parts = raw.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            fm = yaml.safe_load(parts[1]) or {}
                        except Exception:
                            fm = {}
                        body = parts[2]
                if not isinstance(fm, dict):
                    fm = {}
                fm.update({
                    "name": agent.id,
                    "display_name": agent.name,
                    "description": str((agent.metadata or {}).get("description") or fm.get("description") or ""),
                    "agent_type": agent.type,
                    "version": agent.version,
                    "status": agent.status,
                    "required_skills": agent.skills or [],
                    "required_tools": agent.tools or [],
                    "config": agent.config or {},
                    "protected": (agent.metadata or {}).get("protected", fm.get("protected", False)),
                })
                header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
                agent_md_path.write_text(f"---\n{header}\n---\n{body.lstrip()}", encoding="utf-8")
        except Exception:
            pass
        
        return agent

    # ==================== SOP (AGENT.md body section) ====================

    def _read_agent_md(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Best-effort read AGENT.md and split into frontmatter/body."""
        agent = self._agents.get(agent_id)
        if not agent or not isinstance(getattr(agent, "metadata", None), dict):
            return None
        fs = (agent.metadata or {}).get("filesystem") if isinstance(agent.metadata, dict) else None
        agent_md = None
        if isinstance(fs, dict):
            agent_md = fs.get("agent_md")
        if not agent_md:
            # fallback to expected path
            try:
                base_dir = self._resolve_agents_base_path()
                agent_md = str((base_dir / agent.id / "AGENT.md"))
            except Exception:
                agent_md = None
        if not agent_md:
            return None
        try:
            from pathlib import Path
            p = Path(agent_md)
            if not p.exists():
                return None
            raw = p.read_text(encoding="utf-8")
            fm = {}
            body = raw
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = yaml.safe_load(parts[1]) or {}
                    except Exception:
                        fm = {}
                    body = parts[2]
            if not isinstance(fm, dict):
                fm = {}
            return {"path": str(p), "raw": raw, "frontmatter": fm, "body": body}
        except Exception:
            return None

    @staticmethod
    def _extract_sop_from_body(body: str) -> str:
        """Extract the '## SOP' section content from markdown body."""
        import re
        text = body or ""
        m = re.search(r"(?m)^##\\s+SOP\\s*$", text)
        if not m:
            return ""
        start = m.end()
        rest = text[start:]
        # find next H2 section
        m2 = re.search(r"(?m)^##\\s+[^\\n]+\\s*$", rest)
        sop = rest[: m2.start()] if m2 else rest
        return sop.strip("\n").strip()

    @staticmethod
    def _replace_sop_in_body(body: str, sop_markdown: str) -> str:
        """Replace or insert the '## SOP' section content."""
        import re
        text = body or ""
        sop_markdown = (sop_markdown or "").strip("\n").rstrip() + "\n"
        header = "## SOP\n"
        m = re.search(r"(?m)^##\\s+SOP\\s*$", text)
        if not m:
            # append new SOP section at end
            sep = "" if text.endswith("\n") or text == "" else "\n"
            return f"{text}{sep}\n{header}{sop_markdown}"
        start = m.end()
        rest = text[start:]
        m2 = re.search(r"(?m)^##\\s+[^\\n]+\\s*$", rest)
        before = text[:start]
        after = rest[m2.start():] if m2 else ""
        # keep one blank line between header and content
        return f"{before}\n{sop_markdown}{after.lstrip()}"

    async def get_agent_sop(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get SOP markdown for agent (workspace-friendly)."""
        info = self._read_agent_md(agent_id)
        if not info:
            return None
        sop = self._extract_sop_from_body(str(info.get("body") or ""))
        return {"agent_id": agent_id, "agent_md": info.get("path"), "sop": sop}

    async def update_agent_sop(self, agent_id: str, sop_markdown: str) -> bool:
        """Update SOP section in AGENT.md (best-effort)."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

    async def get_agent_execution_help(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution input help/examples/schema for an agent.
        Priority:
        1) AGENT.md frontmatter fields:
           - execution_help (markdown string)
           - execution_examples (list of {title, content})
           - execution_input_schema (object)
        2) Generate defaults based on bound skills/tools.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        info = self._read_agent_md(agent_id)
        fm = (info or {}).get("frontmatter") if isinstance(info, dict) else {}
        if not isinstance(fm, dict):
            fm = {}

        help_md = fm.get("execution_help")
        examples = fm.get("execution_examples")
        schema = fm.get("execution_input_schema")

        # normalize examples
        norm_examples: list[dict] = []
        if isinstance(examples, list):
            for e in examples:
                if isinstance(e, dict) and e.get("title") and e.get("content") is not None:
                    norm_examples.append({"title": str(e["title"]), "content": str(e["content"])})

        if isinstance(help_md, str) and help_md.strip():
            return {
                "agent_id": agent_id,
                "help_markdown": help_md.strip(),
                "examples": norm_examples,
                "input_schema": schema if isinstance(schema, dict) else None,
            }

        # -------------------- default help generation --------------------
        skill_ids = list(getattr(agent, "skills", []) or [])
        tool_ids = list(getattr(agent, "tools", []) or [])

        has_file_ops = "file_operations" in tool_ids
        has_code_review = "code_review" in skill_ids

        default_help = (
            "### 如何填写输入\n"
            "- 你可以输入 **文本** 或 **JSON**。\n"
            "- 如果输入不是合法 JSON，系统会自动封装为：`{\"message\": \"...\"}`。\n"
            "\n"
            "### 常见输入字段（推荐 JSON）\n"
            "- `message`：文本任务描述（最通用）\n"
            "- `directory`：要分析的目录（绝对路径）\n"
            "- `exclude`：忽略目录/文件（数组）\n"
            "- `diff`：PR diff（字符串）\n"
            "- `language`：语言/框架\n"
            "\n"
            "### 目录自动分析的前置条件\n"
            f"- 当前 Agent {'已' if has_file_ops else '未'}绑定 `file_operations` 工具。\n"
            "- 服务器需配置 `AIPLAT_FILE_OPERATIONS_ALLOWED_ROOTS` 允许读取的根目录（白名单）。\n"
        )

        if not norm_examples:
            if has_code_review:
                norm_examples = [
                    {
                        "title": "代码片段审查（文本）",
                        "content": "请审查下面代码，输出高/中/低问题清单 + 修改建议 + 安全风险 + 测试建议。\n\n语言/框架：<填写>\n代码：\n<粘贴代码>",
                    },
                    {
                        "title": "PR diff 审查（JSON）",
                        "content": json.dumps(
                            {
                                "task": "code_review",
                                "language": "<填写>",
                                "diff": "<粘贴 diff>",
                                "output": {"format": "markdown", "severity_levels": ["high", "medium", "low"]},
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    },
                    {
                        "title": "目录审查（JSON，需要 file_operations）",
                        "content": json.dumps(
                            {
                                "task": "codebase_review",
                                "directory": "/abs/path/to/repo",
                                "exclude": ["node_modules", "dist", "build", ".git", ".venv"],
                                "language": "<填写>",
                                "strategy": {"max_files": 30, "read_max_bytes": 200000},
                                "output": {"format": "markdown", "severity_levels": ["high", "medium", "low"]},
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                    },
                ]
            else:
                norm_examples = [
                    {"title": "通用任务（文本）", "content": "请完成以下任务：\n<描述你的需求>"},
                    {"title": "通用任务（JSON）", "content": json.dumps({"message": "请完成以下任务：<描述你的需求>"}, ensure_ascii=False, indent=2)},
                ]

        return {
            "agent_id": agent_id,
            "help_markdown": default_help,
            "examples": norm_examples,
            "input_schema": schema if isinstance(schema, dict) else None,
        }
        # protect engine scope agents
        if (self._scope or "engine").strip().lower() == "engine":
            if isinstance(getattr(agent, "metadata", None), dict) and agent.metadata.get("protected") is True:
                raise PermissionError("Protected engine agent cannot be edited")

        info = self._read_agent_md(agent_id)
        if not info:
            return False
        try:
            from pathlib import Path
            p = Path(str(info.get("path")))
            raw = str(info.get("raw") or "")
            fm = info.get("frontmatter") or {}
            body = str(info.get("body") or "")
            new_body = self._replace_sop_in_body(body, sop_markdown)
            header = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
            p.write_text(f"---\n{header}\n---\n{new_body.lstrip()}", encoding="utf-8")
            agent.updated_at = datetime.utcnow()
            return True
        except Exception:
            return False
    
    async def delete_agent(self, agent_id: str) -> bool:
        """Delete agent"""
        if agent_id not in self._agents:
            return False

        agent = self._agents.get(agent_id)
        if (self._scope or "engine").strip().lower() == "engine":
            if isinstance(getattr(agent, "metadata", None), dict) and agent.metadata.get("protected") is True:
                raise PermissionError("Protected engine agent cannot be deleted")
        
        del self._agents[agent_id]
        del self._stats[agent_id]
        del self._skill_bindings[agent_id]
        del self._tool_bindings[agent_id]
        del self._execution_history[agent_id]
        return True
    
    async def start_agent(self, agent_id: str) -> bool:
        """Start agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.status = AgentStateEnum.RUNNING.value
        agent.updated_at = datetime.utcnow()
        return True
    
    async def stop_agent(self, agent_id: str) -> bool:
        """Stop agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        agent.status = AgentStateEnum.STOPPED.value
        agent.updated_at = datetime.utcnow()
        return True
    
    async def bind_skills(self, agent_id: str, skill_ids: List[str]) -> bool:
        """Bind skills to agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        # Add new skills
        for skill_id in skill_ids:
            if skill_id not in agent.skills:
                agent.skills.append(skill_id)
                self._skill_bindings[agent_id].append(SkillBinding(
                    skill_id=skill_id,
                    skill_name=f"skill-{skill_id}",
                    skill_type="unknown"
                ))
        
        agent.updated_at = datetime.utcnow()
        return True
    
    async def unbind_skill(self, agent_id: str, skill_id: str) -> bool:
        """Unbind skill from agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        if skill_id in agent.skills:
            agent.skills.remove(skill_id)
            self._skill_bindings[agent_id] = [
                b for b in self._skill_bindings[agent_id] if b.skill_id != skill_id
            ]
            agent.updated_at = datetime.utcnow()
        
        return True
    
    async def get_skill_bindings(self, agent_id: str) -> List[SkillBinding]:
        """Get skill bindings for agent"""
        return self._skill_bindings.get(agent_id, [])
    
    async def bind_tools(self, agent_id: str, tool_ids: List[str]) -> bool:
        """Bind tools to agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        # Add new tools
        for tool_id in tool_ids:
            if tool_id not in agent.tools:
                agent.tools.append(tool_id)
                self._tool_bindings[agent_id].append(ToolBinding(
                    tool_id=tool_id,
                    tool_name=f"tool-{tool_id}",
                    tool_type="unknown"
                ))
        
        agent.updated_at = datetime.utcnow()
        return True
    
    async def unbind_tool(self, agent_id: str, tool_id: str) -> bool:
        """Unbind tool from agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False
        
        if tool_id in agent.tools:
            agent.tools.remove(tool_id)
            self._tool_bindings[agent_id] = [
                b for b in self._tool_bindings[agent_id] if b.tool_id != tool_id
            ]
            agent.updated_at = datetime.utcnow()
        
        return True
    
    async def get_tool_bindings(self, agent_id: str) -> List[ToolBinding]:
        """Get tool bindings for agent"""
        return self._tool_bindings.get(agent_id, [])
    
    async def get_stats(self, agent_id: str) -> Optional[AgentStats]:
        """Get agent statistics"""
        return self._stats.get(agent_id)
    
    async def record_execution(
        self,
        agent_id: str,
        execution_id: str,
        status: str,
        duration_ms: float,
        input_data: Any,
        output_data: Optional[Any] = None,
        error: Optional[str] = None
    ) -> bool:
        """Record execution history"""
        if agent_id not in self._agents:
            return False
        
        self._execution_history[agent_id].append({
            "id": execution_id,
            "status": status,
            "duration_ms": duration_ms,
            "input": input_data,
            "output": output_data,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Update stats
        stats = self._stats[agent_id]
        stats.total_executions += 1
        if status == "completed":
            stats.success_count += 1
        else:
            stats.failed_count += 1
        stats.success_rate = stats.success_count / stats.total_executions
        
        return True
    
    async def get_execution_history(
        self,
        agent_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """Get execution history"""
        history = self._execution_history.get(agent_id, [])
        return history[offset:offset + limit]
    
    def get_agent_count(self) -> Dict[str, int]:
        """Get agent count by status"""
        counts = {"total": len(self._agents), "running": 0, "stopped": 0, "error": 0, "pending": 0}
        for agent in self._agents.values():
            if agent.status in counts:
                counts[agent.status] += 1
        return counts

    async def get_versions(self, agent_id: str) -> List[AgentVersion]:
        """Get agent versions"""
        return self._versions.get(agent_id, [])

    async def create_version(self, agent_id: str, changes: str) -> Optional[AgentVersion]:
        """Create new version"""
        agent = self._agents.get(agent_id)
        if not agent:
            return None

        current_version = agent.version
        try:
            major, minor, patch = map(int, current_version.replace("v", "").split("."))
        except (ValueError, AttributeError):
            major, minor, patch = 1, 0, 0

        new_version = f"v{major}.{minor}.{patch + 1}"

        for v in self._versions[agent_id]:
            if v.status == "current":
                v.status = "historical"

        version = AgentVersion(
            version=new_version,
            status="current",
            created_at=datetime.utcnow(),
            changes=changes
        )

        self._versions[agent_id].append(version)
        agent.version = new_version
        agent.updated_at = datetime.utcnow()

        return version

    async def rollback_version(self, agent_id: str, version: str) -> bool:
        """Rollback to specific version"""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        versions = self._versions.get(agent_id, [])
        target = None
        for v in versions:
            if v.version == version:
                target = v
                break

        if not target:
            return False

        for v in versions:
            v.status = "historical" if v.version != version else "current"

        agent.version = version
        agent.updated_at = datetime.utcnow()

        return True
