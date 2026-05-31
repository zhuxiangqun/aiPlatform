from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.models.test_case import TestCase
from backend.models.bug_record import BugRecord
from backend.schemas.test_case import TestCaseResponse
from backend.database import get_db

router = APIRouter(prefix="/api/projects/{project_id}/tests", tags=["test_results"])

@router.get("", response_model=List[TestCaseResponse])
async def list_test_cases(project_id: str, db: Session = Depends(get_db)):
    test_cases = db.query(TestCase).filter(TestCase.project_id == project_id).all()
    return test_cases

@router.get("/bugs", response_model=List[dict])
async def list_bugs(project_id: str, db: Session = Depends(get_db)):
    bugs = db.query(BugRecord).filter(BugRecord.project_id == project_id).all()
    return bugs