from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ArtifactResponse(BaseModel):
    id: str
    project_id: str
    type: str
    content: str
    version: int
    created_by: str
    created_at: datetime

    class Config:
        from_attributes = True