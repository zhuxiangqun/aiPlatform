import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from services.conversation_service import ConversationService
from services.prd_generator import PRDGenerator
from services.architecture_designer import ArchitectureDesigner

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.mark.asyncio
async def test_conversation_service(db_session):
    service = ConversationService(db_session)
    result = await service.process_message("test-project", "Hello")
    assert "response" in result
    assert "prd_id" in result

@pytest.mark.asyncio
async def test_prd_generator(db_session):
    service = PRDGenerator(db_session)
    prd_id = await service.generate("test-project")
    assert prd_id is not None

@pytest.mark.asyncio
async def test_architecture_designer(db_session):
    service = ArchitectureDesigner(db_session)
    arch_id = await service.generate("test-project")
    assert arch_id is not None