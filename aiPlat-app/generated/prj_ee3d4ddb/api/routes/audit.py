from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.project import Project
from models.audit_log import AuditLog
from database import get_db

router = APIRouter()

@router.get("/{project_id}/audit")
async def get_audit_logs(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    logs = db.query(AuditLog).filter(AuditLog.project_id == project_id).all()
    return logs