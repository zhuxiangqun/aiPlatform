from fastapi import APIRouter, HTTPException
from services.test_case_generator import TestCaseGenerator
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@router.post("/api/projects/{project_id}/testcases")
def generate_testcases(project_id: str):
    db = SessionLocal()
    try:
        generator = TestCaseGenerator(db)
        test_case_id = generator.generate_test_cases(project_id)
        return {"test_case_id": test_case_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()