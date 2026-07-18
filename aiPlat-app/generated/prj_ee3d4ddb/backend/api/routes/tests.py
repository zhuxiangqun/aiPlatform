from fastapi import APIRouter, HTTPException
from services.test_executor import TestExecutor
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@router.post("/api/projects/{project_id}/tests")
def execute_tests(project_id: str):
    db = SessionLocal()
    try:
        executor = TestExecutor(db)
        report_id = executor.execute_tests(project_id)
        return {"report_id": report_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()