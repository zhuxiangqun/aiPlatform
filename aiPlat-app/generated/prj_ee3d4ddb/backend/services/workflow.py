from sqlalchemy.orm import Session
from typing import List
from backend.models.project import Project
from backend.models.project_role import ProjectRole
from backend.models.artifact import Artifact
from backend.models.audit_log import AuditLog
from backend.services.agent_manager import AgentManager
from datetime import datetime

class WorkflowEngine:
    def __init__(self, db: Session):
        self.db = db
        self.agent_manager = AgentManager(db)

    def assign_roles(self, project_id: str, roles: List[dict]) -> str:
        for role in roles:
            project_role = ProjectRole(
                project_id=project_id,
                role_name=role["role_name"],
                user_id=role["user_id"]
            )
            self.db.add(project_role)
        self._log_action(project_id, "role_assignment", "roles_assigned", "system")
        self.db.commit()
        return "roles_assigned"

    def confirm_prd(self, project_id: str) -> str:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            return "project_not_found"
        project.status = "prd_confirmed"
        self._log_action(project_id, "prd_confirmation", "prd_confirmed", "system")
        self.db.commit()
        return "prd_confirmed"

    def _log_action(self, project_id: str, phase: str, action: str, actor: str):
        log = AuditLog(
            project_id=project_id,
            phase=phase,
            action=action,
            actor=actor,
            details=f"{action} performed in phase {phase}"
        )
        self.db.add(log)