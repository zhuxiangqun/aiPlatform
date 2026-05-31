from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.project import Project
from models.code import Code
from services.code_generator import CodeGenerator
from database import get_db

router = APIRouter()

@router.post("/{project_id}/code")
async def generate_code(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = CodeGenerator(db)
    code_id = await service.generate(project_id)
    return {"code_id": code_id}