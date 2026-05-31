from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TestCaseResponse(BaseModel):
    id: str
    project_id: str
    description: str
    status: str
    result: str
    executed_at: Optional[datetime] = None

    class Config:
        from_attributes = True