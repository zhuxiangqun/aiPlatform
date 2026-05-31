from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class BugRecord(Base):
    __tablename__ = "bug_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=False)
    description = Column(Text, default="")
    fixed_date = Column(DateTime, nullable=True)
    fix_method = Column(Text, default="")
    program_name = Column(String, default="")
    status = Column(String, default="open")