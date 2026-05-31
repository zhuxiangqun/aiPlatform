from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class ProjectCreateInput(BaseModel):
    description: str
    team_members: Dict[str, Any]

class ProjectCreateOutput(BaseModel):
    project_id: str
    status: str

class PRDGenerateInput(BaseModel):
    conversation_history: List[Dict[str, str]]

class PRDGenerateOutput(BaseModel):
    prd_id: str
    content: str
    confirmed: bool

class PRDConfirmInput(BaseModel):
    prd_id: str

class PRDConfirmOutput(BaseModel):
    status: str

class ArchitectureGenerateInput(BaseModel):
    prd_id: str

class ArchitectureGenerateOutput(BaseModel):
    architecture_id: str
    diagram: str
    description: str
    confirmed: bool