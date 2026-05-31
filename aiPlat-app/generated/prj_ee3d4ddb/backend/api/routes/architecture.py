from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.architecture_designer import ArchitectureDesigner
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class ArchitectureOut(BaseModel):
    architecture_id: str

@router.post("/api/projects/{project_id}/architecture", response_model=ArchitectureOut)
def create_architecture(project_id: str):
    db = SessionLocal()
    try:
        designer = ArchitectureDesigner(db)
        architecture_id = designer.generate_architecture(project_id)
        return {"architecture_id": architecture_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()