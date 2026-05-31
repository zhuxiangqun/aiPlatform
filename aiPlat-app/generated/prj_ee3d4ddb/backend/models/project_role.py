from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class ProjectRole(Base):
    __tablename__ = "project_roles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    role_name = Column(String, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)