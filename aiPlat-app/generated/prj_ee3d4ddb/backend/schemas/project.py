from pydantic import BaseModel
from typing import List, Optional
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

class RoleItem(BaseModel):
    role_name: str
    user_id: str

class RoleAssignRequest(BaseModel):
    roles: List[RoleItem]

class StatusResponse(BaseModel):
    status: str