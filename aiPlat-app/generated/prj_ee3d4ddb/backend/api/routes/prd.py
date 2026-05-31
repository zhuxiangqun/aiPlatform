from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models.prd import PRD
from config import DATABASE_URL
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

router = APIRouter()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

class PRDOut(BaseModel):
    prd: object

@router.get("/api/projects/{project_id}/prd", response_model=PRDOut)
def get_prd(project_id: str):
    db = SessionLocal()
    try:
        prd = db.query(PRD).filter(PRD.project_id == project_id).first()
        if not prd:
            raise HTTPException(status_code=404, detail="PRD not found")
        return {"prd": {"id": prd.id, "content": prd.content, "version": prd.version}}
    finally:
        db.close()