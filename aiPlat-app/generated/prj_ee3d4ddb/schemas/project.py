from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str
    requirements: str

class ProjectResponse(BaseModel):
    id: str
    name: str
    status: str
    requirements: str
    prd: str
    architecture: str
    test_pass_rate: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ProjectRoleInput(BaseModel):
    roles: List[dict]

class ConfirmPRDResponse(BaseModel):
    status: str