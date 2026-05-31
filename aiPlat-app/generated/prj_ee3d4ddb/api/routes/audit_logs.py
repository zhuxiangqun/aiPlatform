from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
from models.audit_log import AuditLog
from database import get_db

router = APIRouter()

@router.get("/projects/{project_id}/audit-logs", response_model=List[dict])
async def get_audit_logs(project_id: str, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter(AuditLog.project_id == project_id).all()
    return [{"id": str(log.id), "project_id": str(log.project_id), "phase": log.phase, "action": log.action, "actor": log.actor, "timestamp": log.timestamp.isoformat(), "details": log.details} for log in logs]