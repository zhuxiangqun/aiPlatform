"""
Skill Manager - Manages Skill instances

Provides CRUD operations for skills and execution management.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


@dataclass
class SkillInfo:
    """Skill information"""
    id: str
    name: str
    type: str  # generation, analysis, transformation, retrieval, execution
    description: str
    status: str  # enabled, disabled, deprecated
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    config: Dict[str, Any]
    dependencies: List[Dict[str, Any]]
    version: str
    created_at: datetime
    updated_at: datetime
    created_by: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillStats:
    """Skill execution statistics"""
    total_calls: int = 0
    success_count: int = 0
    failed_count: int = 0
    avg_duration_ms: float = 0.0
    success_rate: float = 0.0


@dataclass
class SkillExecution:
    """Skill execution record"""
    id: str
    skill_id: str
    status: str  # pending, running, completed, failed
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]]
    error: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: float


@dataclass
class SkillVersion:
    """Skill version"""
    version: str
    status: str  # current, historical
    created_at: datetime
    changes: str


class SkillManager:
    """
    Skill Manager - Manages Skill instances
    
    Provides:
    - Skill CRUD operations
    - Skill version management
    - Skill execution
    - Skill statistics
    """
    
    def __init__(self, seed: bool = True):
        self._skills: Dict[str, SkillInfo] = {}
        self._stats: Dict[str, SkillStats] = {}
        self._executions: Dict[str, List[SkillExecution]] = {}
        self._versions: Dict[str, List[SkillVersion]] = {}
        if seed:
            self._seed_data()
    
    def _seed_data(self):
        now = datetime.utcnow()
        demo_skills = [
            ("text_generation", "文本生成", "generation", "根据提示生成各类文本内容", "enabled"),
            ("code_generation", "代码生成", "generation", "根据需求描述生成代码", "disabled"),
            ("data_analysis", "数据分析", "analysis", "分析数据并提供洞察", "enabled"),
            ("task_planning", "任务规划", "execution", "根据目标拆解为可执行的子任务步骤", "enabled"),
            ("information_search", "信息检索", "retrieval", "从知识库和互联网中检索相关信息", "enabled"),
            ("knowledge_retrieval", "知识召回", "retrieval", "从向量数据库中召回相关文档片段", "enabled"),
            ("summarization", "内容摘要", "transformation", "将长文本压缩为简洁的摘要", "enabled"),
            ("task_decomposition", "任务分解", "analysis", "将复杂任务分解为简单子任务", "enabled"),
            ("api_calling", "API调用", "execution", "调用外部API接口获取数据", "enabled"),
            ("chitchat", "闲聊", "generation", "处理日常闲聊和简单问答", "enabled"),
            ("code_review", "代码审查", "analysis", "审查代码质量并给出改进建议", "enabled"),
            ("translation", "多语言翻译", "transformation", "在多语言之间进行翻译", "enabled"),
        ]
        for skill_id, name, skill_type, desc, status in demo_skills:
            self._skills[skill_id] = SkillInfo(
                id=skill_id, name=name, type=skill_type, description=desc,
                status=status, input_schema={}, output_schema={},
                config={"version": "1.0.0"}, dependencies=[],
                version="1.0.0", created_at=now, updated_at=now, created_by="system"
            )
            self._stats[skill_id] = SkillStats()
            self._executions[skill_id] = []
            self._versions[skill_id] = [SkillVersion(version="1.0.0", status="current", created_at=now, changes="初始版本")]
        self._bound_agents = {}  # skill_id -> [agent_ids]
        
        for skill_id, skill_info in self._skills.items():
            self._bridge_to_registry(skill_info)
    
    async def create_skill(
        self,
        name: str,
        skill_type: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[Dict[str, Any]]] = None,
        created_by: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> SkillInfo:
        """Create a new skill"""
        skill_id = name.lower().replace(" ", "_").replace("-", "_")
        now = datetime.utcnow()
        
        skill = SkillInfo(
            id=skill_id,
            name=name,
            type=skill_type,
            description=description,
            status="enabled",
            input_schema=input_schema,
            output_schema=output_schema,
            config=config or {
                "timeout_seconds": 60,
                "max_concurrent": 10,
                "retry_count": 3
            },
            dependencies=dependencies or [],
            version="v1.0.0",
            created_at=now,
            updated_at=now,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        self._skills[skill_id] = skill
        self._stats[skill_id] = SkillStats()
        self._executions[skill_id] = []
        self._versions[skill_id] = [
            SkillVersion(
                version="v1.0.0",
                status="current",
                created_at=now,
                changes="Initial version"
            )
        ]
        self._bound_agents[skill_id] = []
        
        for skill_id, skill_info in self._skills.items():
            self._bridge_to_registry(skill_info)
        
        self._bridge_to_registry(skill)
        
        return skill
    
    def _bridge_to_registry(self, skill_info: SkillInfo) -> None:
        """Bridge: register skill in execution-layer SkillRegistry."""
        try:
            from core.apps.skills import get_skill_registry, create_skill as create_skill_instance
            from core.apps.skills.base import TextGenerationSkill, CodeGenerationSkill, DataAnalysisSkill
            from core.apps.skills.registry import _GenericSkill
            from core.harness.interfaces import SkillConfig
            
            registry = get_skill_registry()
            skill_id = skill_info.id
            
            _builtin_map = {
                "text_generation": TextGenerationSkill,
                "code_generation": CodeGenerationSkill,
                "data_analysis": DataAnalysisSkill,
            }
            
            skill_cls = _builtin_map.get(skill_id)
            if skill_cls:
                skill_instance = skill_cls()
            else:
                config = SkillConfig(
                    name=skill_id,
                    description=skill_info.description,
                    metadata={"category": skill_info.type, "version": skill_info.version}
                )
                skill_instance = _GenericSkill(config)
            
            registry.register(skill_instance)
            
            if skill_info.status == "disabled":
                registry.disable(skill_id)
        except Exception:
            pass
    
    async def get_skill(self, skill_id: str) -> Optional[SkillInfo]:
        """Get skill by ID"""
        return self._skills.get(skill_id)
    
    async def list_skills(
        self,
        skill_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SkillInfo]:
        """List skills with filters"""
        skills = list(self._skills.values())
        
        if skill_type:
            skills = [s for s in skills if s.type == skill_type]
        if status:
            skills = [s for s in skills if s.status == status]
        
        return skills[offset:offset + limit]
    
    async def update_skill(
        self,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[SkillInfo]:
        """Update skill configuration"""
        skill = self._skills.get(skill_id)
        if not skill:
            return None
        
        if name:
            skill.name = name
        if description:
            skill.description = description
        if input_schema:
            skill.input_schema.update(input_schema)
        if output_schema:
            skill.output_schema.update(output_schema)
        if config:
            skill.config.update(config)
        if metadata:
            skill.metadata.update(metadata)
        
        skill.updated_at = datetime.utcnow()
        
        return skill
    
    async def delete_skill(self, skill_id: str) -> bool:
        """Delete skill"""
        if skill_id not in self._skills:
            return False
        
        del self._skills[skill_id]
        del self._stats[skill_id]
        del self._executions[skill_id]
        del self._versions[skill_id]
        del self._bound_agents[skill_id]
        
        return True
    
    async def enable_skill(self, skill_id: str) -> bool:
        """Enable skill"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        skill.status = "enabled"
        skill.updated_at = datetime.utcnow()
        return True
    
    async def disable_skill(self, skill_id: str) -> bool:
        """Disable skill"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        skill.status = "disabled"
        skill.updated_at = datetime.utcnow()
        return True
    
    async def execute_skill(
        self,
        skill_id: str,
        input_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        mode: str = "inline"
    ) -> SkillExecution:
        """Execute skill via SkillExecutor and record audit trail."""
        import time
        execution_id = f"exec-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow()
        
        execution = SkillExecution(
            id=execution_id,
            skill_id=skill_id,
            status="running",
            input_data=input_data,
            output_data=None,
            error=None,
            start_time=now,
            end_time=None,
            duration_ms=0.0
        )
        
        self._executions[skill_id].append(execution)
        
        stats = self._stats.get(skill_id, SkillStats())
        stats.total_calls += 1
        
        try:
            from core.apps.skills import get_skill_executor, get_skill_registry
            from core.harness.interfaces import SkillContext
            
            executor = get_skill_executor()
            registry = get_skill_registry()
            skill = registry.get(skill_id)
            
            if skill and hasattr(skill, 'set_model'):
                try:
                    from core.adapters.llm import create_adapter
                    model = create_adapter(provider="openai", model="gpt-4o")
                    skill.set_model(model)
                except Exception:
                    pass
            
            skill_tools = context.get("tools", []) if context else []
            skill_context = SkillContext(
                session_id=execution_id,
                user_id=context.get("user_id", "system") if context else "system",
                variables=input_data,
                tools=skill_tools,
            )
            
            timeout = context.get("timeout") if context else None
            
            result = await executor.execute(
                skill_id,
                input_data,
                context=skill_context,
                timeout=timeout,
                mode=mode
            )
            
            duration_ms = (datetime.utcnow() - now).total_seconds() * 1000
            
            if result.success:
                await self.complete_execution(execution_id, result.output or {}, duration_ms)
            else:
                await self.fail_execution(execution_id, result.error or "Unknown error", duration_ms)
            
        except Exception as e:
            duration_ms = (datetime.utcnow() - now).total_seconds() * 1000
            await self.fail_execution(execution_id, str(e), duration_ms)
        
        updated = await self.get_execution(execution_id)
        return updated if updated else execution
    
    async def complete_execution(
        self,
        execution_id: str,
        output_data: Dict[str, Any],
        duration_ms: float
    ) -> bool:
        """Complete execution"""
        for skill_id, executions in self._executions.items():
            for exec_ in executions:
                if exec_.id == execution_id:
                    exec_.status = "completed"
                    exec_.output_data = output_data
                    exec_.end_time = datetime.utcnow()
                    exec_.duration_ms = duration_ms
                    
                    # Update stats
                    stats = self._stats[skill_id]
                    stats.success_count += 1
                    stats.success_rate = stats.success_count / stats.total_calls
                    stats.avg_duration_ms = (
                        (stats.avg_duration_ms * (stats.success_count - 1) + duration_ms)
                        / stats.success_count
                    )
                    
                    return True
        return False
    
    async def fail_execution(
        self,
        execution_id: str,
        error: str,
        duration_ms: float
    ) -> bool:
        """Fail execution"""
        for skill_id, executions in self._executions.items():
            for exec_ in executions:
                if exec_.id == execution_id:
                    exec_.status = "failed"
                    exec_.error = error
                    exec_.end_time = datetime.utcnow()
                    exec_.duration_ms = duration_ms
                    
                    # Update stats
                    stats = self._stats[skill_id]
                    stats.failed_count += 1
                    stats.success_rate = stats.success_count / stats.total_calls
                    
                    return True
        return False
    
    async def get_execution(self, execution_id: str) -> Optional[SkillExecution]:
        """Get execution by ID"""
        for executions in self._executions.values():
            for exec_ in executions:
                if exec_.id == execution_id:
                    return exec_
        return None
    
    async def get_execution_history(
        self,
        skill_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[SkillExecution]:
        """Get execution history for skill"""
        history = self._executions.get(skill_id, [])
        return history[offset:offset + limit]
    
    async def get_stats(self, skill_id: str) -> Optional[SkillStats]:
        """Get skill statistics"""
        return self._stats.get(skill_id)
    
    async def get_versions(self, skill_id: str) -> List[SkillVersion]:
        """Get skill versions"""
        return self._versions.get(skill_id, [])
    
    async def create_version(
        self,
        skill_id: str,
        changes: str
    ) -> Optional[SkillVersion]:
        """Create new version"""
        skill = self._skills.get(skill_id)
        if not skill:
            return None
        
        # Parse current version
        current_version = skill.version
        major, minor, patch = map(int, current_version[1:].split('.'))
        
        # Increment patch version
        new_version = f"v{major}.{minor}.{patch +1}"
        
        # Update current version to historical
        for v in self._versions[skill_id]:
            if v.status == "current":
                v.status = "historical"
        
        # Create new version
        version = SkillVersion(
            version=new_version,
            status="current",
            created_at=datetime.utcnow(),
            changes=changes
        )
        
        self._versions[skill_id].append(version)
        skill.version = new_version
        skill.updated_at = datetime.utcnow()
        
        return version
    
    async def rollback_version(self, skill_id: str, version: str) -> bool:
        """Rollback to specific version"""
        skill = self._skills.get(skill_id)
        if not skill:
            return False
        
        versions = self._versions.get(skill_id, [])
        target_version = None
        for v in versions:
            if v.version == version:
                target_version = v
                break
        
        if not target_version:
            return False
        
        # Update current version
        for v in versions:
            v.status = "historical" if v.version != version else "current"
        
        skill.version = version
        skill.updated_at = datetime.utcnow()
        
        return True
    
    async def get_bound_agents(self, skill_id: str) -> List[str]:
        """Get agents bound to this skill"""
        return self._bound_agents.get(skill_id, [])
    
    def get_skill_count(self) -> Dict[str, int]:
        """Get skill count by status"""
        counts = {"total": len(self._skills), "enabled": 0, "disabled": 0, "deprecated": 0}
        for skill in self._skills.values():
            if skill.status in counts:
                counts[skill.status] += 1
        return counts