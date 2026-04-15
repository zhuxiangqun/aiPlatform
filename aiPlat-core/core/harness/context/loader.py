"""
Context Loader

Progressive context loading with directory summarization and trimming.
"""

import os
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
import re

from .types import (
    LoadStrategy,
    Priority,
    FileContext,
    DirectorySummary,
    LoadedContext,
    TrimmedContext,
    TaskSpec,
)


class ContextLoader:
    """Context Loader - Progressive context loading"""

    DEFAULT_EXCLUDES = [
        "__pycache__",
        ".git",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "*.pyc",
        ".DS_Store",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "*.log",
    ]

    DEFAULT_INCLUDE = [
        "*.py",
        "*.js",
        "*.ts",
        "*.jsx",
        "*.tsx",
        "*.md",
        "*.yaml",
        "*.yml",
        "*.json",
        "*.txt",
    ]

    PRIORITY_MAP = {
        ".py": Priority.P1,
        ".js": Priority.P1,
        ".ts": Priority.P1,
        ".jsx": Priority.P1,
        ".tsx": Priority.P1,
        ".json": Priority.P2,
        ".yaml": Priority.P2,
        ".yml": Priority.P2,
        ".md": Priority.P3,
        ".txt": Priority.P4,
    }

    def __init__(
        self,
        root_path: str = ".",
        max_tokens: int = 100000,
        exclude_patterns: List[str] = None,
        include_patterns: List[str] = None,
    ):
        self._root_path = Path(root_path)
        self._max_tokens = max_tokens
        self._exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDES
        self._include_patterns = include_patterns or self.DEFAULT_INCLUDE

    async def load(
        self,
        task: TaskSpec,
        strategy: LoadStrategy = LoadStrategy.ADAPTIVE
    ) -> LoadedContext:
        """Load context based on task and strategy"""
        
        # Determine effective strategy
        if strategy == LoadStrategy.ADAPTIVE:
            strategy = self._adapt_strategy(task)
        
        # Load directory summary
        directory_summary = await self.load_directory(
            str(self._root_path),
            max_depth=2
        )
        
        # Determine files to load
        if strategy == LoadStrategy.LAZY:
            files = await self._load_lazy(task)
        else:
            files = await self._load_eager(task)
        
        # Calculate total tokens
        total_tokens = sum(fc.token_count or self._estimate_tokens(fc.content) for fc in files)
        
        return LoadedContext(
            files=files,
            directory_summary=directory_summary,
            total_tokens=total_tokens,
            strategy=strategy
        )

    def _adapt_strategy(self, task: TaskSpec) -> LoadStrategy:
        """Adapt strategy based on task type"""
        task_type = task.type.lower()
        
        if task_type in ["code_edit", "debug"]:
            return LoadStrategy.LAZY
        elif task_type in ["code_review", "general"]:
            return LoadStrategy.EAGER
        
        return LoadStrategy.ADAPTIVE

    async def load_directory(
        self,
        root: str,
        max_depth: int = 2
    ) -> DirectorySummary:
        """Generate directory structure summary"""
        
        structure_lines = []
        file_count = 0
        total_size = 0
        
        root_path = Path(root)
        
        def walk_tree(path: Path, prefix: str = "", depth: int = 0):
            nonlocal file_count, total_size
            
            if depth > max_depth:
                return
            
            try:
                entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            except PermissionError:
                return
            
            dirs = []
            files = []
            
            for entry in entries:
                if self._should_exclude(entry.name):
                    continue
                
                if entry.is_dir():
                    dirs.append(entry)
                else:
                    if self._should_include(entry.name):
                        files.append(entry)
            
            # Add files at current level
            if files:
                for f in files:
                    file_count += 1
                    try:
                        total_size += f.stat().st_size
                    except:
                        pass
                    
                    indent = "  " * (depth + 1)
                    structure_lines.append(f"{indent}{f.name}")
            
            # Process directories
            for i, d in enumerate(dirs):
                is_last = (i == len(dirs) - 1) and not files
                indent = "  " * depth
                connector = "└── " if is_last else "├── "
                
                structure_lines.append(f"{indent}{connector}{d.name}/")
                new_prefix = indent + ("    " if is_last else "│   ")
                walk_tree(d, new_prefix, depth + 1)
        
        walk_tree(root_path)
        
        structure = "\n".join(structure_lines) or "(empty)"
        
        return DirectorySummary(
            root=root,
            structure=structure,
            file_count=file_count,
            total_size=total_size,
            max_depth=max_depth,
            excludes=self._exclude_patterns
        )

    async def load_file(self, path: str, priority: Priority = Priority.P3) -> FileContext:
        """Load a single file"""
        
        file_path = Path(path)
        
        if not file_path.exists():
            return FileContext(
                path=path,
                content="",
                priority=priority,
                size=0
            )
        
        try:
            content = file_path.read_text(encoding="utf-8")
            size = len(content.encode("utf-8"))
            
            # Determine priority based on file extension
            ext = file_path.suffix
            if ext in self.PRIORITY_MAP:
                priority = self.PRIORITY_MAP[ext]
            
            return FileContext(
                path=path,
                content=content,
                priority=priority,
                size=size,
                token_count=self._estimate_tokens(content)
            )
        except Exception as e:
            return FileContext(
                path=path,
                content=f"Error reading file: {str(e)}",
                priority=priority,
                size=0
            )

    async def _load_lazy(self, task: TaskSpec) -> List[FileContext]:
        """Lazy loading - only current file and immediate dependencies"""
        
        files = []
        
        # Load target file
        if task.target_file:
            fc = await self.load_file(task.target_file, Priority.P0)
            files.append(fc)
            
            # Try to find and load dependencies
            deps = await self._find_dependencies(task.target_file, task.language)
            for dep in deps[:5]:
                fc = await self.load_file(dep, Priority.P1)
                files.append(fc)
        
        return files

    async def _load_eager(self, task: TaskSpec) -> List[FileContext]:
        """Eager loading - load all relevant files"""
        
        files = []
        
        # Find all relevant files
        relevant_files = await self._find_relevant_files(task)
        
        # Load files up to token limit
        total_tokens = 0
        for f in relevant_files:
            if total_tokens >= self._max_tokens:
                break
            
            fc = await self.load_file(f, Priority.P3)
            tokens = fc.token_count or self._estimate_tokens(fc.content)
            
            if total_tokens + tokens <= self._max_tokens:
                files.append(fc)
                total_tokens += tokens
        
        return files

    async def _find_dependencies(self, file_path: str, language: Optional[str]) -> List[str]:
        """Find file dependencies"""
        
        deps = []
        
        try:
            content = Path(file_path).read_text()
        except:
            return deps
        
        if language == "python":
            # Find imports
            import_pattern = r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))'
            for match in re.finditer(import_pattern, content, re.MULTILINE):
                module = match.group(1) or match.group(2)
                # Try to resolve to file path
                if "." in module:
                    parts = module.split(".")
                    for i in range(len(parts)):
                        potential = "/".join(parts[:i+1]) + ".py"
                        if Path(potential).exists():
                            deps.append(potential)
        elif language in ["javascript", "typescript"]:
            # Find imports
            import_pattern = r'(?:import\s+(?:.*?\s+from\s+)?[\'"]([^\'"]+)[\'"])'
            for match in re.finditer(import_pattern, content):
                dep = match.group(1)
                if not dep.startswith("."):
                    dep = f"./{dep}"
                deps.append(dep)
        
        return deps[:10]

    async def _find_relevant_files(self, task: TaskSpec) -> List[str]:
        """Find all relevant files for the task"""
        
        relevant = []
        
        for pattern in self._include_patterns:
            for f in self._root_path.rglob(pattern):
                if not self._should_exclude(f.name):
                    relevant.append(str(f))
        
        return relevant

    def _should_exclude(self, name: str) -> bool:
        """Check if file/directory should be excluded"""
        for pattern in self._exclude_patterns:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern == name:
                return True
        return False

    def _should_include(self, name: str) -> bool:
        """Check if file should be included"""
        for pattern in self._include_patterns:
            if pattern.startswith("*"):
                if name.endswith(pattern[1:]):
                    return True
            elif pattern == name:
                return True
        return False

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)"""
        # Average English word is ~4 characters
        # ~1.3 tokens per word
        words = text.split()
        return int(len(words) * 1.3)


class ContextTrimmer:
    """Context Trimmer - Trim context to fit token limit"""

    def __init__(self, max_tokens: int = 8000):
        self._max_tokens = max_tokens

    def trim(self, context: LoadedContext, max_tokens: int = None) -> TrimmedContext:
        """Trim context to fit within token limit"""
        
        max_tokens = max_tokens or self._max_tokens
        target_tokens = min(max_tokens, context.total_tokens)
        
        if context.total_tokens <= target_tokens:
            return TrimmedContext(
                content=context.to_prompt(),
                original_tokens=context.total_tokens,
                trimmed_tokens=context.total_tokens
            )
        
        # Sort files by priority
        sorted_files = sorted(context.files, key=lambda f: f.priority.value)
        
        kept_files = []
        current_tokens = 0
        removed_files = []
        
        for fc in sorted_files:
            tokens = fc.token_count or self._estimate_tokens(fc.content)
            
            if current_tokens + tokens <= target_tokens:
                kept_files.append(fc)
                current_tokens += tokens
            else:
                removed_files.append(fc.path)
        
        # Rebuild context
        trimmed_context = LoadedContext(
            files=kept_files,
            directory_summary=context.directory_summary,
            total_tokens=current_tokens,
            strategy=context.strategy
        )
        
        return TrimmedContext(
            content=trimmed_context.to_prompt(),
            original_tokens=context.total_tokens,
            trimmed_tokens=current_tokens,
            removed_files=removed_files
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count"""
        words = text.split()
        return int(len(words) * 1.3)


def create_context_loader(
    root_path: str = ".",
    max_tokens: int = 100000
) -> ContextLoader:
    """Create a context loader instance"""
    return ContextLoader(root_path=root_path, max_tokens=max_tokens)


def create_context_trimmer(max_tokens: int = 8000) -> ContextTrimmer:
    """Create a context trimmer instance"""
    return ContextTrimmer(max_tokens=max_tokens)


__all__ = [
    "ContextLoader",
    "ContextTrimmer",
    "create_context_loader",
    "create_context_trimmer",
]