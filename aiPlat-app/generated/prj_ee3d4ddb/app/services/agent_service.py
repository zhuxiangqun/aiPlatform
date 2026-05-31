from app.services.llm_service import LLMService
from app.models import Project, PRD, Architecture, AuditLog
from app.database import SessionLocal
from datetime import datetime, timezone
import uuid

class AgentService:
    def __init__(self):
        self.llm = LLMService()

    def create_project(self, description: str, team_members: dict) -> dict:
        db = SessionLocal()
        try:
            project = Project(
                description=description,
                team_members=team_members,
                status="created",
                current_phase="prd"
            )
            db.add(project)
            db.commit()
            db.refresh(project)
            
            audit = AuditLog(
                project_id=project.id,
                phase="project_creation",
                start_time=datetime.now(timezone.utc),
                executor="system"
            )
            db.add(audit)
            db.commit()
            
            return {"project_id": project.id, "status": project.status}
        finally:
            db.close()

    def generate_prd(self, project_id: str, conversation_history: list) -> dict:
        db = SessionLocal()
        try:
            content = self.llm.generate_prd(conversation_history)
            prd = PRD(
                project_id=project_id,
                content=content,
                confirmed=False
            )
            db.add(prd)
            
            project = db.query(Project).filter(Project.id == project_id).first()
            project.current_phase = "prd_generated"
            
            audit = AuditLog(
                project_id=project_id,
                phase="prd_generation",
                start_time=datetime.now(timezone.utc),
                executor="ProductManagerAgent"
            )
            db.add(audit)
            db.commit()
            db.refresh(prd)
            
            return {"prd_id": prd.id, "content": prd.content, "confirmed": prd.confirmed}
        finally:
            db.close()

    def confirm_prd(self, project_id: str, prd_id: str) -> dict:
        db = SessionLocal()
        try:
            prd = db.query(PRD).filter(PRD.id == prd_id, PRD.project_id == project_id).first()
            if prd:
                prd.confirmed = True
                project = db.query(Project).filter(Project.id == project_id).first()
                project.current_phase = "prd_confirmed"
                db.commit()
                return {"status": "confirmed"}
            return {"status": "not_found"}
        finally:
            db.close()

    def generate_architecture(self, project_id: str, prd_id: str) -> dict:
        db = SessionLocal()
        try:
            prd = db.query(PRD).filter(PRD.id == prd_id, PRD.project_id == project_id).first()
            if not prd:
                return {"architecture_id": "", "diagram": "", "description": "", "confirmed": False}
            
            arch_content = self.llm.generate_architecture(prd.content)
            parts = arch_content.split("\n\n", 1)
            diagram = parts[0] if parts else ""
            description = parts[1] if len(parts) > 1 else ""
            
            architecture = Architecture(
                project_id=project_id,
                prd_id=prd_id,
                diagram=diagram,
                description=description,
                confirmed=False
            )
            db.add(architecture)
            
            project = db.query(Project).filter(Project.id == project_id).first()
            project.current_phase = "architecture_generated"
            
            audit = AuditLog(
                project_id=project_id,
                phase="architecture_generation",
                start_time=datetime.now(timezone.utc),
                executor="SystemArchitectAgent"
            )
            db.add(audit)
            db.commit()
            db.refresh(architecture)
            
            return {
                "architecture_id": architecture.id,
                "diagram": architecture.diagram,
                "description": architecture.description,
                "confirmed": architecture.confirmed
            }
        finally:
            db.close()