"""
Context Service - Session Context and State Management

Provides:
- Session context management
- State persistence
- Context sharing across components
- Context lifecycle management
- Context query and retrieval
- File-based communication support
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid


class ContextState(Enum):
    """Context state enumeration."""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    CLOSED = "closed"


class FileType(Enum):
    """File types for Agent communication."""
    SPEC = "spec"                  # 需求规格说明
    SPRINT_REPORT = "sprint_report"  # 冲刺报告
    FEEDBACK = "feedback"          # 反馈记录
    HANDOFF = "handoff"            # 交接文档
    REVIEW = "review"              # 评审记录


@dataclass
class ContextFile:
    """File in context for communication."""
    file_id: str
    file_type: FileType
    name: str
    content: str
    version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_content(self, new_content: str) -> None:
        """Update file content and increment version."""
        self.content = new_content
        self.version += 1
        self.updated_at = datetime.utcnow()


@dataclass
class SessionContext:
    """
    Session Context - Holds session state and metadata.
    
    Attributes:
        session_id: Unique session ID
        user_id: User ID (optional)
        agent_id: Agent ID (optional)
        state: Context state
        data: Context data
        metadata: Context metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
        expires_at: Expiration timestamp (optional)
        parent_context_id: Parent context ID (optional)
    """
    session_id: str
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    state: ContextState = ContextState.ACTIVE
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    parent_context_id: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if context is expired."""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def touch(self):
        """Update the last modified time."""
        self.updated_at = datetime.utcnow()


