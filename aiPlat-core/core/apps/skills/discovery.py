"""
Skill Discovery Module

Provides automatic skill discovery by scanning directories and parsing SKILL.md metadata.
"""

import importlib.util
import importlib.abc
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import yaml
import re


@dataclass
class DiscoveredSkill:
    """Discovered skill metadata"""
    name: str
    display_name: str
    description: str
    version: str = "1.0.0"
    category: str = "general"
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    trigger_conditions: List[str] = field(default_factory=list)  # Skill 触发条件（路由表）
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[Dict[str, str]] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    handler_path: Optional[str] = None
    references_path: Optional[str] = None
    scripts_path: Optional[str] = None
    # New fields for OpenClaw compatibility
    trigger_keywords: List[str] = field(default_factory=list)
    execution_mode: str = "inline"
    author: str = ""


class SKILLMD_parser:
    """Parser for SKILL.md format"""
    
    FRONT_MATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    YAML_BLOCK_PATTERN = re.compile(r'```yaml\s*\n(.*?)```', re.DOTALL)
    
    @staticmethod
    def parse(skill_dir: Path) -> Optional[DiscoveredSkill]:
        """Parse SKILL.md file in skill directory"""
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        
        content = skill_md.read_text(encoding='utf-8')
        
        # Extract YAML from front matter or code block
        yaml_content = None
        
        # Try front matter format (--- ... ---)
        if content.startswith('---'):
            lines = content.split('\n')
            yaml_lines = []
            in_front_matter = False
            for i, line in enumerate(lines):
                if line.strip() == '---':
                    if not in_front_matter:
                        in_front_matter = True
                        continue
                    else:
                        break
                if in_front_matter:
                    yaml_lines.append(line)
            yaml_content = '\n'.join(yaml_lines)
        
        if not yaml_content:
            # Try yaml code block format (```yaml ... ```)
            match = SKILLMD_parser.YAML_BLOCK_PATTERN.search(content)
            if match:
                yaml_content = match.group(1)
        
        if not yaml_content:
            # Try to find any YAML-like content
            lines = content.split('\n')
            yaml_lines = []
            in_yaml = False
            for line in lines:
                if line.strip().startswith('name:'):
                    in_yaml = True
                if in_yaml:
                    yaml_lines.append(line)
                    if line.strip() == '```' or (line.strip() and not line.startswith(' ') and not line.startswith('\t')) and len(yaml_lines) > 2:
                        break
            yaml_content = '\n'.join(yaml_lines)
        
        if not yaml_content:
            return None
        
        try:
            data = yaml.safe_load(yaml_content)
            if not data:
                return None
            
            return DiscoveredSkill(
                name=data.get('name', skill_dir.name),
                display_name=data.get('display_name', data.get('name', skill_dir.name)),
                description=data.get('description', ''),
                version=data.get('version', '1.0.0'),
                category=data.get('category', 'general'),
                tags=data.get('tags', []),
                capabilities=data.get('capabilities', []),
                trigger_conditions=data.get('trigger_conditions', []),  # Skill 触发条件（路由表）
                input_schema=data.get('input_schema', {}),
                output_schema=data.get('output_schema', {}),
                examples=data.get('examples', []),
                requirements=data.get('requirements', []),
                permissions=data.get('permissions', []),
                trigger_keywords=data.get('trigger_keywords', []),
                execution_mode=data.get('execution_mode', 'inline'),
                author=data.get('author', ''),
            )
        except yaml.YAMLError:
            return None


