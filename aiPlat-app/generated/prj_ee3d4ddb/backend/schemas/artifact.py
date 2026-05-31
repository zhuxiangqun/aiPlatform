from pydantic import BaseModel
from datetime import datetime

class ArtifactResponse(BaseModel):
    id: str
    project_id: str
    type: str
    content: str
    version: int
    created_by: str
    created_at: datetime