class ContextService:
    """
    Context Service - Session context and state management.
    
    Features:
    - Context creation and retrieval
    - State persistence
    - Context sharing
    - Lifecycle management
    - Context query
    """
    
    def __init__(self, default_ttl: int = 3600):
        """
        Initialize ContextService.
        
        Args:
            default_ttl: Default time-to-live in seconds (default: 3600)
        """
        self._contexts: Dict[str, SessionContext] = {}
        self._user_contexts: Dict[str, List[str]] = {}
        self._agent_contexts: Dict[str, List[str]] = {}
        self._default_ttl = default_ttl
    
    async def create_context(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
        parent_context_id: Optional[str] = None
    ) -> SessionContext:
        """
        Create a new session context.
        
        Args:
            user_id: User ID (optional)
            agent_id: Agent ID (optional)
            data: Initial context data
            metadata: Initial metadata
            ttl: Time-to-live in seconds (uses default if not specified)
            parent_context_id: Parent context ID (optional)
            
        Returns:
            Created SessionContext
        """
        session_id = str(uuid.uuid4())
        
        effective_ttl = ttl or self._default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=effective_ttl) if effective_ttl > 0 else None
        
        context = SessionContext(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            data=data or {},
            metadata=metadata or {},
            expires_at=expires_at,
            parent_context_id=parent_context_id
        )
        
        self._contexts[session_id] = context
        
        if user_id:
            if user_id not in self._user_contexts:
                self._user_contexts[user_id] = []
            self._user_contexts[user_id].append(session_id)
        
        if agent_id:
            if agent_id not in self._agent_contexts:
                self._agent_contexts[agent_id] = []
            self._agent_contexts[agent_id].append(session_id)
        
        return context
    
    async def get_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Get a context by session ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            SessionContext or None
        """
        context = self._contexts.get(session_id)
        
        if context and context.is_expired():
            context.state = ContextState.EXPIRED
            return None
        
        return context
    
    async def update_context(
        self,
        session_id: str,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        merge: bool = True
    ) -> Optional[SessionContext]:
        """
        Update a context.
        
        Args:
            session_id: Session ID
            data: New data (merged with existing if merge=True)
            metadata: New metadata (merged with existing if merge=True)
            merge: Merge with existing data/metadata
            
        Returns:
            Updated SessionContext
        """
        context = await self.get_context(session_id)
        if not context:
            return None
        
        if data:
            if merge:
                context.data.update(data)
            else:
                context.data = data
        
        if metadata:
            if merge:
                context.metadata.update(metadata)
            else:
                context.metadata = metadata
        
        context.touch()
        
        return context
    
    async def set_context_value(
        self,
        session_id: str,
        key: str,
        value: Any
    ) -> Optional[SessionContext]:
        """
        Set a value in context data.
        
        Args:
            session_id: Session ID
            key: Key
            value: Value
            
        Returns:
            Updated SessionContext
        """
        context = await self.get_context(session_id)
        if not context:
            return None
        
        context.data[key] = value
        context.touch()
        
        return context
    
    async def get_context_value(
        self,
        session_id: str,
        key: str,
        default: Any = None
    ) -> Any:
        """
        Get a value from context data.
        
        Args:
            session_id: Session ID
            key: Key
            default: Default value if key not found
            
        Returns:
            Value or default
        """
        context = await self.get_context(session_id)
        if not context:
            return default
        
        return context.data.get(key, default)
    
    async def delete_context(self, session_id: str) -> bool:
        """
        Delete a context.
        
        Args:
            session_id: Session ID
            
        Returns:
            True if deleted
        """
        context = self._contexts.get(session_id)
        if not context:
            return False
        
        del self._contexts[session_id]
        
        if context.user_id and context.user_id in self._user_contexts:
            self._user_contexts[context.user_id] = [
                sid for sid in self._user_contexts[context.user_id] if sid != session_id
            ]
        
        if context.agent_id and context.agent_id in self._agent_contexts:
            self._agent_contexts[context.agent_id] = [
                sid for sid in self._agent_contexts[context.agent_id] if sid != session_id
            ]
        
        return True
    
    async def list_user_contexts(self, user_id: str) -> List[SessionContext]:
        """
        List all contexts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of SessionContext
        """
        session_ids = self._user_contexts.get(user_id, [])
        contexts = []
        for sid in session_ids:
            context = await self.get_context(sid)
            if context:
                contexts.append(context)
        return contexts
    
    async def list_agent_contexts(self, agent_id: str) -> List[SessionContext]:
        """
        List all contexts for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List of SessionContext
        """
        session_ids = self._agent_contexts.get(agent_id, [])
        contexts = []
        for sid in session_ids:
            context = await self.get_context(sid)
            if context:
                contexts.append(context)
        return contexts
    
    async def close_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Close a context (set state to CLOSED).
        
        Args:
            session_id: Session ID
            
        Returns:
            Closed SessionContext
        """
        context = await self.get_context(session_id)
        if not context:
            return None
        
        context.state = ContextState.CLOSED
        context.touch()
        
        return context
    
    async def expire_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Expire a context.
        
        Args:
            session_id: Session ID
            
        Returns:
            Expired SessionContext
        """
        context = await self.get_context(session_id)
        if not context:
            return None
        
        context.state = ContextState.EXPIRED
        context.expires_at = datetime.utcnow()
        context.touch()
        
        return context
    
    async def extend_context_ttl(
        self,
        session_id: str,
        additional_seconds: int = 3600
    ) -> Optional[SessionContext]:
        """
        Extend context TTL.
        
        Args:
            session_id: Session ID
            additional_seconds: Additional seconds to extend
            
        Returns:
            Updated SessionContext
        """
        context = await self.get_context(session_id)
        if not context:
            return None
        
        if context.expires_at:
            context.expires_at = context.expires_at + timedelta(seconds=additional_seconds)
        else:
            context.expires_at = datetime.utcnow() + timedelta(seconds=additional_seconds)
        
        context.touch()
        
        return context
    
    async def export_context(self, session_id: str) -> str:
        """
        Export context to JSON string.
        
        Args:
            session_id: Session ID
            
        Returns:
            JSON string
        """
        context = await self.get_context(session_id)
        if not context:
            return "{}"
        
        data = {
            "session_id": context.session_id,
            "user_id": context.user_id,
            "agent_id": context.agent_id,
            "state": context.state.value,
            "data": context.data,
            "metadata": context.metadata,
            "created_at": context.created_at.isoformat(),
            "updated_at": context.updated_at.isoformat(),
            "expires_at": context.expires_at.isoformat() if context.expires_at else None,
            "parent_context_id": context.parent_context_id
        }
        
        return json.dumps(data, indent=2)
    
    async def import_context(self, json_data: str) -> SessionContext:
        """
        Import context from JSON string.
        
        Args:
            json_data: JSON string
            
        Returns:
            Imported SessionContext
        """
        data = json.loads(json_data)
        
        context = SessionContext(
            session_id=data["session_id"],
            user_id=data.get("user_id"),
            agent_id=data.get("agent_id"),
            state=ContextState(data.get("state", "active")),
            data=data.get("data", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow(),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            parent_context_id=data.get("parent_context_id")
        )
        
        self._contexts[context.session_id] = context
        
        if context.user_id:
            if context.user_id not in self._user_contexts:
                self._user_contexts[context.user_id] = []
            self._user_contexts[context.user_id].append(context.session_id)
        
        if context.agent_id:
            if context.agent_id not in self._agent_contexts:
                self._agent_contexts[context.agent_id] = []
            self._agent_contexts[context.agent_id].append(context.session_id)
        
        return context
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get context statistics.
        
        Returns:
            Context statistics
        """
        total_contexts = len(self._contexts)
        active_contexts = sum(1 for c in self._contexts.values() if c.state == ContextState.ACTIVE)
        idle_contexts = sum(1 for c in self._contexts.values() if c.state == ContextState.IDLE)
        expired_contexts = sum(1 for c in self._contexts.values() if c.state == ContextState.EXPIRED)
        closed_contexts = sum(1 for c in self._contexts.values() if c.state == ContextState.CLOSED)
        
        total_files = sum(len(getattr(c, '_files', {})) for c in self._contexts.values())
        
        return {
            "total_contexts": total_contexts,
            "active_contexts": active_contexts,
            "idle_contexts": idle_contexts,
            "expired_contexts": expired_contexts,
            "closed_contexts": closed_contexts,
            "total_users": len(self._user_contexts),
            "total_agents": len(self._agent_contexts),
            "total_files": total_files
        }


