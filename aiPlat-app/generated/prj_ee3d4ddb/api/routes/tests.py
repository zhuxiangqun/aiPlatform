from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.project import Project
from services.test_executor import TestExecutor
from database import get_db

router = APIRouter()

@router.post("/{project_id}/tests")
async def execute_tests(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    service = TestExecutor(db)
    report_id = await service.execute(project_id)
    return {"test_report_id": report_id}