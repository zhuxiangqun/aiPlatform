from fastapi import APIRouter, HTTPException
from services.bug_fixer import BugFixer
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@router.post("/api/projects/{project_id}/bugs")
def fix_bugs(project_id: str):
    db = SessionLocal()
    try:
        fixer = BugFixer(db)
        bug_id = fixer.fix_bugs(project_id)
        return {"bug_id": bug_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()