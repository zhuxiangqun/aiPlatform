from sqlalchemy.orm import Session
from backend.services.skill_registry import SkillRegistry

class AgentManager:
    def __init__(self, db: Session):
        self.db = db
        self.skill_registry = SkillRegistry()

    def execute_skill(self, skill_name: str, params: dict) -> dict:
        return self.skill_registry.execute(skill_name, params)