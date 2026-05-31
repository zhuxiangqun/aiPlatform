import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    phase = Column(String(50), default="")
    action = Column(String(255), default="")
    actor = Column(String(100), default="")
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text, default="")