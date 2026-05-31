from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from backend.models.audit_log import AuditLog
from backend.database import get_db

router = APIRouter(prefix="/api/projects/{project_id}/audit-logs", tags=["audit_logs"])

@router.get("", response_model=List[dict])
async def list_audit_logs(project_id: str, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter(AuditLog.project_id == project_id).order_by(AuditLog.timestamp.desc()).all()
    return logs