class FileService:
    """
    File Service - Manages file lifecycle for Agent communication.
    
    Provides:
    - File creation and storage
    - Version control
    - File diff comparison
    - Template support
    """
    
    def __init__(self, context_service: Optional[ContextService] = None):
        self._context_service = context_service or ContextService()
        self._files: Dict[str, ContextFile] = {}
        self._session_files: Dict[str, List[str]] = {}  # session_id -> [file_ids]
    
    def _init_context_files(self, context: SessionContext) -> None:
        """Initialize files storage for context if not exists."""
        if not hasattr(context, '_files'):
            context._files = {}
    
    async def create_file(
        self,
        session_id: str,
        file_type: FileType,
        name: str,
        content: str,
        created_by: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ContextFile]:
        """Create a new file in context."""
        context = await self._context_service.get_context(session_id)
        if not context:
            return None
        
        self._init_context_files(context)
        
        file_id = str(uuid.uuid4())
        file = ContextFile(
            file_id=file_id,
            file_type=file_type,
            name=name,
            content=content,
            created_by=created_by,
            metadata=metadata or {}
        )
        
        context._files[file_id] = file
        
        if session_id not in self._session_files:
            self._session_files[session_id] = []
        self._session_files[session_id].append(file_id)
        
        return file
    
    async def get_file(self, session_id: str, file_id: str) -> Optional[ContextFile]:
        """Get a file by ID."""
        context = await self._context_service.get_context(session_id)
        if not context:
            return None
        
        self._init_context_files(context)
        return context._files.get(file_id)
    
    async def update_file(
        self,
        session_id: str,
        file_id: str,
        new_content: str
    ) -> Optional[ContextFile]:
        """Update file content."""
        context = await self._context_service.get_context(session_id)
        if not context:
            return None
        
        self._init_context_files(context)
        
        file = context._files.get(file_id)
        if not file:
            return None
        
        file.update_content(new_content)
        return file
    
    async def delete_file(self, session_id: str, file_id: str) -> bool:
        """Delete a file."""
        context = await self._context_service.get_context(session_id)
        if not context:
            return False
        
        self._init_context_files(context)
        
        if file_id in context._files:
            del context._files[file_id]
            
            if session_id in self._session_files:
                self._session_files[session_id] = [
                    fid for fid in self._session_files[session_id] if fid != file_id
                ]
            return True
        
        return False
    
    async def list_files(
        self,
        session_id: str,
        file_type: Optional[FileType] = None
    ) -> List[ContextFile]:
        """List files in context."""
        context = await self._context_service.get_context(session_id)
        if not context:
            return []
        
        self._init_context_files(context)
        
        files = list(context._files.values())
        
        if file_type:
            files = [f for f in files if f.file_type == file_type]
        
        return files
    
    async def get_file_history(self, session_id: str, file_id: str) -> List[Dict[str, Any]]:
        """Get file version history."""
        file = await self.get_file(session_id, file_id)
        if not file:
            return []
        
        return [
            {
                "version": file.version,
                "content": file.content,
                "updated_at": file.updated_at.isoformat()
            }
        ]
    
    async def diff(
        self,
        session_id: str,
        file_id: str,
        version1: int,
        version2: int
    ) -> Optional[Dict[str, Any]]:
        """Compare two versions of a file."""
        file = await self.get_file(session_id, file_id)
        if not file:
            return None
        
        if version1 == file.version:
            old_content = file.content
        elif version1 < file.version:
            old_content = file.content
        else:
            return None
        
        if version2 == file.version:
            new_content = file.content
        else:
            new_content = file.content
        
        return {
            "file_id": file_id,
            "file_name": file.name,
            "version1": version1,
            "version2": version2,
            "old_content": old_content,
            "new_content": new_content,
            "diff": self._generate_simple_diff(old_content, new_content)
        }
    
    def _generate_simple_diff(self, old: str, new: str) -> Dict[str, Any]:
        """Generate simple diff between two content strings."""
        old_lines = old.split('\n')
        new_lines = new.split('\n')
        
        return {
            "added": len([l for l in new_lines if l not in old_lines]),
            "removed": len([l for l in old_lines if l not in new_lines]),
            "unchanged": len([l for l in old_lines if l in new_lines])
        }
    
    @staticmethod
    def get_file_template(file_type: FileType) -> str:
        """Get template for a file type."""
        templates = {
            FileType.SPEC: """# 需求规格说明

## 功能需求
- 

## 性能指标
- 

## 边界条件
- 

## 验收标准
- [ ] 
""",
            FileType.SPRINT_REPORT: """# 冲刺报告

## 完成情况
- [ ] 

## 问题
- 

## 待办
- [ ] 

## 下一步
- 
""",
            FileType.FEEDBACK: """# 反馈记录

## 问题描述
- 

## 影响范围
- 

## 修复建议
- 

## 优先级
- 
""",
            FileType.HANDOFF: """# 交接文档

## 当前状态
- 

## 后续任务
- [ ] 

## 注意事项
- 

## 联系信息
- 
""",
            FileType.REVIEW: """# 评审记录

## 评审意见
- 

## 修改要求
- 

## 通过状态
- [ ] 通过
- [ ] 需要修改

## 评审人
- 
"""
        }
        return templates.get(file_type, "")