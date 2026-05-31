from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.project import Project
from services.test_case_generator import TestCaseGenerator
from database import get_db

router = APIRouter()

@router.post("/{project_id}/testcases")
async def generate_testcases(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = TestCaseGenerator(db)
    test_case_id = await service.generate(project_id)
    return {"test_case_id": test_case_id}