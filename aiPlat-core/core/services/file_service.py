"""
File Service - File Lifecycle Management for Agent Communication

Provides:
- File creation and storage
- Version control
- File diff comparison
- Template support
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

from .context_service import ContextService, SessionContext, FileType, ContextFile


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
        self._session_files: Dict[str, List[str]] = {}
    
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
        
        old_content = file.content if version1 >= file.version else file.content
        new_content = file.content if version2 >= file.version else file.content
        
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