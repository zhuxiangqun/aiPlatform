from sqlalchemy.orm import Session
from uuid import uuid4
from models.prd import PRD
from services.prd_generator import PRDGenerator

class ConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.prd_generator = PRDGenerator(db)

    async def process_message(self, project_id: str, message: str) -> dict:
        # Simulate conversation processing and PRD generation
        prd_id = str(uuid4())
        prd_content = f"Generated PRD based on: {message}"
        prd = PRD(
            id=prd_id,
            project_id=project_id,
            content=prd_content,
            version=1
        )
        self.db.add(prd)
        self.db.commit()
        return {"response": f"PRD generated for your request: {message}", "prd_id": prd_id}