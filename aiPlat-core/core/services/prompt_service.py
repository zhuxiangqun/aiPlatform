"""
Prompt Service - Prompt Template Management

Provides:
- Template registration and storage
- Variable substitution
- Version control
- Template rendering
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import re
import json


@dataclass
class PromptTemplate:
    """
    Prompt template definition.
    
    Attributes:
        id: Unique template ID
        name: Template name
        template: Template content with variables
        variables: List of variable names
        version: Template version
        metadata: Additional metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """
    id: str
    name: str
    template: str
    variables: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def extract_variables(self) -> List[str]:
        """Extract variables from template."""
        pattern = r'\{(\w+)\}'
        return list(set(re.findall(pattern, self.template)))


class PromptService:
    """
    Prompt Service - Manages prompt templates and rendering.
    
    Features:
    - Template registration and retrieval
    - Variable substitution
    - Version management
    - Template validation
    - Caching
    """
    
    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._versions: Dict[str, List[str]] = {}
        self._cache: Dict[str, str] = {}
    
    async def register_template(
        self,
        template_id: str,
        name: str,
        template: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PromptTemplate:
        """
        Register a new prompt template.
        
        Args:
            template_id: Unique template ID
            name: Template name
            template: Template content
            metadata: Additional metadata
            
        Returns:
            Registered PromptTemplate
        """
        variables = self._extract_variables(template)
        
        prompt_template = PromptTemplate(
            id=template_id,
            name=name,
            template=template,
            variables=variables,
            metadata=metadata or {}
        )
        
        self._templates[template_id] = prompt_template
        
        if template_id not in self._versions:
            self._versions[template_id] = []
        self._versions[template_id].append(prompt_template.version)
        
        return prompt_template
    
    async def get_template(self, template_id: str, version: Optional[str] = None) -> Optional[PromptTemplate]:
        """
        Get a prompt template by ID.
        
        Args:
            template_id: Template ID
            version: Specific version (optional)
            
        Returns:
            PromptTemplate or None
        """
        return self._templates.get(template_id)
    
    async def render(
        self,
        template_id: str,
        variables: Dict[str, Any],
        strict: bool = True
    ) -> str:
        """
        Render a prompt template with variables.
        
        Args:
            template_id: Template ID
            variables: Variable values
            strict: Raise error if variable missing
            
        Returns:
            Rendered prompt string
        """
        template = await self.get_template(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")
        
        if strict:
            missing = set(template.variables) - set(variables.keys())
            if missing:
                raise ValueError(f"Missing variables: {missing}")
        
        result = template.template
        for key, value in variables.items():
            result = result.replace(f"{{{key}}}", str(value))
        
        return result
    
    async def update_template(
        self,
        template_id: str,
        template: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        increment_version: bool = True
    ) -> Optional[PromptTemplate]:
        """
        Update an existing template.
        
        Args:
            template_id: Template ID
            template: New template content
            metadata: New metadata
            increment_version: Auto-increment version
            
        Returns:
            Updated PromptTemplate
        """
        existing = await self.get_template(template_id)
        if not existing:
            return None
        
        if template:
            existing.template = template
            existing.variables = self._extract_variables(template)
        
        if metadata:
            existing.metadata.update(metadata)
        
        if increment_version:
            parts = existing.version.split('.')
            parts[-1] = str(int(parts[-1]) + 1)
            existing.version = '.'.join(parts)
        
        existing.updated_at = datetime.utcnow()
        
        self._templates[template_id] = existing
        self._versions[template_id].append(existing.version)
        
        if template_id in self._cache:
            del self._cache[template_id]
        
        return existing
    
    async def delete_template(self, template_id: str) -> bool:
        """
        Delete a template.
        
        Args:
            template_id: Template ID
            
        Returns:
            True if deleted
        """
        if template_id in self._templates:
            del self._templates[template_id]
            if template_id in self._versions:
                del self._versions[template_id]
            if template_id in self._cache:
                del self._cache[template_id]
            return True
        return False
    
    async def list_templates(self) -> List[PromptTemplate]:
        """
        List all templates.
        
        Returns:
            List of PromptTemplate
        """
        return list(self._templates.values())
    
    async def get_versions(self, template_id: str) -> List[str]:
        """
        Get all versions of a template.
        
        Args:
            template_id: Template ID
            
        Returns:
            List of version strings
        """
        return self._versions.get(template_id, [])
    
    def _extract_variables(self, template: str) -> List[str]:
        """Extract variables from template."""
        pattern = r'\{(\w+)\}'
        return list(set(re.findall(pattern, template)))
    
    async def optimize_format_locked(
        self,
        template: str,
        preferred_format: str = "json"
    ) -> str:
        """
        Optimize template with locked format.
        
        Args:
            template: Original template
            preferred_format: Preferred output format
            
        Returns:
            Optimized template
        """
        if preferred_format == "json":
            return f"Output in JSON format:\n{template}"
        elif preferred_format == "markdown":
            return f"Output in Markdown format:\n{template}"
        return template
    
    async def optimize_format_progressive(
        self,
        template: str
    ) -> str:
        """
        Optimize template with progressive format.
        
        Args:
            template: Original template
            
        Returns:
            Progressive template
        """
        return f"First, provide a brief summary. Then, expand with detailed analysis.\n\n{template}"
    
    async def optimize_format_feedback(
        self,
        template: str
    ) -> str:
        """
        Optimize template with feedback-based format.
        
        Args:
            template: Original template
            
        Returns:
            Template with feedback mechanism
        """
        return f"Answer the following. If the format needs adjustment, suggest improvements:\n\n{template}"
    
    async def apply_format_template(
        self,
        template: str,
        template_type: str = "standard"
    ) -> str:
        """
        Apply standardized format template.
        
        Args:
            template: Original template
            template_type: Type of format template
            
        Returns:
            Template with format structure applied
        """
        if template_type == "standard":
            return f"""Task: {template}

Please provide output in the following format:
1. Summary: [brief overview]
2. Details: [detailed explanation]
3. Recommendations: [action items]
"""
        elif template_type == "technical":
            return f"""Task: {template}

Please provide technical output with:
- Overview
- Implementation details
- Examples
- Best practices
"""
        return template