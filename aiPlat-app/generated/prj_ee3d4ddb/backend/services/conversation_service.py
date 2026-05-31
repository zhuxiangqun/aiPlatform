from sqlalchemy.orm import Session
from models.prd import PRD
from models.project import Project
from services.prd_generator import PRDGenerator
import uuid

class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.prd_generator = PRDGenerator(db)

    def process_message(self, project_id: str, message: str) -> dict:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("Project not found")
        prd_content = self.prd_generator.generate_prd(project_id, message)
        prd_id = str(uuid.uuid4())
        prd = PRD(id=prd_id, project_id=project_id, content=prd_content)
        self.db.add(prd)
        self.db.commit()
        return {"response": f"PRD generated for project {project.name}", "prd_id": prd_id}