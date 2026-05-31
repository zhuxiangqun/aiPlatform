from sqlalchemy.orm import Session
from uuid import uuid4
from models.audit_log import AuditLog

class AuditLogger:
    def __init__(self, db: Session):
        self.db = db

    async def log(self, project_id: str, action: str, actor: str, details: str = ""):
        log_entry = AuditLog(
            id=str(uuid4()),
            project_id=project_id,
            action=action,
            actor=actor,
            details=details
        )
        self.db.add(log_entry)
        self.db.commit()