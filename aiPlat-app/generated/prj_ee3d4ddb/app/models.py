from sqlalchemy import Column, String, Text, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Project(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="created")
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
    current_phase = Column(String, default="prd")

class PRD(Base):
    __tablename__ = "prds"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    content = Column(Text)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class Architecture(Base):
    __tablename__ = "architectures"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    prd_id = Column(String, ForeignKey("prds.id"))
    diagram = Column(Text)
    description = Column(Text)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class Code(Base):
    __tablename__ = "codes"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    arch_id = Column(String, ForeignKey("architectures.id"))
    type = Column(String)
    content = Column(Text)
    version = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class TestSuite(Base):
    __tablename__ = "test_suites"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    prd_id = Column(String, ForeignKey("prds.id"))
    test_cases = Column(Text)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class TestReport(Base):
    __tablename__ = "test_reports"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    test_suite_id = Column(String, ForeignKey("test_suites.id"))
    pass_rate = Column(Float)
    failures = Column(Text)
    logs = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class BugRecord(Base):
    __tablename__ = "bug_records"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    test_report_id = Column(String, ForeignKey("test_reports.id"))
    failed_test = Column(String)
    code_snippet = Column(Text)
    fix_date = Column(DateTime, nullable=True)
    fix_method = Column(String)
    program_name = Column(String)
    status = Column(String, default="open")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"))
    phase = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    executor = Column(String)
    artifact_version = Column(String)