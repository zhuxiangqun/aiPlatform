from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.conversation_service import ConversationService
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class ConversationInput(BaseModel):
    message: str

class ConversationOut(BaseModel):
    response: str
    prd_id: str

@router.post("/api/projects/{project_id}/conversation", response_model=ConversationOut)
def handle_conversation(project_id: str, input_data: ConversationInput):
    db = SessionLocal()
    try:
        service = ConversationService(db)
        result = service.process_message(project_id, input_data.message)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()