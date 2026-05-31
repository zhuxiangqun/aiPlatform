from sqlalchemy.orm import Session
from models.project import Project
from models.audit_log import AuditLog
from datetime import datetime, timezone

class WorkflowEngine:
    def __init__(self, db: Session):
        self.db = db

    def confirm_prd(self, project_id: str) -> str:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return "project not found"
        project.status = "prd_confirmed"
        project.updated_at = datetime.now(timezone.utc)
        log = AuditLog(project_id=project_id, phase="prd", action="confirm_prd", actor="system", details="PRD confirmed by user")
        self.db.add(log)
        self.db.commit()
        return "prd_confirmed"