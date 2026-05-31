from typing import Dict, Any, List
from app.services.llm_service import LLMService
from app.models import Project, PRD, Architecture, Code, TestSuite, TestReport, BugRecord, AuditLog
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import json

class AgentEngine:
    def __init__(self, llm_service: LLMService):
        self.llm = llm_service

    def create_project(self, db: Session, description: str, team_members: Dict[str, Any]) -> Project:
        project = Project(
            status="created",
            current_phase="prd_generation"
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # Log audit
        audit = AuditLog(
            project_id=project.id,
            phase="project_creation",
            start_time=datetime.now(timezone.utc),
            executor="system",
            artifact_version="1.0"
        )
        db.add(audit)
        db.commit()
        return project

    def generate_prd(self, db: Session, project_id: str, conversation_history: List[Dict[str, Any]]) -> PRD:
        content = self.llm.generate_prd(conversation_history)
        prd = PRD(
            project_id=project_id,
            content=content,
            confirmed=False
        )
        db.add(prd)
        db.commit()
        db.refresh(prd)

        # Update project phase
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.current_phase = "prd_review"

        # Log audit
        audit = AuditLog(
            project_id=project_id,
            phase="prd_generation",
            start_time=datetime.now(timezone.utc),
            executor="ProductManagerAgent",
            artifact_version="1.0"
        )
        db.add(audit)
        db.commit()
        return prd

    def confirm_prd(self, db: Session, prd_id: str) -> str:
        prd = db.query(PRD).filter(PRD.id == prd_id).first()
        if not prd:
            return "prd_not_found"
        prd.confirmed = True

        # Update project phase
        project = db.query(Project).filter(Project.id == prd.project_id).first()
        if project:
            project.current_phase = "architecture_design"

        # Log audit
        audit = AuditLog(
            project_id=prd.project_id,
            phase="prd_confirmation",
            start_time=datetime.now(timezone.utc),
            executor="ProductManagerAgent",
            artifact_version="1.0"
        )
        db.add(audit)
        db.commit()
        return "confirmed"

    def generate_architecture(self, db: Session, project_id: str, prd_id: str) -> Architecture:
        prd = db.query(PRD).filter(PRD.id == prd_id).first()
        if not prd:
            raise ValueError("PRD not found")

        arch_data = self.llm.generate_architecture(prd.content)
        architecture = Architecture(
            project_id=project_id,
            prd_id=prd_id,
            diagram=arch_data["diagram"],
            description=arch_data["description"],
            confirmed=False
        )
        db.add(architecture)
        db.commit()
        db.refresh(architecture)

        # Update project phase
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.current_phase = "code_generation"

        # Log audit
        audit = AuditLog(
            project_id=project_id,
            phase="architecture_generation",
            start_time=datetime.now(timezone.utc),
            executor="SystemArchitectAgent",
            artifact_version="1.0"
        )
        db.add(audit)
        db.commit()
        return architecture