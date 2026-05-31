from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from uuid import uuid4
from models.project import Project
from models.prd import PRD
from services.conversation_service import ConversationService
from database import get_db

router = APIRouter()

class ConversationInput(BaseModel):
    message: str

class ConversationOutput(BaseModel):
    response: str
    prd_id: str = ""

@router.post("/{project_id}/conversation", response_model=ConversationOutput)
async def conversation(project_id: str, data: ConversationInput, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = ConversationService(db)
    result = await service.process_message(project_id, data.message)
    return result