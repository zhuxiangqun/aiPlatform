from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from uuid import uuid4
from models.project import Project
from models.architecture import Architecture
from services.architecture_designer import ArchitectureDesigner
from database import get_db

router = APIRouter()

class ArchitectureOutput(BaseModel):
    architecture_id: str

@router.post("/{project_id}/architecture", response_model=ArchitectureOutput)
async def generate_architecture(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = ArchitectureDesigner(db)
    arch_id = await service.generate(project_id)
    return {"architecture_id": arch_id}