from fastapi import APIRouter, HTTPException
from services.audit_logger import AuditLogger
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@router.get("/api/projects/{project_id}/audit")
def get_audit_logs(project_id: str):
    db = SessionLocal()
    try:
        logger = AuditLogger(db)
        logs = logger.get_logs(project_id)
        return {"logs": logs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()