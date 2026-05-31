import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class BugRecord(Base):
    __tablename__ = "bug_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    test_case_id = Column(UUID(as_uuid=True), nullable=True)
    description = Column(Text, default="")
    fixed_date = Column(DateTime, nullable=True)
    fix_method = Column(Text, default="")
    program_name = Column(String(255), default="")
    status = Column(String(50), default="open")