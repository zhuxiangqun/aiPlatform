from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.project import Project
from models.prd import PRD
from services.prd_generator import PRDGenerator
from database import get_db

router = APIRouter()

class PRDResponse(BaseModel):
    prd: object

@router.get("/{project_id}/prd", response_model=PRDResponse)
async def get_prd(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    prd = db.query(PRD).filter(PRD.project_id == project_id).order_by(PRD.version.desc()).first()
    if not prd:
        raise HTTPException(status_code=404, detail="PRD not found")
    return {"prd": {"id": prd.id, "content": prd.content, "version": prd.version, "created_at": prd.created_at}}