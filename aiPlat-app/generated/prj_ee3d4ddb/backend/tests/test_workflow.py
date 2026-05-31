import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.project import Base
from backend.services.workflow import WorkflowEngine

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_assign_roles(db_session):
    workflow = WorkflowEngine(db_session)
    result = workflow.assign_roles("test_project", [{"role_name": "PM", "user_id": "user1"}])
    assert result == "roles_assigned"