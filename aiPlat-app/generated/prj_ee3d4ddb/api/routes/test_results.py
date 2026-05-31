from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.test_case import TestCase
from schemas.test_case import TestCaseResponse
from database import get_db

router = APIRouter()

@router.get("/projects/{project_id}/test-results", response_model=List[TestCaseResponse])
async def get_test_results(project_id: str, db: Session = Depends(get_db)):
    test_cases = db.query(TestCase).filter(TestCase.project_id == project_id).all()
    return [TestCaseResponse.from_orm(tc) for tc in test_cases]