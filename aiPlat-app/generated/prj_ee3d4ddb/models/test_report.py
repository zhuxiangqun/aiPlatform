from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from . import Base

class TestReport(Base):
    __tablename__ = "test_reports"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    test_case_id = Column(String, ForeignKey("test_cases.id"), nullable=False)
    pass_rate = Column(Float, default=0.0)
    details = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())