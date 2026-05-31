from sqlalchemy.orm import Session
from models.audit_log import AuditLog
from models.project import Project

class AuditLogger:
    def __init__(self, db: Session):
        self.db = db

    def get_logs(self, project_id: str) -> list:
        logs = self.db.query(AuditLog).filter(AuditLog.project_id == project_id).all()
        return [{"id": log.id, "action": log.action, "actor": log.actor, "timestamp": str(log.timestamp)} for log in logs]