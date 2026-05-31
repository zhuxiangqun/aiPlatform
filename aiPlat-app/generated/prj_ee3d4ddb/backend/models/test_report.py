from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

Base = declarative_base()

class TestReport(Base):
    __tablename__ = "test_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=False)
    pass_rate = Column(Float, default=0.0)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)