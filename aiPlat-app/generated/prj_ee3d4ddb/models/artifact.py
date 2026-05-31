import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    type = Column(String(50), nullable=False)
    content = Column(Text, default="")
    version = Column(Integer, default=1)
    created_by = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)