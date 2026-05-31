from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, default="pending")
    result = Column(String, default="")
    executed_at = Column(DateTime, nullable=True)