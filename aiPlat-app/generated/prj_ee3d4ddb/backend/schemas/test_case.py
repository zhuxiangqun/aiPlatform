from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class TestCaseResponse(BaseModel):
    id: str
    project_id: str
    description: str
    status: str
    result: str
    executed_at: Optional[datetime] = None