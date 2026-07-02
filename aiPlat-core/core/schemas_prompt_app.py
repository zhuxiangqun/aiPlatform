from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PromptAppTemplateCreate(BaseModel):
    template_id: str
    name: str
    category: str = ""
    tags: List[str] = Field(default_factory=list)
    system_prompt: str = ""
    user_prompt: str = ""
    assistant_prompt: str = ""
    variables: List[Dict[str, Any]] = Field(default_factory=list)
    examples: str = ""
    constraints: str = ""
    scenario_tags: List[str] = Field(default_factory=list)


class PromptAppTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    assistant_prompt: Optional[str] = None
    variables: Optional[List[Dict[str, Any]]] = None
    examples: Optional[str] = None
    constraints: Optional[str] = None
    scenario_tags: Optional[List[str]] = None
    status: Optional[str] = None


class PromptPreviewRequest(BaseModel):
    variables: Dict[str, Any] = Field(default_factory=dict)
    model: str = ""  # resolved via best_model_for_purpose("default") in handler


class PromptPreviewTextRequest(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    variables: Dict[str, Any] = Field(default_factory=dict)
    model: str = ""  # resolved via best_model_for_purpose("default") in handler


class PromptRunRequest(BaseModel):
    template_id: Optional[str] = None
    instance_id: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)
    model: str = ""  # resolved via best_model_for_purpose("default") in handler


class PromptOptimizeRequest(BaseModel):
    prompt: str = ""
    template_id: Optional[str] = None
    model: str = ""  # resolved via best_model_for_purpose("default") in handler


class PromptTestCaseCreate(BaseModel):
    template_id: str
    name: str = ""
    variables: Dict[str, Any] = Field(default_factory=dict)
    expected_keys: str = ""


class PromptTestCaseUpdate(BaseModel):
    name: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    expected_keys: Optional[str] = None


class PromptEvalRunCreate(BaseModel):
    template_id: str
    version_a: str
    version_b: str
    model: str = ""  # resolved via best_model_for_purpose("default") in handler
    case_ids: List[str] = Field(default_factory=list)


class PromptCategoryCreate(BaseModel):
    name: str
    display_order: int = 0
    icon: str = ""
    parent: str = ""


class PromptAppInstanceCreate(BaseModel):
    source_template_id: str
    name: str = ""


class PromptAppInstanceUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    assistant_prompt: Optional[str] = None
    variables: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None
