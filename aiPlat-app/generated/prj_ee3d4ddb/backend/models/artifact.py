from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

Base = declarative_base()

class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    type = Column(String, nullable=False)
    content = Column(Text, default="")
    version = Column(Integer, default=1)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)