class SkillDiscovery:
    """
    Automatic skill discovery system.
    
    Scans directories to find and load skills with SKILL.md metadata.
    """
    
    def __init__(self, base_path: str):
        """
        Initialize discovery system.
        
        Args:
            base_path: Base directory to scan for skills
        """
        self.base_path = Path(base_path)
        self._parser = SKILLMD_parser()
        self._discovered: Dict[str, DiscoveredSkill] = {}
    
    async def discover(self) -> Dict[str, DiscoveredSkill]:
        """
        Scan directory and discover all skills.
        
        Returns:
            Dict mapping skill name to discovered metadata
        """
        if not self.base_path.exists():
            return {}
        
        self._discovered = {}
        
        for item in self.base_path.iterdir():
            if not item.is_dir():
                continue
            
            # Skip hidden directories and special folders
            if item.name.startswith('.') or item.name in ['__pycache__', 'scripts', 'references']:
                continue
            
            skill_info = self._parser.parse(item)
            if skill_info:
                skill_info.handler_path = str(item / "handler.py")
                skill_info.references_path = str(item / "references")
                skill_info.scripts_path = str(item / "scripts")
                self._discovered[skill_info.name] = skill_info
        
        return self._discovered
    
    def get(self, name: str) -> Optional[DiscoveredSkill]:
        """Get discovered skill by name"""
        return self._discovered.get(name)
    
    def list_by_category(self, category: str) -> List[DiscoveredSkill]:
        """List skills by category"""
        return [s for s in self._discovered.values() if s.category == category]
    
    def load_handler(self, skill_info: DiscoveredSkill):
        """Load skill handler module"""
        if not skill_info.handler_path:
            return None
        
        handler_path = Path(skill_info.handler_path)
        if not handler_path.exists():
            return None
        
        spec = importlib.util.spec_from_file_location(
            f"skill_{skill_info.name}",
            str(handler_path)
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        
        return None


class SkillLoader:
    """
    Skill loader with caching and on-demand loading.
    
    Supports references/ and scripts/ directories.
    """
    
    def __init__(self, discovery: SkillDiscovery):
        self._discovery = discovery
        self._handlers: Dict[str, Any] = {}
        self._references: Dict[str, Dict[str, Any]] = {}
        self._scripts: Dict[str, Dict[str, str]] = {}
    
    def load_handler(self, skill_name: str):
        """Load and cache skill handler"""
        if skill_name in self._handlers:
            return self._handlers[skill_name]
        
        skill_info = self._discovery.get(skill_name)
        if not skill_info:
            return None
        
        handler = self._discovery.load_handler(skill_info)
        if handler:
            self._handlers[skill_name] = handler
        
        return handler
    
    def load_reference(self, skill_name: str, ref_name: str) -> Optional[str]:
        """Load reference document on-demand"""
        key = f"{skill_name}:{ref_name}"
        
        if key in self._references:
            return self._references[key]
        
        skill_info = self._discovery.get(skill_name)
        if not skill_info or not skill_info.references_path:
            return None
        
        ref_path = Path(skill_info.references_path) / ref_name
        if not ref_path.exists():
            return None
        
        try:
            content = ref_path.read_text(encoding='utf-8')
            self._references[key] = content
            return content
        except Exception:
            return None
    
    def list_references(self, skill_name: str) -> List[str]:
        """List available references for a skill"""
        skill_info = self._discovery.get(skill_name)
        if not skill_info or not skill_info.references_path:
            return []
        
        ref_dir = Path(skill_info.references_path)
        if not ref_dir.exists():
            return []
        
        return [f.name for f in ref_dir.iterdir() if f.is_file()]
    
    def load_script(self, skill_name: str, script_name: str) -> Optional[str]:
        """Load deterministic script"""
        key = f"{skill_name}:{script_name}"
        
        if key in self._scripts:
            return self._scripts[key]
        
        skill_info = self._discovery.get(skill_name)
        if not skill_info or not skill_info.scripts_path:
            return None
        
        script_path = Path(skill_info.scripts_path) / script_name
        if not script_path.exists():
            return None
        
        try:
            content = script_path.read_text(encoding='utf-8')
            self._scripts[key] = content
            return content
        except Exception:
            return None
    
    def list_scripts(self, skill_name: str) -> List[str]:
        """List available scripts for a skill"""
        skill_info = self._discovery.get(skill_name)
        if not skill_info or not skill_info.scripts_path:
            return []
        
        scripts_dir = Path(skill_info.scripts_path)
        if not scripts_dir.exists():
            return []
        
        return [f.name for f in scripts_dir.iterdir() if f.is_file()]


class SkillMatcher:
    """根据用户输入匹配 Skill"""
    
    def match(self, user_input: str, skills: List[DiscoveredSkill]) -> List[DiscoveredSkill]:
        """匹配相关 Skill"""
        if not user_input or not skills:
            return []
        
        results = []
        input_lower = user_input.lower()
        
        for skill in skills:
            if not skill.trigger_keywords:
                continue
            
            for keyword in skill.trigger_keywords:
                if keyword.lower() in input_lower:
                    results.append(skill)
                    break
        
        return results
    
    def match_by_category(self, category: str, skills: List[DiscoveredSkill]) -> List[DiscoveredSkill]:
        """按 Category 筛选"""
        return [s for s in skills if s.category == category]
    
    def get_suggestions(self, user_input: str, skills: List[DiscoveredSkill], limit: int = 5) -> List[DiscoveredSkill]:
        """获取推荐 Skill"""
        matched = self.match(user_input, skills)
        return matched[:limit]


def create_discovery(base_path: str) -> SkillDiscovery:
    """Factory function to create skill discovery"""
    return SkillDiscovery(base_path)


def create_loader(discovery: SkillDiscovery) -> SkillLoader:
    """Factory function to create skill loader"""
    return SkillLoader(discovery)